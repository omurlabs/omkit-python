"""packages/omur-sdk/tests/test_tenant.py — Tests for tenant context module.

exports: test_require_raises_when_unset() | test_current_or_none_returns_none_when_unset() | test_request_id_returns_none_when_unset() | test_bind_sets_and_resets_tenant() | test_bind_sets_and_resets_request_id() | test_bind_resets_on_exception() | test_middleware_sets_tenant_from_header() | test_middleware_returns_401_when_missing() | test_middleware_returns_401_for_invalid_uuid() | test_middleware_skips_excluded_paths() | test_middleware_resets_contextvar_after_request() | test_middleware_generates_request_id_when_absent() | test_middleware_adds_request_id_to_response_headers() | test_set_rls_executes_set_config() | test_set_rls_raises_outside_transaction() | test_set_rls_raises_without_tenant() | test_async_bind_sets_and_resets() | test_async_bind_resets_on_exception() | test_async_bind_nested() | test_set_rls_conn_runs_set_config() | (+7 more)
used_by: none
rules:   The module relies heavily on `contextvars` for tenant and request ID management, meaning all async and sync operations must properly propagate context to maintain correctness.  
Any changes to the tenant binding or middleware logic must ensure thread-safety and proper cleanup to prevent context leakage or interference between tests.  
The module assumes a PostgreSQL backend with RLS (Row Level Security) support, and all database-related tests depend on transactional integrity and proper session handling.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import pytest
from uuid import uuid4

from omur_sdk import tenant


def test_require_raises_when_unset():
    """require() must raise RuntimeError outside tenant context.

    Rules:   require() raises RuntimeError when no tenant is set, ensuring strict context enforcement.
    """
    with pytest.raises(RuntimeError, match="No tenant"):
        tenant.require()


def test_current_or_none_returns_none_when_unset():
    assert tenant.current_or_none() is None


def test_request_id_returns_none_when_unset():
    assert tenant.request_id() is None


def test_bind_sets_and_resets_tenant():
    """
    Rules:   The bind context manager ensures tenant is properly set and reset, even on exceptions.
    """
    tid = str(uuid4())
    assert tenant.current_or_none() is None
    with tenant.bind(tid):
        assert tenant.require() == tid
    assert tenant.current_or_none() is None


def test_bind_sets_and_resets_request_id():
    tid = str(uuid4())
    rid = str(uuid4())
    with tenant.bind(tid, request_id=rid):
        assert tenant.request_id() == rid
    assert tenant.request_id() is None


def test_bind_resets_on_exception():
    """
    Rules:   The bind context manager guarantees reset of tenant context even if an exception occurs inside the block.
    """
    tid = str(uuid4())
    with pytest.raises(ValueError):
        with tenant.bind(tid):
            assert tenant.require() == tid
            raise ValueError("boom")
    assert tenant.current_or_none() is None


import uuid
from unittest.mock import AsyncMock
from uuid import uuid4 as _uuid4_alias


@pytest.mark.asyncio
async def test_middleware_sets_tenant_from_header():
    """
    Rules:   The middleware extracts tenant ID from HTTP header and sets it in the context.
    """
    tid = str(_uuid4_alias())

    async def app(scope, receive, send):
        assert tenant.require() == tid

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": [
        (b"x-tenant-id", tid.encode()),
    ]}
    await wrapped(scope, AsyncMock(), AsyncMock())


@pytest.mark.asyncio
async def test_middleware_returns_401_when_missing():
    """
    Rules:   The middleware returns a 401 status if the required tenant header is missing.
    """
    responses = []

    async def capture_send(msg):
        responses.append(msg)

    async def app(scope, receive, send):
        pytest.fail("App should not be called")

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": []}
    await wrapped(scope, AsyncMock(), capture_send)

    assert responses[0]["status"] == 401


@pytest.mark.asyncio
async def test_middleware_returns_401_for_invalid_uuid():
    """
    Rules:   The middleware returns a 401 status if the tenant ID in the header is not a valid UUID.
    """
    responses = []

    async def capture_send(msg):
        responses.append(msg)

    async def app(scope, receive, send):
        pytest.fail("App should not be called")

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": [
        (b"x-tenant-id", b"not-a-uuid"),
    ]}
    await wrapped(scope, AsyncMock(), capture_send)

    assert responses[0]["status"] == 401


@pytest.mark.asyncio
async def test_middleware_skips_excluded_paths():
    """
    Rules:   The middleware skips tenant context setting for specified excluded paths.
    """
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True
        assert tenant.current_or_none() is None

    mw = tenant.middleware(exclude_paths={"/health"})
    wrapped = mw(app)

    scope = {"type": "http", "path": "/health", "headers": []}
    await wrapped(scope, AsyncMock(), AsyncMock())
    assert called


@pytest.mark.asyncio
async def test_middleware_resets_contextvar_after_request():
    """
    Rules:   The middleware ensures that the context variable is reset after each request completes.
    """
    tid = str(_uuid4_alias())

    async def app(scope, receive, send):
        assert tenant.require() == tid

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": [
        (b"x-tenant-id", tid.encode()),
    ]}
    await wrapped(scope, AsyncMock(), AsyncMock())

    # After middleware completes, contextvar should be reset
    assert tenant.current_or_none() is None


@pytest.mark.asyncio
async def test_middleware_generates_request_id_when_absent():
    """
    Rules:   The middleware automatically generates a request ID if one is not provided in the header.
    """
    tid = str(_uuid4_alias())
    captured_rid = None

    async def app(scope, receive, send):
        nonlocal captured_rid
        captured_rid = tenant.request_id()

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": [
        (b"x-tenant-id", tid.encode()),
    ]}
    await wrapped(scope, AsyncMock(), AsyncMock())

    assert captured_rid is not None
    uuid.UUID(captured_rid)  # validates it's a UUID


@pytest.mark.asyncio
async def test_middleware_adds_request_id_to_response_headers():
    tid = str(_uuid4_alias())
    responses = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def capture_send(msg):
        responses.append(msg)

    mw = tenant.middleware()
    wrapped = mw(app)

    scope = {"type": "http", "path": "/chat", "headers": [
        (b"x-tenant-id", tid.encode()),
    ]}
    await wrapped(scope, AsyncMock(), capture_send)

    start_msg = responses[0]
    header_names = [h[0] for h in start_msg["headers"]]
    assert b"x-request-id" in header_names


from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_set_rls_executes_set_config():
    """
    Rules:   Tenant must be bound before calling set_rls, and the session must be in an active transaction.
    """
    tid = str(uuid4())
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=True)

    with tenant.bind(tid):
        await tenant.set_rls(session)

    session.execute.assert_called_once()
    call_args = session.execute.call_args
    # First arg is the text() SQL
    assert "set_config" in str(call_args[0][0])
    # Second arg is the params dict
    assert call_args[0][1] == {"tid": tid}


@pytest.mark.asyncio
async def test_set_rls_raises_outside_transaction():
    """
    Rules:   Tenant must be bound and session must be in an active transaction to call set_rls.
    """
    tid = str(uuid4())
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=False)

    with tenant.bind(tid):
        with pytest.raises(RuntimeError, match="active transaction"):
            await tenant.set_rls(session)


@pytest.mark.asyncio
async def test_set_rls_raises_without_tenant():
    """
    Rules:   A tenant must be bound before calling set_rls.
    """
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=True)

    with pytest.raises(RuntimeError, match="No tenant"):
        await tenant.set_rls(session)


# ---------------------------------------------------------------------------
# async_bind, set_rls_conn, hashed_for_log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_bind_sets_and_resets():
    tid = str(uuid4())
    rid = str(uuid4())
    async with tenant.async_bind(tid, request_id=rid):
        assert tenant.require() == tid
        assert tenant.request_id() == rid
    assert tenant.current_or_none() is None
    assert tenant.request_id() is None


@pytest.mark.asyncio
async def test_async_bind_resets_on_exception():
    tid = str(uuid4())
    with pytest.raises(ValueError, match="boom"):
        async with tenant.async_bind(tid):
            assert tenant.require() == tid
            raise ValueError("boom")
    assert tenant.current_or_none() is None


@pytest.mark.asyncio
async def test_async_bind_nested():
    outer = str(uuid4())
    inner = str(uuid4())
    async with tenant.async_bind(outer):
        assert tenant.require() == outer
        async with tenant.async_bind(inner):
            assert tenant.require() == inner
        assert tenant.require() == outer
    assert tenant.current_or_none() is None


@pytest.mark.asyncio
async def test_set_rls_conn_runs_set_config():
    """
    Rules:   Tenant must be bound and connection must be in an active transaction to call set_rls_conn.
    """
    tid = str(uuid4())
    conn = MagicMock()
    conn.is_in_transaction = MagicMock(return_value=True)
    conn.execute = AsyncMock()

    async with tenant.async_bind(tid):
        await tenant.set_rls_conn(conn)

    conn.execute.assert_awaited_once_with(
        "SELECT set_config('app.tenant_id', $1, true)", tid
    )


@pytest.mark.asyncio
async def test_set_rls_conn_requires_transaction():
    """
    Rules:   Tenant must be bound and connection must be in an active transaction to call set_rls_conn.
    """
    tid = str(uuid4())
    conn = MagicMock()
    conn.is_in_transaction = MagicMock(return_value=False)
    conn.execute = AsyncMock()

    async with tenant.async_bind(tid):
        with pytest.raises(RuntimeError, match="active transaction"):
            await tenant.set_rls_conn(conn)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_rls_conn_requires_tenant():
    """
    Rules:   A tenant must be bound before calling set_rls_conn.
    """
    conn = MagicMock()
    conn.is_in_transaction = MagicMock(return_value=True)
    conn.execute = AsyncMock()

    with pytest.raises(RuntimeError, match="No tenant"):
        await tenant.set_rls_conn(conn)


def test_hashed_for_log_with_explicit_key():
    """
    Rules:   The HMAC key must be 32 bytes long for consistent hashing; using a different key length will produce different outputs.
    """
    tid = str(uuid4())
    h1 = tenant.hashed_for_log(tid, key=b"secret-bytes-key-1234567890abcdef")
    h2 = tenant.hashed_for_log(tid, key=b"secret-bytes-key-1234567890abcdef")
    h3 = tenant.hashed_for_log(tid, key=b"other-bytes-key-1234567890abcdef!")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


def test_hashed_for_log_reads_env_hex(monkeypatch):
    """
    Rules:   The environment variable OMUR_LOG_HMAC_KEY must be a 64-character hex string representing 32 bytes, or the function will raise an error on conversion.
    """
    tid = str(uuid4())
    # openssl rand -hex 32 produces 64-char hex string
    hex_key = "0123456789abcdef" * 4
    monkeypatch.setenv("OMUR_LOG_HMAC_KEY", hex_key)
    h_env = tenant.hashed_for_log(tid)
    h_explicit = tenant.hashed_for_log(tid, key=bytes.fromhex(hex_key))
    assert h_env == h_explicit


def test_hashed_for_log_rejects_non_hex_env(monkeypatch):
    """
    Rules:   Environment variable OMUR_LOG_HMAC_KEY must contain only valid hexadecimal characters. Invalid characters will raise a RuntimeError with 'hex string' in the message.
    """
    tid = str(uuid4())
    monkeypatch.setenv("OMUR_LOG_HMAC_KEY", "not-hex-zzz!")
    with pytest.raises(RuntimeError, match="hex string"):
        tenant.hashed_for_log(tid)


def test_hashed_for_log_rejects_short_env(monkeypatch):
    """
    Rules:   Environment variable OMUR_LOG_HMAC_KEY must be at least 16 hexadecimal characters long (8 bytes). Shorter values will raise a RuntimeError with 'too short' in the message.
    """
    tid = str(uuid4())
    # Only 8 hex chars = 4 bytes
    monkeypatch.setenv("OMUR_LOG_HMAC_KEY", "deadbeef")
    with pytest.raises(RuntimeError, match="too short"):
        tenant.hashed_for_log(tid)


def test_hashed_for_log_requires_key(monkeypatch):
    """
    Rules:   Environment variable OMUR_LOG_HMAC_KEY must be set. Missing environment variable will raise a RuntimeError with 'OMUR_LOG_HMAC_KEY' in the message.
    """
    tid = str(uuid4())
    monkeypatch.delenv("OMUR_LOG_HMAC_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OMUR_LOG_HMAC_KEY"):
        tenant.hashed_for_log(tid)
