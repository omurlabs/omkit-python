"""Per-request tenant isolation via contextvars.

Middleware sets the tenant on each request. Handlers call require() to access.
Background tasks use bind() to establish context.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from contextlib import contextmanager

import structlog

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
