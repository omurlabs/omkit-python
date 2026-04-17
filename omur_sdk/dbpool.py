"""asyncpg pool helper that enforces a Postgres role via the init coroutine.

Runs ``SET ROLE <role>`` on every new physical connection so the role is
guaranteed even across reconnects — the async equivalent of pgx's
``AfterConnect`` hook. This is the defence-in-depth mechanism we rely on
after removing PgBouncer (which previously took care of the role reset via
``server_reset_query``).
"""

from __future__ import annotations

import re
from typing import Optional

import asyncpg


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
    connection runs ``SET ROLE "<role>"`` via the init coroutine."""

    async def _init(conn: asyncpg.Connection) -> None:
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    if role:
        kwargs.setdefault("init", _init)

    return await asyncpg.create_pool(
        _normalize_dsn(dsn),
        min_size=min_size,
        max_size=max_size,
        **kwargs,
    )
