"""omkit/scheduler/scheduler.py — DB-driven reconcile loop.

Diff engine: every poll_interval, fetch desired (tenant, provider) rows from
the ProviderSource, compare to currently-registered entries on the backend,
and Register / Unregister to converge.

Re-register on change: each entry carries a SHA-256 hash of
`(cronspec, canonical_json(config))`. When the hash drifts, the loop
unregisters the old entry_id and registers fresh.

exports: Scheduler | DEFAULT_POLL_INTERVAL
rules:   reconcile() failures (DB fetch error, backend register error) are
         logged at WARNING and retried next tick — never crash the loop.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/scheduler
message:
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from omkit.jobqueue.envelope import wrap
from omkit.scheduler.types import (
    CronDeriver,
    Enqueuer,
    Provider,
    ProviderSource,
    SchedulerBackend,
)

_log = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 10.0  # seconds, matches omkit-go default


class _RegisteredEntry:
    __slots__ = ("entry_id", "hash", "cronspec")

    def __init__(self, entry_id: str, hash_: str, cronspec: str):
        self.entry_id = entry_id
        self.hash = hash_
        self.cronspec = cronspec


class Scheduler:
    """DB-driven cron reconciler.

    Wraps any `SchedulerBackend` with a poll-and-diff loop. Call `start()`
    once at service startup and `stop()` on shutdown.
    """

    def __init__(
        self,
        backend: SchedulerBackend,
        source: ProviderSource,
        *,
        kind: str,
        queue: str,
        task_type: str,
        derive_cron: CronDeriver,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        enqueuer: Enqueuer | None = None,
    ):
        self._backend = backend
        self._source = source
        self._kind = kind
        self._queue = queue
        self._task_type = task_type
        self._derive_cron = derive_cron
        self._poll_interval = poll_interval
        self._enqueuer = enqueuer

        self._entries: dict[str, _RegisteredEntry] = {}
        self._lock = asyncio.Lock()
        self._loop_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Initial reconcile, start backend, kick off the loop."""
        await self._backend.start()
        await self._reconcile()
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop())
        _log.info(
            "scheduler.started kind=%s entries=%d",
            self._kind,
            len(self._entries),
        )

    async def stop(self) -> None:
        """Cancel the loop and shut down the backend."""
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None
        await self._backend.shutdown()
        _log.info("scheduler.stopped kind=%s", self._kind)

    def entries(self) -> list[str]:
        """Sorted list of currently-registered `<tenant>:<name>` keys."""
        return sorted(self._entries.keys())

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval,
                    )
                    return  # stop signaled
                except asyncio.TimeoutError:
                    pass
                await self._reconcile()
        except asyncio.CancelledError:
            return

    async def _reconcile(self) -> None:
        try:
            rows = await self._source.fetch_providers(self._kind)
        except Exception as exc:
            _log.warning("scheduler.fetch_failed kind=%s err=%s", self._kind, exc)
            return

        desired: dict[str, Provider] = {
            _key(r.tenant_id, r.name): r for r in rows
        }

        async with self._lock:
            # Unregister entries no longer in DB.
            stale = [k for k in self._entries if k not in desired]
            for k in stale:
                ent = self._entries[k]
                try:
                    await self._backend.unregister(ent.entry_id)
                except Exception as exc:
                    _log.warning(
                        "scheduler.unregister_failed key=%s err=%s", k, exc
                    )
                    continue
                del self._entries[k]
                _log.info("scheduler.unregistered key=%s", k)

            # Register new or changed entries.
            for k, p in desired.items():
                cronspec, ok = self._derive_cron(p)
                if not ok:
                    continue
                h = _config_hash(cronspec, p.config)
                existing = self._entries.get(k)
                if existing is not None:
                    if existing.hash == h:
                        continue
                    try:
                        await self._backend.unregister(existing.entry_id)
                    except Exception as exc:
                        _log.warning(
                            "scheduler.reregister_unregister_failed "
                            "key=%s err=%s",
                            k,
                            exc,
                        )
                        continue
                    del self._entries[k]

                try:
                    entry_id = await self._register_one(p, cronspec)
                except Exception as exc:
                    _log.warning(
                        "scheduler.register_failed key=%s err=%s", k, exc
                    )
                    continue
                self._entries[k] = _RegisteredEntry(entry_id, h, cronspec)
                _log.info(
                    "scheduler.registered key=%s cronspec=%s", k, cronspec
                )

                if self._enqueuer is not None:
                    try:
                        await self._enqueuer.enqueue(
                            self._task_type,
                            p.tenant_id,
                            _build_payload(p),
                            queue=self._queue,
                        )
                    except Exception as exc:
                        _log.warning(
                            "scheduler.immediate_enqueue_failed "
                            "key=%s err=%s",
                            k,
                            exc,
                        )

    async def _register_one(self, p: Provider, cronspec: str) -> str:
        payload = _build_payload(p)
        body = wrap(p.tenant_id, payload)
        return await self._backend.register(
            cronspec, self._task_type, body, queue=self._queue
        )


def _build_payload(p: Provider) -> dict[str, Any]:
    """Mirrors Go's providerSyncPayload: provider_name + raw config JSON."""
    try:
        cfg_str = json.dumps(p.config, sort_keys=True)
    except (TypeError, ValueError):
        cfg_str = "{}"
    return {"provider_name": p.name, "config": cfg_str}


def _key(tenant: str, name: str) -> str:
    return f"{tenant}:{name}"


def _config_hash(cronspec: str, cfg: dict[str, Any]) -> str:
    """Deterministic SHA-256 of (cronspec || \\0 || canonical_json(cfg))."""
    body = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    h = hashlib.sha256()
    h.update(cronspec.encode())
    h.update(b"\x00")
    h.update(body)
    return h.hexdigest()
