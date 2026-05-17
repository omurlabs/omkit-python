"""packages/omur-sdk/tests/test_eventbus.py — test_eventbus module.

exports: pool() | test_postgres_bus_publish_subscribe(pool) | test_backend_from_env(monkeypatch) | test_redis_bus_publish_subscribe()
rules:   The module requires explicit environment variable configuration for database and Redis connections, and all tests must be isolated to prevent cross-test pollution of event bus state.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import asyncio
import os

import asyncpg
import pytest

from omur_sdk.eventbus import (
    NIL_TENANT_ID,
    PostgresEventBus,
    RedisEventBus,
    backend_from_env,
)


@pytest.fixture
async def pool():
    """
    Rules:   Database connection requires TEST_POSTGRES_DSN environment variable to be set. If not set, the test will be skipped. The function creates a PostgreSQL table with specific schema constraints including primary key, not null constraints, and default values.
    """
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    p = await asyncpg.create_pool(dsn)
    async with p.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID,
                topic TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                consumed BOOLEAN NOT NULL DEFAULT false
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_offsets (
                consumer TEXT NOT NULL,
                topic TEXT NOT NULL,
                last_id BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (consumer, topic)
            )
            """
        )
        await conn.execute("DELETE FROM events WHERE topic LIKE 'test.py.%'")
        await conn.execute(
            "DELETE FROM event_offsets WHERE consumer = 'test-py-consumer'"
        )
    yield p
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM events WHERE topic LIKE 'test.py.%'")
        await conn.execute(
            "DELETE FROM event_offsets WHERE consumer = 'test-py-consumer'"
        )
    await p.close()


@pytest.mark.asyncio
async def test_postgres_bus_publish_subscribe(pool):
    """
    Rules:   The test assumes a specific timing window (0.1s intervals) for message delivery, which may fail if the system is slow or under load.
    """
    bus = PostgresEventBus(pool, consumer_name="test-py-consumer", poll_interval=0.1)
    received: list = []

    async def handler(event):
        received.append(event)

    sub_task = asyncio.create_task(bus.subscribe("test.py.topic", handler))
    await asyncio.sleep(0.2)
    await bus.publish("test.py.topic", {"k": "v"})
    for _ in range(20):
        await asyncio.sleep(0.1)
        if received:
            break
    await bus.close()
    sub_task.cancel()
    try:
        await sub_task
    except asyncio.CancelledError:
        pass
    assert received, "expected at least one delivered event"
    assert received[0].payload == {"k": "v"}

    # #549 — publish() must stamp the nil-UUID sentinel so admin-role
    # readers can see the row under the migration-0005 RLS policy.
    async with pool.acquire() as conn:
        stored_tenant = await conn.fetchval(
            "SELECT tenant_id::text FROM events "
            "WHERE topic = 'test.py.topic' ORDER BY id DESC LIMIT 1"
        )
    assert stored_tenant == NIL_TENANT_ID, (
        f"publish() stored tenant_id = {stored_tenant!r}, "
        f"want NIL_TENANT_ID {NIL_TENANT_ID!r}"
    )


def test_backend_from_env(monkeypatch):
    """
    Rules:   Function assumes environment variable 'OMUR_EVENTBUS_BACKEND' controls backend selection, with 'postgres' as default and only 'redis' or 'postgres' as valid values, raising ValueError for invalid inputs.
    """
    monkeypatch.delenv("OMUR_EVENTBUS_BACKEND", raising=False)
    assert backend_from_env() == "postgres"
    monkeypatch.setenv("OMUR_EVENTBUS_BACKEND", "redis")
    assert backend_from_env() == "redis"
    monkeypatch.setenv("OMUR_EVENTBUS_BACKEND", "garbage")
    with pytest.raises(ValueError):
        backend_from_env()


@pytest.mark.asyncio
async def test_redis_bus_publish_subscribe():
    """
    Rules:   The test requires TEST_REDIS_ADDR to be set and may fail if Redis is not reachable or misconfigured.
    """
    addr = os.getenv("TEST_REDIS_ADDR")
    if not addr:
        pytest.skip("TEST_REDIS_ADDR not set")
    import redis.asyncio as aioredis

    password = os.getenv("TEST_REDIS_PASSWORD") or None
    host, port = addr.split(":")
    url = (
        f"redis://:{password}@{host}:{port}" if password else f"redis://{host}:{port}"
    )
    client = aioredis.from_url(url)
    bus = RedisEventBus(
        client,
        consumer_name="test-py",
        group="test-py-group",
        stream_prefix="test:omur:events:",
    )
    received: list = []

    async def handler(event):
        received.append(event)

    sub_task = asyncio.create_task(bus.subscribe("redistopic", handler))
    await asyncio.sleep(0.2)
    await bus.publish("redistopic", {"r": 1})
    for _ in range(20):
        await asyncio.sleep(0.1)
        if received:
            break
    await bus.close()
    sub_task.cancel()
    try:
        await sub_task
    except asyncio.CancelledError:
        pass
    assert received
    assert received[0].payload == {"r": 1}
