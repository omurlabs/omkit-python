"""packages/omur-sdk/tests/test_sessions.py — test_sessions module.

exports: pool() | test_postgres_store_put_get_delete(pool) | test_postgres_store_expired(pool) | test_postgres_store_list(pool) | test_backend_from_env(monkeypatch) | test_new_store_postgres_requires_pool(monkeypatch) | test_redis_store_put_get_delete()
used_by: none
rules:   The module requires explicit environment configuration for database connections and does not support implicit fallbacks or default configurations for session backends.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import os
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from omur_sdk.sessions import (
    NotFound,
    PostgresSessionStore,
    RedisSessionStore,
    Session,
    backend_from_env,
    new_store,
)


@pytest.fixture
async def pool():
    """
    Rules:   The TEST_POSTGRES_DSN environment variable must be set for the test to run, otherwise it will be skipped. The database table 'sessions' is created with specific constraints (e.g., token as primary key, tenant_id and payload as NOT NULL).
    """
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    p = await asyncpg.create_pool(dsn)
    async with p.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                tenant_id UUID NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                expires_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    yield p
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE token LIKE 'ptest-%'")
    await p.close()


@pytest.mark.asyncio
async def test_postgres_store_put_get_delete(pool):
    """
    Rules:   The session token must be unique in the database; inserting a duplicate token will cause a database constraint violation.
    """
    store = PostgresSessionStore(pool)
    s = Session(
        token="ptest-1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        payload={"k": "v"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await store.put(s)
    got = await store.get("ptest-1")
    assert got.payload == {"k": "v"}
    assert got.tenant_id == "00000000-0000-0000-0000-000000000001"
    await store.delete("ptest-1")
    with pytest.raises(NotFound):
        await store.get("ptest-1")


@pytest.mark.asyncio
async def test_postgres_store_expired(pool):
    """
    Rules:   Expired sessions (where expires_at is in the past) are automatically rejected by the store and raise a NotFound exception when attempting to retrieve them.
    """
    store = PostgresSessionStore(pool)
    s = Session(
        token="ptest-expired",
        tenant_id="00000000-0000-0000-0000-000000000001",
        payload={},
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    await store.put(s)
    with pytest.raises(NotFound):
        await store.get("ptest-expired")


@pytest.mark.asyncio
async def test_postgres_store_list(pool):
    """
    Rules:   The list function filters sessions by tenant_id, so only sessions belonging to the specified tenant will be returned.
    """
    store = PostgresSessionStore(pool)
    tenant = "00000000-0000-0000-0000-000000000002"
    for tok in ("ptest-list-a", "ptest-list-b"):
        await store.put(
            Session(
                token=tok,
                tenant_id=tenant,
                payload={},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
    rows = await store.list(tenant)
    tokens = {r.token for r in rows}
    assert {"ptest-list-a", "ptest-list-b"}.issubset(tokens)


def test_backend_from_env(monkeypatch):
    """
    Rules:   The OMUR_SESSION_BACKEND environment variable must be one of 'postgres', 'redis', or unset (defaults to 'postgres'). Any other value will raise a ValueError.
    """
    monkeypatch.delenv("OMUR_SESSION_BACKEND", raising=False)
    assert backend_from_env() == "postgres"
    monkeypatch.setenv("OMUR_SESSION_BACKEND", "redis")
    assert backend_from_env() == "redis"
    monkeypatch.setenv("OMUR_SESSION_BACKEND", "garbage")
    with pytest.raises(ValueError):
        backend_from_env()


@pytest.mark.asyncio
async def test_new_store_postgres_requires_pool(monkeypatch):
    """
    Rules:   When OMUR_SESSION_BACKEND is set to 'postgres', the new_store function requires a valid pool argument; passing None will raise a ValueError.
    """
    monkeypatch.setenv("OMUR_SESSION_BACKEND", "postgres")
    with pytest.raises(ValueError):
        await new_store(pool=None)


@pytest.mark.asyncio
async def test_redis_store_put_get_delete():
    """
    Rules:   The TEST_REDIS_ADDR environment variable must be set for the test to run, otherwise it will be skipped. The Redis client must be properly configured with host, port, and optional password.
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
    store = RedisSessionStore(client, key_prefix="test:omur:session:")
    s = Session(
        token="rtest-py-1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        payload={"r": 1},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await store.put(s)
    got = await store.get("rtest-py-1")
    assert got.payload == {"r": 1}
    await store.delete("rtest-py-1")
    with pytest.raises(NotFound):
        await store.get("rtest-py-1")
    await store.close()
