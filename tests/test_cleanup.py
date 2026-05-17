"""packages/omur-sdk/tests/test_cleanup.py — test_cleanup module.

exports: test_loop_runs_task_when_lock_acquired() | test_loop_skips_when_lock_held_elsewhere()
rules:   none
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import asyncio
import os

import asyncpg
import pytest

from omkit.cleanup import Loop


@pytest.mark.asyncio
async def test_loop_runs_task_when_lock_acquired():
    """
    Rules:   Loop requires PostgreSQL connection via TEST_POSTGRES_DSN environment variable and uses advisory locking with key 9991 to ensure only one instance runs the task concurrently.
    """
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        ran = asyncio.Event()

        async def task():
            ran.set()

        loop = Loop(pool, lock_key=9991, interval=0.05, task=task, name="test")
        runner = asyncio.create_task(loop.run())
        try:
            await asyncio.wait_for(ran.wait(), timeout=1.0)
        finally:
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_loop_skips_when_lock_held_elsewhere():
    """
    Rules:   Loop requires PostgreSQL connection via TEST_POSTGRES_DSN environment variable and uses advisory locking with key 8881; if another connection holds this lock via pg_advisory_lock, the loop will skip execution.
    """
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    holder = await asyncpg.connect(dsn)
    try:
        await holder.execute("SELECT pg_advisory_lock(8881)")
        ran = asyncio.Event()

        async def task():
            ran.set()

        loop = Loop(pool, lock_key=8881, interval=0.05, task=task)
        runner = asyncio.create_task(loop.run())
        try:
            await asyncio.wait_for(ran.wait(), timeout=0.3)
            pytest.fail("task ran despite contention")
        except asyncio.TimeoutError:
            pass
        finally:
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass
    finally:
        try:
            await holder.execute("SELECT pg_advisory_unlock(8881)")
        finally:
            await holder.close()
        await pool.close()
