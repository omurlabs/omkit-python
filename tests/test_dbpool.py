"""packages/omur-sdk/tests/test_dbpool.py — test_dbpool module.

exports: test_sqlalchemy_connect_args_disables_prepared_statements() | test_role_set_on_acquire() | test_role_set_after_txn_error() | test_no_role_leaves_pool_behaviour_unchanged()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import os

import pytest

from omur_sdk.dbpool import create_pool, sqlalchemy_asyncpg_connect_args


def test_sqlalchemy_connect_args_disables_prepared_statements():
    args = sqlalchemy_asyncpg_connect_args()
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0


@pytest.mark.asyncio
async def test_role_set_on_acquire():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    pool = await create_pool(dsn, role="omur_app", min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT current_user")
            assert row["current_user"] == "omur_app"
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_role_set_after_txn_error():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    pool = await create_pool(dsn, role="omur_app", min_size=1, max_size=1)
    try:
        with pytest.raises(Exception):
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT 1/0")
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT current_user")
            assert row["current_user"] == "omur_app"
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_no_role_leaves_pool_behaviour_unchanged():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    pool = await create_pool(dsn, min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT current_user")
            assert row["current_user"] == "omur"
    finally:
        await pool.close()
