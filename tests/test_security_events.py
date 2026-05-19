"""tests/test_security_events.py — Tests for omkit.security.events.log_security_event.

Integration tests (gated by TEST_POSTGRES_DSN) exercise the full
RLS tenant-isolation contract: rows inserted under tenant A are
invisible when the GUC is set to tenant B.

Unit tests exercise the happy-path call path with a mock pool so
they run without a live database.

exports: test_log_security_event_calls_pool_execute() | test_log_security_event_block_emits_warning(caplog) | test_log_security_event_no_warning_below_block(caplog) | test_log_security_event_facade_export() | test_rls_tenant_isolation()
rules:   The module must maintain strict separation between security event logging and database operations, with all database interactions routed through a dedicated connection pool. All security event logging must be synchronous to ensure proper ordering and prevent race conditions in event processing. The module cannot directly import or use any database-specific libraries outside of the established connection pool abstraction.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from omkit.security.events import (
    SecurityEvent,
    log_security_event,
    write_security_event,
)


# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_security_event_calls_pool_execute():
    """
    Rules:   The function assumes that the database connection's execute method is called exactly once, and that the call arguments are validated by the test. Future developers must ensure that the SQL query being executed is correctly formed and that the parameters passed (like tenant_id, kind, severity, etc.) are properly escaped or handled to prevent injection attacks.
    """
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
    """
    Rules:   When the severity is set to 'block', a warning must be emitted. Future developers must understand that this behavior is tied to the logging level and the specific logger name 'omkit.security.events'.
    """
    import logging

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    tenant = uuid.uuid4()
    with caplog.at_level(logging.WARNING, logger="omkit.security.events"):
        await log_security_event(
            pool=mock_pool,
            tenant_id=tenant,
            kind="classifier_malicious",
            severity="block",
        )

    assert any("security_event_block" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_security_event_no_warning_below_block(caplog):
    """
    Rules:   Warnings are only emitted for events with severity 'block' or higher. Future developers must know that lower severities like 'warn' do not trigger warnings in this context.
    """
    import logging

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with caplog.at_level(logging.WARNING, logger="omkit.security.events"):
        await log_security_event(
            pool=mock_pool,
            tenant_id=uuid.uuid4(),
            kind="citation_invalid",
            severity="warn",
        )

    assert not any("security_event_block" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_security_event_facade_export():
    """
    Rules:   The test assumes that the facade function and direct function are the same object, which means the security event logging module must maintain this specific API structure and not refactor the facade to be a separate implementation.
    """
    from omkit.security import log_security_event as facade_fn
    from omkit.security.events import log_security_event as direct_fn

    assert facade_fn is direct_fn


# ---------------------------------------------------------------------------
# SecurityEvent + write_security_event (Go parity)
# ---------------------------------------------------------------------------


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def test_security_event_is_frozen():
    ev = SecurityEvent(
        tenant_id=uuid.uuid4(),
        kind="sanitiser_pattern_hit",
        severity="warn",
    )
    with pytest.raises(Exception):
        ev.kind = "other"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_write_security_event_inserts_row():
    pool, conn = _mock_pool()
    tenant = uuid.uuid4()
    ev = SecurityEvent(
        tenant_id=tenant,
        kind="classifier_malicious",
        severity="block",
        evidence={"pattern": "x"},
        request_id="req-1",
    )
    await write_security_event(pool, ev)
    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args
    assert args[1] == tenant
    assert args[2] == "classifier_malicious"
    assert args[3] == "block"


@pytest.mark.asyncio
async def test_write_security_event_rejects_nil_pool():
    ev = SecurityEvent(tenant_id=uuid.uuid4(), kind="k", severity="info")
    with pytest.raises(ValueError, match="nil pool"):
        await write_security_event(None, ev)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_security_event_rejects_empty_kind():
    pool, _ = _mock_pool()
    ev = SecurityEvent(tenant_id=uuid.uuid4(), kind="", severity="info")
    with pytest.raises(ValueError, match="kind required"):
        await write_security_event(pool, ev)


@pytest.mark.asyncio
async def test_write_security_event_rejects_empty_severity():
    pool, _ = _mock_pool()
    ev = SecurityEvent(tenant_id=uuid.uuid4(), kind="k", severity="")
    with pytest.raises(ValueError, match="severity required"):
        await write_security_event(pool, ev)


@pytest.mark.asyncio
async def test_write_security_event_facade_export():
    from omkit.security import SecurityEvent as facade_se
    from omkit.security import write_security_event as facade_fn

    assert facade_se is SecurityEvent
    assert facade_fn is write_security_event


# ---------------------------------------------------------------------------
# Integration tests — require TEST_POSTGRES_DSN with superuser access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_tenant_isolation():
    """Rows inserted under tenant A must be invisible when GUC is tenant B.

    Rules:   The test requires a valid TEST_POSTGRES_DSN environment variable to run. Future developers must be aware that this test will be skipped if the environment variable is not set, and that it depends on PostgreSQL's Row Level Security (RLS) and GUC settings for proper tenant isolation.
    """
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")

    from omkit.dbpool import create_pool

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
