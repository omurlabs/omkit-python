"""tests/test_dbpool.py — test_dbpool module.

exports: test_sqlalchemy_connect_args_disables_prepared_statements() | test_role_set_on_acquire() | test_role_set_after_txn_error() | test_no_role_leaves_pool_behaviour_unchanged()
rules:   The module requires all database connection tests to validate against environment-based DSN settings and must maintain consistent role assignment behavior across transaction states.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import os

import pytest

from omkit.dbpool import create_pool, sqlalchemy_asyncpg_connect_args


def test_sqlalchemy_connect_args_disables_prepared_statements():
    """
    Rules:   The function assumes that sqlalchemy_asyncpg_connect_args() will always return a dictionary with 'statement_cache_size' and 'prepared_statement_cache_size' keys, and that these will be set to 0. Future developers must ensure this behavior is maintained if the function is modified.
    """
    args = sqlalchemy_asyncpg_connect_args()
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0


@pytest.mark.asyncio
async def test_role_set_on_acquire():
    """
    Rules:   The test assumes that setting a role in the pool configuration will result in the current_user being set to that role for subsequent database connections. Future developers must ensure the role-setting logic in create_pool is correctly implemented and that the test environment supports role switching.
    """
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
    """
    Rules:   The test assumes that even after a transaction error, the pool will maintain the role setting for subsequent connections. Future developers must ensure that connection state is properly reset or preserved after transaction errors.
    """
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
    """
    Rules:   The test assumes that when no role is specified, the default PostgreSQL user ('omur') will be used. Future developers must verify that the default user is correctly set in the test environment and that the create_pool function does not alter default behavior when no role is specified.
    """
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
