"""omkit/tenant.py — Per-request tenant isolation via contextvars.

Middleware sets the tenant on each request. Handlers call require() to access.
Background tasks use bind() to establish context.

exports: require() | current_or_none() | request_id() | _DEFAULT_EXCLUDE | class TenantMiddleware | middleware(exclude_paths) | set_rls(session) | set_rls_conn(conn) | bind(tenant_id, request_id) | async_bind(tenant_id, request_id) | hashed_for_log(tenant_id, key)
rules:   The tenant middleware must be applied before any database operations to ensure RLS policies are properly set, and all tenant context must be bound to the current request scope to maintain isolation between concurrent requests.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, AsyncIterator, Callable

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()

_tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def require() -> str:
    """Return current tenant ID or raise RuntimeError.

    Rules:   Tenant context must be set before calling this function, otherwise a RuntimeError is raised. Used in FastAPI middleware or background tasks via bind().
    """
    tid = _tenant_id_var.get()
    if tid is None:
        raise RuntimeError(
            "No tenant context set. Use tenant.middleware() in FastAPI "
            "or tenant.bind() for background tasks."
        )
    return tid


def current_or_none() -> str | None:
    """Return current tenant ID or None. For shared services where tenant is optional.

    Rules:   Returns None if no tenant context is set; intended for optional tenant scenarios like shared services.
    """
    return _tenant_id_var.get()


def request_id() -> str | None:
    """Return current request ID or None.

    Rules:   Returns None if no request ID is set; used for tracking requests across services.
    """
    return _request_id_var.get()


_DEFAULT_EXCLUDE = frozenset({"/health", "/healthz", "/ready", "/readyz", "/metrics"})


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


class TenantMiddleware:
    """Pure ASGI middleware for tenant extraction.

    Usage with FastAPI:
        app.add_middleware(TenantMiddleware)
        app.add_middleware(TenantMiddleware, exclude_paths={"/health", "/custom"})
    """

    def __init__(self, app, exclude_paths: set[str] | None = None) -> None:
        self.app = app
        self.excluded = frozenset(exclude_paths) if exclude_paths is not None else _DEFAULT_EXCLUDE

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.excluded:
            await self.app(scope, receive, send)
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
                resp_headers = list(message.get("headers", []))
                resp_headers.append((b"x-request-id", raw_rid.encode()))
                message = {**message, "headers": resp_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _tenant_id_var.reset(tid_token)
            _request_id_var.reset(rid_token)


def middleware(exclude_paths: set[str] | None = None) -> Callable:
    """ASGI middleware factory. Prefer TenantMiddleware class with app.add_middleware().

    This factory form works for raw ASGI wrapping (tests).
    For FastAPI, use: app.add_middleware(TenantMiddleware)

    Rules:   This function returns a factory for ASGI middleware; prefer using TenantMiddleware class directly with app.add_middleware() for FastAPI apps.
    """
    excluded = exclude_paths

    def asgi_middleware(app):
        mw = TenantMiddleware(app, exclude_paths=excluded)
        return mw

    return asgi_middleware


async def set_rls(session) -> None:
    """Set PostgreSQL RLS tenant context. Must be called inside an active transaction.

    Uses transaction-local set_config so the setting resets when the transaction ends.
    Requires sqlalchemy (optional dependency).

    Rules:   Must be called inside an active SQLAlchemy transaction; otherwise raises RuntimeError. Sets PostgreSQL RLS context using set_config within the transaction.
    """
    from sqlalchemy import text

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


async def set_rls_conn(conn: "asyncpg.Connection") -> None:
    """Set PostgreSQL RLS tenant context on an asyncpg connection.

    Asyncpg counterpart of set_rls(). Reads tenant from ContextVar (require()).
    Must be called inside an active transaction — set_config(..., true) is
    transaction-local; outside a transaction the setting silently leaks across
    pooled checkouts (cross-tenant data leak risk).

    Rules:   Must be called inside an active asyncpg transaction; otherwise raises RuntimeError. Sets PostgreSQL RLS context using set_config within the transaction to prevent cross-tenant data leaks.
    """
    if not conn.is_in_transaction():
        raise RuntimeError(
            "set_rls_conn() must be called inside an active transaction. "
            "Use 'async with conn.transaction():' before calling."
        )
    tid = require()
    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tid)


@contextmanager
def bind(tenant_id: str, request_id: str | None = None):
    """Set tenant context for background tasks, scripts, and tests.

    Resets on exit, even if an exception is raised.

    Rules:   Sets tenant and request ID in ContextVars for background tasks, scripts, or tests; resets values on exit even if an exception occurs.
    """
    tid_token = _tenant_id_var.set(tenant_id)
    rid_token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _tenant_id_var.reset(tid_token)
        _request_id_var.reset(rid_token)


@asynccontextmanager
async def async_bind(
    tenant_id: str, request_id: str | None = None
) -> AsyncIterator[None]:
    """Async counterpart of bind() for use inside `async with` blocks.

    ContextVar set/reset itself is sync; this is a convenience wrapper so
    job-queue middleware and other async code can write `async with
    tenant.async_bind(tid):` without a `with` inside `async def`.

    Rules:   Async version of bind(); used in async contexts with `async with tenant.async_bind(tid):` to manage tenant context.
    """
    tid_token = _tenant_id_var.set(tenant_id)
    rid_token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _tenant_id_var.reset(tid_token)
        _request_id_var.reset(rid_token)


def hashed_for_log(tenant_id: str, key: bytes | None = None) -> str:
    """HMAC-SHA-256 of tenant_id for log/metric correlation without re-id risk.

    Plain SHA-256 over a finite tenant population is brute-forceable; HMAC with
    a per-deployment secret is not. Reads LOG_HMAC_KEY from env when key
    not supplied. Returns first 16 hex chars (8 bytes) — enough entropy for
    correlation, short enough for log lines.

    Key encoding contract: LOG_HMAC_KEY must be a hex string (output of
    `openssl rand -hex 32`). hashed_for_log decodes it to raw bytes before
    HMAC, so the full 256 bits of entropy are used. A bare ASCII passphrase
    will silently work but only at ~5 bits/char effective key strength.

    Rules:   Requires LOG_HMAC_KEY environment variable to be set as a hex-encoded 32-byte key; returns first 16 hex chars of HMAC-SHA-256 for log correlation.
    """
    if key is None:
        env = os.environ.get("LOG_HMAC_KEY")
        if not env:
            raise RuntimeError(
                "LOG_HMAC_KEY env var required for tenant log hashing. "
                "Set in BaseServiceSettings or pass key= explicitly."
            )
        try:
            key = bytes.fromhex(env)
        except ValueError as exc:
            raise RuntimeError(
                "LOG_HMAC_KEY must be a hex string (openssl rand -hex 32). "
                f"Got {len(env)} chars, decode error: {exc}"
            ) from exc
        if len(key) < 16:
            raise RuntimeError(
                f"LOG_HMAC_KEY too short ({len(key)} bytes); need >= 16"
            )
    digest = hmac.new(key, tenant_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]
