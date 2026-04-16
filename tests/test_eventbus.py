import asyncio
import os

import asyncpg
import pytest

from omur_sdk.eventbus import PostgresEventBus, RedisEventBus, backend_from_env


@pytest.fixture
async def pool():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    p = await asyncpg.create_pool(dsn)
    async with p.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
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


def test_backend_from_env(monkeypatch):
    monkeypatch.delenv("OMUR_EVENTBUS_BACKEND", raising=False)
    assert backend_from_env() == "postgres"
    monkeypatch.setenv("OMUR_EVENTBUS_BACKEND", "redis")
    assert backend_from_env() == "redis"
    monkeypatch.setenv("OMUR_EVENTBUS_BACKEND", "garbage")
    with pytest.raises(ValueError):
        backend_from_env()


@pytest.mark.asyncio
async def test_redis_bus_publish_subscribe():
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
