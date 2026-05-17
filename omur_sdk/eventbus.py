"""packages/omur-sdk/omur_sdk/eventbus.py — Backend-agnostic event bus for cross-service pub/sub notifications.

Implementations:

- ``PostgresEventBus`` (default) writes events to the ``events`` table and
  delivers them to subscribers by polling; each consumer tracks its offset in
  ``event_offsets``.
- ``RedisEventBus`` (opt-in via ``OMUR_EVENTBUS_BACKEND=redis``) uses Redis
  Streams consumer groups — the same wire-format used by the legacy
  ``omur_sdk.events.EventBus`` wrapper so both can coexist.

exports: class Event | class EventBus | class PostgresEventBus | class RedisEventBus | backend_from_env() | new_bus() | NIL_TENANT_ID
rules:   The EventBus module must support both PostgreSQL and Redis backends, with PostgreSQL as the default, and all implementations must adhere to the provided `EventBus` protocol interface.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message:
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol

# Nil-UUID sentinel for system-level events with no tenant context. Matches
# the pattern used by ``security_events`` and the events RLS policy in
# migration 0005: rows stamped with this sentinel are readable by sessions
# that have ``SET app.role = 'admin'`` and writable by ``service`` role
# sessions, but invisible to ordinary tenant connections. Mirrors
# ``NilTenantID`` in packages/omur-go-sdk/eventbus/postgres.go.
NIL_TENANT_ID = "00000000-0000-0000-0000-000000000000"


@dataclass
class Event:
    id: int
    topic: str
    payload: Any
    tenant_id: Optional[str] = None  # None for global/system events
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Handler = Callable[[Event], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, topic: str, payload: Any) -> None:
        """
        Rules:   The publish method must asynchronously send the given payload to the specified topic and return immediately without blocking. Implementations must handle any necessary serialization of the payload and ensure the topic parameter is a valid string identifier.
        """
        ...
    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None:
        """
        Rules:   The tenant_id must correspond to an existing tenant, topic must be a valid publishable topic string, and payload must be serializable. The function asynchronously publishes the payload to the specified topic for the given tenant without returning a value.
        """
        ...
    async def subscribe(self, topic: str, handler: Handler) -> None:
        """
        Rules:   The subscribe method must register the handler to receive messages from the specified topic, with the handler being called asynchronously when messages arrive. The topic parameter must be a valid string identifying the message source, and the handler must be a callable that accepts the message content as its only argument.
        """
        ...
    async def close(self) -> None:
        """
        Rules:   Async close method must be idempotent and handle concurrent calls gracefully, ensuring all resources are properly released and no further operations should be performed after calling close. Implementations must not raise exceptions during cleanup, and the method should complete within a reasonable timeout period.
        """
        ...


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
        """Publish a system-level event with the nil-UUID tenant sentinel.

        Before migration 0005 this wrote NULL tenant_id; the new RLS policy
        hides NULL rows from every connection except the bus itself, which
        left the table internally inconsistent. Writing ``NIL_TENANT_ID``
        keeps the row admin-readable while preserving the cross-tenant leak
        fix.

        Rules: Function requires topic string and payload any object that
        serializes to JSON, uses connection pool for database operations,
        and executes within a transaction that sets bus role. Function
        must be called within an async context and handles JSON
        serialization internally.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._as_bus_role(conn)
                await conn.execute(
                    "INSERT INTO events (tenant_id, topic, payload) "
                    "VALUES ($1::uuid, $2, $3::jsonb)",
                    NIL_TENANT_ID,
                    topic,
                    json.dumps(payload),
                )

    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None:
        """
        Rules:   Function requires tenant_id to be a valid UUID string when provided, otherwise publishes to the topic directly without tenant isolation. Function must be called within an async context and requires a valid database connection pool with proper transaction handling. The payload must be JSON serializable, and the function assumes the database schema includes an events table with tenant_id, topic, and payload columns.
        """
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
        """
        Rules:   The subscribe method requires a valid topic string and handler function, performs database operations to register the consumer-topic relationship, and may raise exceptions during initial polling or subsequent periodic polling. The method runs asynchronously and will continue polling until the internal stop event is set, with exceptions during polling silently ignored.
        """
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
        """
        Rules:   The close method must be called to signal the async operation to stop, and it should only be called once per instance. The method is not thread-safe and should only be called from the same thread that started the async operation.
        """
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
        """
        Rules:   The publish method requires a valid topic string and serializable payload, performs asynchronous Redis stream insertion with JSON-encoded data, and must be called on an initialized instance with active Redis connection. The method has no side effects beyond the Redis operation and assumes the underlying Redis stream and connection are properly configured.
        """
        await self._r.xadd(self._stream(topic), {"payload": json.dumps(payload)})

    async def publish_tenant(
        self, tenant_id: str, topic: str, payload: Any
    ) -> None:
        """
        Rules:   Function requires tenant_id and topic to be non-empty strings, payload can be any JSON-serializable object, and must not be called with None values for tenant_id or topic. The function performs an asynchronous Redis stream write operation with no side effects beyond the Redis storage modification.
        """
        await self._r.xadd(
            self._stream(topic),
            {"tenant_id": tenant_id, "payload": json.dumps(payload)},
        )

    async def subscribe(self, topic: str, handler: Handler) -> None:
        """
        Rules:   The subscribe method asynchronously subscribes to a Redis stream topic and processes messages using the provided handler, with the handler expected to be an async callable that accepts an Event object. The method creates a Redis stream group if it doesn't exist and acknowledges processed messages, while gracefully handling connection issues and message processing errors without stopping the subscription loop.
        """
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
        """
        Rules:   The close method must be called to properly terminate the async iterator and clean up resources, and it should only be called once per instance. The method sets an internal stop flag and asynchronously closes the underlying resource, ensuring proper cleanup of the async context.
        """
        self._stop.set()
        await self._r.aclose()


def backend_from_env() -> str:
    """
    Rules:   Function reads OMUR_EVENTBUS_BACKEND environment variable and returns "postgres" or "redis" string, raising ValueError for invalid values. If environment variable is not set, it defaults to "postgres".
    """
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
    """
    Rules:   Function requires either pool parameter for postgres backend or redis_client parameter for redis backend, with redis_client being optional only when backend is redis and environment variables are set for connection. Function raises ValueError for postgres backend when pool is None, and RuntimeError for unreachable backend cases. Returns EventBus instance configured for the specified backend type.
    """
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
