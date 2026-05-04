"""packages/omur-sdk/omur_sdk/dbpool.py — asyncpg pool helper that enforces a Postgres role via the init coroutine.

Runs ``SET ROLE <role>`` on every new physical connection so the role is
guaranteed even across reconnects — the async equivalent of pgx's
``AfterConnect`` hook. This is the defence-in-depth mechanism we rely on
after removing PgBouncer (which previously took care of the role reset via
``server_reset_query``).

exports: sqlalchemy_asyncpg_connect_args(role) | new_session_pool(dsn) | create_pool(dsn)
rules:   The module must maintain backward compatibility with existing SQLAlchemy and asyncpg integration patterns, and all database connection handling must adhere to async/await semantics throughout.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import re
from typing import Any, Optional

import asyncpg


def sqlalchemy_asyncpg_connect_args(role: str | None = "omur_app") -> dict[str, Any]:
    """Return ``connect_args`` for ``create_async_engine(..., connect_args=...)``.

    Keeps the engine pgbouncer-transaction-mode-compatible
    (``statement_cache_size=0``, ``prepared_statement_cache_size=0``) and,
    when ``role`` is non-empty, applies ``SET ROLE <role>`` at connection
    startup via asyncpg's ``server_settings`` dict so every pool
    checkout already runs as the restricted role without any sync-event
    listener. Pass ``role=None`` to opt out.

    Running the role switch through ``server_settings`` (rather than a
    sync ``"connect"`` event listener that calls ``dbapi_conn.cursor()``)
    avoids a greenlet race between SQLAlchemy's async adapter and
    asyncpg's connection init — the listener would occasionally see a
    half-initialized DBAPI connection and raise ``'NoneType' object
    has no attribute 'cursor'`` / ``'commit'``. asyncpg issues
    ``SET name = value`` for every entry in ``server_settings`` during
    the connection handshake, before the connection is handed to the
    pool, so the role is always in place by the time SQLAlchemy sees
    the connection.

    Rules:   The function assumes that the `role` parameter is either a valid PostgreSQL role name or None. If a role is provided, it must exist in the database, and the calling user must have permission to switch to that role.
    """
    args: dict[str, Any] = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    if role:
        args["server_settings"] = {"role": role}
    return args


async def new_session_pool(dsn: str, **kwargs) -> asyncpg.Pool:
    """Build an asyncpg pool for :class:`omur_sdk.sessions.PostgresSessionStore`.

    The session pool intentionally does **not** run ``SET ROLE omur_app``
    on each new connection. Token-based session lookup (``get``/``delete``)
    takes an opaque token without knowing the tenant, so SELECT/DELETE
    under a role that's subject to the ``sessions_tenant_isolation`` RLS
    policy would silently return zero rows. Connecting as the default
    ``omur`` superuser (which has ``BYPASSRLS``) lets token lookup cross
    tenants; writes (``put``, ``list``) still run inside a transaction
    that sets ``app.tenant_id`` so RLS is honored for multi-tenant
    mutations.

    Use this helper in service lifespans that need a SessionStore. For
    pools that back RLS-enforced app queries, use :func:`create_pool`
    with ``role='omur_app'`` instead.

    Rules:   The function intentionally avoids setting a role on connections to allow cross-tenant session lookups. Future developers must understand that this design relies on the `omur` superuser having `BYPASSRLS` privileges to ensure proper behavior.
    """
    return await create_pool(dsn, **kwargs)


def _normalize_dsn(dsn: str) -> str:
    """Strip a SQLAlchemy dialect suffix like ``+asyncpg`` from the URL
    scheme so asyncpg accepts a DSN that was originally shaped for
    ``create_async_engine``."""
    return re.sub(r"^(postgres(?:ql)?)\+[a-z0-9_]+://", r"\1://", dsn, count=1)


async def create_pool(
    dsn: str,
    *,
    role: Optional[str] = None,
    min_size: int = 1,
    max_size: int = 10,
    **kwargs,
) -> asyncpg.Pool:
    """Create an asyncpg pool. If ``role`` is given, every new physical
    connection runs ``SET ROLE "<role>"`` via the init coroutine.

    ``statement_cache_size`` defaults to ``0`` so that pgbouncer in
    transaction mode can be reintroduced as a pure config change
    (prepared statements don't survive across pgbouncer's per-transaction
    server rotation). Callers can override by passing ``statement_cache_size``

    Rules:   If `role` is provided, it must be a valid PostgreSQL role name, and the calling user must have the necessary permissions to execute `SET ROLE <role>`. Additionally, `statement_cache_size` is defaulted to 0 for pgbouncer compatibility, but callers can override this if needed.
    explicitly."""

    async def _init(conn: asyncpg.Connection) -> None:
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    if role:
        kwargs.setdefault("init", _init)
    kwargs.setdefault("statement_cache_size", 0)

    return await asyncpg.create_pool(
        _normalize_dsn(dsn),
        min_size=min_size,
        max_size=max_size,
        **kwargs,
    )
