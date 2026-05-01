"""packages/omur-sdk/tests/test_security_events.py — Tests for omur_sdk.security.events.log_security_event.

Integration tests (gated by TEST_POSTGRES_DSN) exercise the full
RLS tenant-isolation contract: rows inserted under tenant A are
invisible when the GUC is set to tenant B.

Unit tests exercise the happy-path call path with a mock pool so
they run without a live database.

exports: test_log_security_event_calls_pool_execute() | test_log_security_event_block_emits_warning(caplog) | test_log_security_event_no_warning_below_block(caplog) | test_log_security_event_facade_export() | test_rls_tenant_isolation()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from omur_sdk.security.events import log_security_event


# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_security_event_calls_pool_execute():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    tenant = uuid.uuid4()
    await log_security_event(
        pool=mock_pool,
        tenant_id=tenant,
        kind="sanitiser_pattern_hit",
        severity="warn",
        evidence={"pattern": "sql_injection_v1"},
        request_id="req-abc",
    )

    mock_conn.execute.assert_awaited_once()
    call_args = mock_conn.execute.await_args
    sql = call_args.args[0]
    assert "security_events" in sql
    assert call_args.args[1] == tenant


@pytest.mark.asyncio
async def test_log_security_event_block_emits_warning(caplog):
    import logging

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    tenant = uuid.uuid4()
    with caplog.at_level(logging.WARNING, logger="omur_sdk.security.events"):
        await log_security_event(
            pool=mock_pool,
            tenant_id=tenant,
            kind="classifier_malicious",
            severity="block",
        )

    assert any("security_event_block" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_security_event_no_warning_below_block(caplog):
    import logging

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with caplog.at_level(logging.WARNING, logger="omur_sdk.security.events"):
        await log_security_event(
            pool=mock_pool,
            tenant_id=uuid.uuid4(),
            kind="citation_invalid",
            severity="warn",
        )

    assert not any("security_event_block" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_security_event_facade_export():
    from omur_sdk.security import log_security_event as facade_fn
    from omur_sdk.security.events import log_security_event as direct_fn

    assert facade_fn is direct_fn


# ---------------------------------------------------------------------------
# Integration tests — require TEST_POSTGRES_DSN with superuser access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_tenant_isolation():
    """Rows inserted under tenant A must be invisible when GUC is tenant B."""
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")

    from omur_sdk.dbpool import create_pool

    pool = await create_pool(dsn, role=None)  # superuser for GUC control
    try:
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()

        async with pool.acquire() as conn:
            await conn.execute(
                "SET app.tenant_id = $1", str(tenant_a)
            )
            await conn.execute(
                """
                INSERT INTO security_events
                    (tenant_id, kind, severity, evidence)
                VALUES ($1, 'rls_test', 'info', '{}'::jsonb)
                """,
                tenant_a,
            )

            await conn.execute(
                "SET app.tenant_id = $1", str(tenant_b)
            )
            row = await conn.fetchrow(
                "SELECT count(*) AS cnt FROM security_events WHERE tenant_id = $1",
                tenant_a,
            )
            assert row["cnt"] == 0, (
                f"RLS isolation failed: tenant B sees {row['cnt']} rows from tenant A"
            )

            # Cleanup
            await conn.execute(
                "RESET app.tenant_id"
            )
            await conn.execute(
                "DELETE FROM security_events WHERE tenant_id = $1", tenant_a
            )
    finally:
        await pool.close()
