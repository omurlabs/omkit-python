"""ProviderRegistry — loads providers from DB, manages asyncio tasks, hot-reloads via Valkey."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from .base import ProviderBase

log = structlog.get_logger()


class ProviderRegistry:
    """
    Manages one asyncio Task per active (tenant_id, provider_name) pair.

    Lifecycle:
    - start(): load all enabled providers from DB, start tasks, subscribe to Valkey
    - stop(): cancel all tasks cleanly
    - _reload_tenant(tenant_id): cancel stale tasks, re-query DB, start new tasks

    Valkey channel: omur:providers:updated:{tenant_id}
    On reconnect after Valkey disconnect: re-read full providers table to reconcile
    any events missed during the outage (reconnect-with-exponential-backoff).
    """

    def __init__(
        self,
        kind: str,
        provider_classes: dict[str, type[ProviderBase]],
        postgres_dsn: str,
        valkey_url: str,
    ) -> None:
        self.kind = kind
        self.provider_classes = provider_classes
        self._postgres_dsn = postgres_dsn
        self._valkey_url = valkey_url
        self._tasks: dict[str, asyncio.Task] = {}  # key: "{tenant_id}:{name}"
        self._valkey_task: asyncio.Task | None = None
        self._table_missing: bool = False

    # ── Public API ────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            rows = await self._fetch_providers()
        except Exception as exc:
            log.warning("registry.db_unavailable", kind=self.kind, error=str(exc))
            rows = []
        for row in rows:
            self._start_task(row["tenant_id"], row["name"], row["config"])
        self._valkey_task = asyncio.create_task(self._subscribe_valkey())
        log.info("registry.started", kind=self.kind, tasks=len(self._tasks))

    async def stop(self) -> None:
        if self._valkey_task:
            self._valkey_task.cancel()
            await asyncio.gather(self._valkey_task, return_exceptions=True)
        await self._cancel_tasks(list(self._tasks.keys()))
        log.info("registry.stopped", kind=self.kind)

    async def _reload_tenant(self, tenant_id: str) -> None:
        # Cancel all tasks for this tenant
        tenant_keys = [k for k in self._tasks if k.startswith(f"{tenant_id}:")]
        await self._cancel_tasks(tenant_keys)

        # Re-query and restart
        rows = await self._fetch_providers(tenant_id=tenant_id)
        for row in rows:
            self._start_task(row["tenant_id"], row["name"], row["config"])
        log.info("registry.tenant_reloaded", tenant_id=tenant_id, new_tasks=len(rows))

    # ── Internal ─────────────────────────────────────────────────

    def _start_task(self, tenant_id: str, name: str, config: dict[str, Any]) -> None:
        cls = self.provider_classes.get(name)
        if cls is None:
            log.warning("registry.unknown_provider", name=name, tenant_id=tenant_id)
            return
        key = f"{tenant_id}:{name}"
        assert key not in self._tasks, f"Task {key!r} already running — cancel before starting"
        instance = cls(tenant_id=tenant_id, config=config)
        task = asyncio.create_task(instance.run(), name=key)
        task.add_done_callback(lambda t, k=key: self._on_task_done(k, t))
        self._tasks[key] = task
        log.info("registry.task_started", key=key)

    def _on_task_done(self, key: str, task: asyncio.Task) -> None:
        """Remove crashed tasks from _tasks so reconcile can restart them."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("registry.task_crashed", key=key, error=str(exc))
            self._tasks.pop(key, None)

    async def _cancel_tasks(self, keys: list[str]) -> None:
        tasks = []
        for key in keys:
            task = self._tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
                tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_providers(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """Query DB for enabled providers of this registry's kind.

        Returns [] and logs a warning if the providers table doesn't exist yet
        (pre-migration state). The warning is rate-limited to avoid log spam.
        """
        import asyncpg
        conn = await asyncpg.connect(self._postgres_dsn.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            if tenant_id:
                rows = await conn.fetch(
                    "SELECT tenant_id::text, name, config FROM providers "
                    "WHERE kind = $1 AND enabled = TRUE AND tenant_id = $2::uuid",
                    self.kind, tenant_id,
                )
            else:
                rows = await conn.fetch(
                    "SELECT tenant_id::text, name, config FROM providers "
                    "WHERE kind = $1 AND enabled = TRUE",
                    self.kind,
                )
            if self._table_missing:
                log.info("registry.table_available", kind=self.kind)
                self._table_missing = False
            return [{"tenant_id": r["tenant_id"], "name": r["name"], "config": r["config"]} for r in rows]
            # asyncpg auto-deserializes JSONB to dict — no json.loads() needed
        except asyncpg.UndefinedTableError:
            if not self._table_missing:
                log.warning("registry.table_missing", kind=self.kind,
                            hint="run the migrate container to create the providers table")
                self._table_missing = True
            return []
        finally:
            await conn.close()

    async def _subscribe_valkey(self) -> None:
        """
        Subscribe to omur:providers:updated:* and reload tenants on events.
        Implements reconnect-with-exponential-backoff.
        On reconnect, performs a full provider reconciliation to catch missed events.
        """
        import redis.asyncio as redis

        backoff = 1.0
        while True:
            client = None
            pubsub = None
            try:
                client = redis.from_url(self._valkey_url)
                pubsub = client.pubsub()
                await pubsub.psubscribe("omur:providers:updated:*")
                log.info("registry.valkey_subscribed", kind=self.kind)
                backoff = 1.0

                # On (re)connect: full reconciliation to catch missed events
                await self._reconcile_all()

                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue
                    channel: str = message["channel"].decode()
                    tenant_id = channel.split(":")[-1]
                    await self._reload_tenant(tenant_id)

            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("registry.valkey_disconnected", error=str(exc), retry_in=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            finally:
                if pubsub is not None:
                    await pubsub.aclose()
                if client is not None:
                    await client.aclose()

    async def _reconcile_all(self) -> None:
        """Re-read all enabled providers from DB and sync running tasks."""
        rows = await self._fetch_providers()
        desired = {f"{r['tenant_id']}:{r['name']}": r for r in rows}
        current = set(self._tasks.keys())
        desired_keys = set(desired.keys())

        # Cancel tasks no longer in DB
        await self._cancel_tasks(list(current - desired_keys))

        # Start new tasks not yet running
        for key in desired_keys - current:
            row = desired[key]
            self._start_task(row["tenant_id"], row["name"], row["config"])
