"""packages/omur-sdk/tests/test_settings_polling.py — test_settings_polling module.

exports: pool() | test_polling_picks_up_updates(pool, monkeypatch)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import asyncio
import os
import uuid

import asyncpg
import pytest

from omur_sdk.settings import SettingsManager


@pytest.fixture
async def pool():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    p = await asyncpg.create_pool(dsn)
    yield p
    await p.close()


@pytest.mark.asyncio
async def test_polling_picks_up_updates(pool, monkeypatch):
    monkeypatch.setenv("OMUR_SETTINGS_BACKEND", "postgres")
    key = f"test_polling_{uuid.uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM app_settings WHERE key = $1", key)

    mgr = SettingsManager(
        pool=pool,
        tenant_id="00000000-0000-0000-0000-000000000099",
        poll_interval=0.1,
    )
    await mgr.start()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO app_settings
                    (key, value_json, value_type, category, label)
                VALUES ($1, '"polling_value"'::jsonb, 'string', 'test', 'polling test')
                ON CONFLICT (key) DO UPDATE SET
                    value_json = EXCLUDED.value_json, updated_at = now()
                """,
                key,
            )
        for _ in range(20):
            await asyncio.sleep(0.1)
            if mgr.get(key) == "polling_value":
                return
        assert mgr.get(key) == "polling_value", (
            f"polling did not propagate; cache={mgr.get(key)!r}"
        )
    finally:
        await mgr.stop()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM app_settings WHERE key = $1", key)
