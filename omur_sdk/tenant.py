"""Per-request tenant isolation via contextvars.

Middleware sets the tenant on each request. Handlers call require() to access.
Background tasks use bind() to establish context.
"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Callable

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

log = structlog.get_logger()

_tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def require() -> str:
    """Return current tenant ID or raise RuntimeError."""
    tid = _tenant_id_var.get()
    if tid is None:
        raise RuntimeError(
            "No tenant context set. Use tenant.middleware() in FastAPI "
            "or tenant.bind() for background tasks."
        )
    return tid


def current_or_none() -> str | None:
    """Return current tenant ID or None. For shared services where tenant is optional."""
    return _tenant_id_var.get()


def request_id() -> str | None:
    """Return current request ID or None."""
    return _request_id_var.get()


_DEFAULT_EXCLUDE = frozenset({"/health", "/ready", "/metrics"})


def _get_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    """Extract a header value from raw ASGI headers."""
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _validate_uuid(value: str) -> bool:
    """Check if value is a valid UUID (any version, case-insensitive)."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def middleware(
    exclude_paths: set[str] | None = None,
) -> Callable:
    """ASGI middleware factory for tenant extraction.

    Extracts X-Tenant-ID from request headers, validates as UUID, sets contextvar.
    Returns 401 for missing/invalid tenant on non-excluded paths.
    """
    excluded = frozenset(exclude_paths) if exclude_paths is not None else _DEFAULT_EXCLUDE

    def asgi_middleware(app):
        async def wrapped(scope, receive, send):
            if scope["type"] != "http":
                await app(scope, receive, send)
                return

            path = scope.get("path", "")
            if path in excluded:
                await app(scope, receive, send)
                return

            headers = scope.get("headers", [])
            raw_tid = _get_header(headers, b"x-tenant-id")

            if not raw_tid or not _validate_uuid(raw_tid):
                body = json.dumps({"error": "X-Tenant-ID header required"}).encode()
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return

            raw_rid = _get_header(headers, b"x-request-id") or str(uuid.uuid4())

            tid_token = _tenant_id_var.set(raw_tid)
            rid_token = _request_id_var.set(raw_rid)

            async def send_with_request_id(message):
                if message.get("type") == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", raw_rid.encode()))
                    message = {**message, "headers": headers}
                await send(message)

            try:
                await app(scope, receive, send_with_request_id)
            finally:
                _tenant_id_var.reset(tid_token)
                _request_id_var.reset(rid_token)

        return wrapped
    return asgi_middleware


async def set_rls(session: AsyncSession) -> None:
    """Set PostgreSQL RLS tenant context. Must be called inside an active transaction.

    Uses transaction-local set_config so the setting resets when the transaction ends.
    """
    if not session.in_transaction():
        raise RuntimeError(
            "set_rls() must be called inside an active transaction. "
            "Use 'async with session.begin():' before calling."
        )
    tid = require()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tid},
    )


def pool_reset_listener(engine: AsyncEngine) -> None:
    """Register pool event to clear tenant context on connection checkin.

    Defense-in-depth: ensures no tenant leakage even if a transaction
    aborts unexpectedly.
    """
    @event.listens_for(engine.sync_engine, "checkin")
    def _reset_tenant(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("RESET app.tenant_id")
        cursor.close()


@contextmanager
def bind(tenant_id: str, request_id: str | None = None):
    """Set tenant context for background tasks, scripts, and tests.

    Resets on exit, even if an exception is raised.
    """
    tid_token = _tenant_id_var.set(tenant_id)
    rid_token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _tenant_id_var.reset(tid_token)
        _request_id_var.reset(rid_token)
