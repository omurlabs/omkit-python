"""asyncpg pool helper that enforces a Postgres role via the init coroutine.

Runs ``SET ROLE <role>`` on every new physical connection so the role is
guaranteed even across reconnects — the async equivalent of pgx's
``AfterConnect`` hook. This is the defence-in-depth mechanism we rely on
after removing PgBouncer (which previously took care of the role reset via
``server_reset_query``).
"""

from __future__ import annotations

import re
from typing import Any, Optional

import asyncpg


def sqlalchemy_asyncpg_connect_args() -> dict[str, Any]:
    """Return ``connect_args`` for ``create_async_engine(..., connect_args=...)``
    that keep the resulting engine compatible with pgbouncer transaction mode.

    Disables asyncpg's statement cache (prepared statements don't survive
    pgbouncer's per-transaction server rotation) while leaving extended
    query protocol + binary params intact. Harmless when talking to
    postgres directly — the only cost is a few percent of single-query
    throughput."""
    return {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }


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
