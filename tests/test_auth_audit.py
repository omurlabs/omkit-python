"""tests/test_auth_audit.py — Tests for omkit.auth.audit.

Unit tests use a mock pool so they run without a live database.

exports: test_*
rules:   diff is marshalled to a JSON STRING (not bytes) — pinning that here
         catches a PgBouncer simple-protocol regression early.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/auth
message:
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from omkit.auth import AuditEntry, Role, write_audit_entry


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def test_audit_entry_is_frozen():
    e = AuditEntry(role=Role.ADMIN, action="system_key.put")
    with pytest.raises(Exception):
        e.action = "other"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_write_audit_entry_inserts_row():
    pool, conn = _mock_pool()
    entry = AuditEntry(
        role=Role.ADMIN,
        action="system_key.put",
        target_kind="provider",
        target_id="anthropic",
        diff={"masked_key": "sk-***abc"},
    )
    await write_audit_entry(
        pool,
        entry,
        actor_uid="user-1",
        actor_email="u@example.com",
        request_id="req-1",
        client_ip="1.2.3.4",
        user_agent="curl/8",
    )
    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args
    assert args[1] == "user-1"  # actor_uid
    assert args[2] == "u@example.com"  # actor_email
    assert args[4] == "admin"  # role .value
    assert args[5] == "system_key.put"  # action
    assert args[6] == "provider"  # target_kind
    assert args[7] == "anthropic"  # target_id
    # diff is JSON string, not bytes (PgBouncer simple-protocol contract)
    assert isinstance(args[8], str)
    assert "masked_key" in args[8]


@pytest.mark.asyncio
async def test_write_audit_entry_actor_defaults_to_service():
    pool, conn = _mock_pool()
    entry = AuditEntry(role=Role.SUPPORT, action="settings.read")
    await write_audit_entry(pool, entry)
    args = conn.execute.await_args.args
    assert args[1] == "service"


@pytest.mark.asyncio
async def test_write_audit_entry_diff_none_yields_null():
    pool, conn = _mock_pool()
    entry = AuditEntry(role=Role.USER, action="login")
    await write_audit_entry(pool, entry)
    args = conn.execute.await_args.args
    assert args[8] is None  # diff


@pytest.mark.asyncio
async def test_write_audit_entry_empty_optional_fields_become_null():
    pool, conn = _mock_pool()
    entry = AuditEntry(role=Role.ADMIN, action="x")
    await write_audit_entry(pool, entry)
    args = conn.execute.await_args.args
    # target_kind, target_id, request_id, ip, user_agent → None
    assert args[6] is None
    assert args[7] is None
    assert args[9] is None
    assert args[10] is None
    assert args[11] is None


@pytest.mark.asyncio
async def test_write_audit_entry_rejects_nil_pool():
    entry = AuditEntry(role=Role.ADMIN, action="x")
    with pytest.raises(ValueError, match="nil pool"):
        await write_audit_entry(None, entry)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_audit_entry_rejects_empty_action():
    pool, _ = _mock_pool()
    entry = AuditEntry(role=Role.ADMIN, action="")
    with pytest.raises(ValueError, match="action required"):
        await write_audit_entry(pool, entry)
