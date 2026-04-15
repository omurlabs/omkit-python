"""Tests for tenant context module."""

import pytest
from uuid import uuid4

from omur_sdk import tenant


def test_require_raises_when_unset():
    """require() must raise RuntimeError outside tenant context."""
    with pytest.raises(RuntimeError, match="No tenant"):
        tenant.require()


def test_current_or_none_returns_none_when_unset():
    assert tenant.current_or_none() is None


def test_request_id_returns_none_when_unset():
    assert tenant.request_id() is None


def test_bind_sets_and_resets_tenant():
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
