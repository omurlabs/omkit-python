"""Backend-agnostic event bus for cross-service pub/sub notifications.

Implementations:

- ``PostgresEventBus`` (default) writes events to the ``events`` table and
  delivers them to subscribers by polling; each consumer tracks its offset in
  ``event_offsets``.
- ``RedisEventBus`` (opt-in via ``OMUR_EVENTBUS_BACKEND=redis``) uses Redis
  Streams consumer groups — the same wire-format used by the legacy
  ``omur_sdk.events.EventBus`` wrapper so both can coexist.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol


@dataclass
class Event:
    id: int
    topic: str
    payload: Any
    tenant_id: Optional[str] = None  # None for global/system events
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Handler = Callable[[Event], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, topic: str, payload: Any) -> None: ...
    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None: ...
    async def subscribe(self, topic: str, handler: Handler) -> None: ...
    async def close(self) -> None: ...


def _parse_payload(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value)
    return value


class PostgresEventBus:
    """Polling-based event bus backed by ``events`` and ``event_offsets``."""

    def __init__(
        self,
        pool,
        *,
        consumer_name: str,
        poll_interval: float = 5.0,
        batch_size: int = 100,
    ):
        self._pool = pool
        self._consumer = consumer_name
        self._poll_interval = poll_interval
        self._batch = batch_size
        self._stop = asyncio.Event()

    async def _as_bus_role(self, conn) -> None:
        """Drop the per-connection omur_app role and disable row_security.

        The event bus is infrastructure — subscribers must see every tenant's
        events on their topic, and publishes happen outside a user session.
        Pool owner must be a superuser or BYPASSRLS role. Mirror of the Go
        SDK's withBusRole pattern.
        """
        await conn.execute("RESET ROLE")
        await conn.execute("SET LOCAL row_security = off")

    async def publish(self, topic: str, payload: Any) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._as_bus_role(conn)
                await conn.execute(
                    "INSERT INTO events (topic, payload) VALUES ($1, $2::jsonb)",
                    topic,
                    json.dumps(payload),
                )

    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None:
        if not tenant_id:
            await self.publish(topic, payload)
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._as_bus_role(conn)
                await conn.execute(
                    "INSERT INTO events (tenant_id, topic, payload) "
                    "VALUES ($1::uuid, $2, $3::jsonb)",
                    tenant_id,
                    topic,
                    json.dumps(payload),
                )

    async def subscribe(self, topic: str, handler: Handler) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._as_bus_role(conn)
                await conn.execute(
                    "INSERT INTO event_offsets (consumer, topic, last_id) "
                    "VALUES ($1, $2, 0) ON CONFLICT DO NOTHING",
                    self._consumer,
                    topic,
                )
        # Drain once immediately so short-lived subscribers and tests don't
        # have to wait a full poll_interval for the first delivery.
        try:
            await self._poll_once(topic, handler)
        except Exception:
            pass
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._poll_interval
                )
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                return
            try:
                await self._poll_once(topic, handler)
            except Exception:
                pass

    async def _poll_once(self, topic: str, handler: Handler) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._as_bus_role(conn)
                rows = await conn.fetch(
                    "SELECT id, tenant_id::text AS tenant_id, topic, payload, created_at FROM events "
                    "WHERE topic = $1 AND id > ("
                    "  SELECT last_id FROM event_offsets WHERE consumer = $2 AND topic = $1"
                    ") ORDER BY id ASC LIMIT $3",
                    topic,
                    self._consumer,
                    self._batch,
                )
            last_id = 0
            for r in rows:
                e = Event(
                    id=r["id"],
                    tenant_id=r["tenant_id"],
                    topic=r["topic"],
                    payload=_parse_payload(r["payload"]),
                    created_at=r["created_at"],
                )
                await handler(e)
                last_id = r["id"]
            if last_id:
                async with conn.transaction():
                    await self._as_bus_role(conn)
                    await conn.execute(
                        "UPDATE event_offsets SET last_id = $1 "
                        "WHERE consumer = $2 AND topic = $3",
                        last_id,
                        self._consumer,
                        topic,
                    )

    async def close(self) -> None:
        self._stop.set()


class RedisEventBus:
    """Redis Streams consumer-group event bus."""

    def __init__(
        self,
        redis_client,
        *,
        consumer_name: str,
        group: str,
        stream_prefix: str = "omur:events:",
    ):
        self._r = redis_client
        self._consumer = consumer_name
        self._group = group
        self._prefix = stream_prefix
        self._stop = asyncio.Event()

    def _stream(self, topic: str) -> str:
        return self._prefix + topic

    async def publish(self, topic: str, payload: Any) -> None:
        await self._r.xadd(self._stream(topic), {"payload": json.dumps(payload)})

    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None:
        await self._r.xadd(
            self._stream(topic),
            {"tenant_id": tenant_id, "payload": json.dumps(payload)},
        )

    async def subscribe(self, topic: str, handler: Handler) -> None:
        stream = self._stream(topic)
        try:
            await self._r.xgroup_create(stream, self._group, id="0", mkstream=True)
        except Exception:
            pass
        while not self._stop.is_set():
            try:
                resp = await self._r.xreadgroup(
                    self._group,
                    self._consumer,
                    {stream: ">"},
                    count=100,
                    block=2000,
                )
            except Exception:
                await asyncio.sleep(1)
                continue
            for _stream_name, msgs in resp or []:
                for msg_id, fields in msgs:
                    payload_raw = fields.get(b"payload") or fields.get("payload")
                    if isinstance(payload_raw, bytes):
                        payload_raw = payload_raw.decode()
                    tenant_raw = fields.get(b"tenant_id") or fields.get("tenant_id")
                    if isinstance(tenant_raw, bytes):
                        tenant_raw = tenant_raw.decode()
                    payload = json.loads(payload_raw)
                    e = Event(
                        id=0,
                        tenant_id=tenant_raw or None,
                        topic=topic,
                        payload=payload,
                    )
                    try:
                        await handler(e)
                        await self._r.xack(stream, self._group, msg_id)
                    except Exception:
                        continue

    async def close(self) -> None:
        self._stop.set()
        await self._r.aclose()


def backend_from_env() -> str:
    v = os.getenv("OMUR_EVENTBUS_BACKEND", "postgres")
    if v not in {"postgres", "redis"}:
        raise ValueError(f"unknown OMUR_EVENTBUS_BACKEND: {v}")
    return v


async def new_bus(
    *,
    pool=None,
    redis_client=None,
    consumer_name: str,
    group: Optional[str] = None,
) -> EventBus:
    backend = backend_from_env()
    if backend == "postgres":
        if pool is None:
            raise ValueError("postgres backend requires pool=")
        return PostgresEventBus(pool, consumer_name=consumer_name)
    if backend == "redis":
        if redis_client is None:
            import redis.asyncio as aioredis

            host = os.getenv("VALKEY_HOST", "valkey")
            port = os.getenv("VALKEY_PORT", "6379")
            password = os.getenv("VALKEY_PASSWORD") or None
            url = (
                f"redis://:{password}@{host}:{port}"
                if password
                else f"redis://{host}:{port}"
            )
            redis_client = aioredis.from_url(url)
        return RedisEventBus(
            redis_client,
            consumer_name=consumer_name,
            group=group or consumer_name,
        )
    raise RuntimeError("unreachable")
