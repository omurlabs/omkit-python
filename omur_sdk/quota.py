"""Per-tenant quota helpers (plan 1.7).

Mirrors ``packages/omur-go-sdk/quota/quota.go`` so marrow (Python) and
spine (Go) enforce identical defaults. Absence of a ``tenant_quotas`` row
means "use defaults below". Limits are integers; bytes are BIGINT.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_DOCS = 100
DEFAULT_STORAGE_BYTES = 500 * 1024 * 1024  # 500 MiB
DEFAULT_QUERIES_PER_MONTH = 1000


class Resource(str, enum.Enum):
    DOCS = "docs"
    STORAGE_BYTES = "storage_bytes"
    QUERIES_PER_MONTH = "queries_per_month"


@dataclass(frozen=True)
class Limits:
    docs: int
    storage_bytes: int
    queries_per_month: int


@dataclass(frozen=True)
class Usage:
    docs: int
    storage_bytes: int
    queries_this_month: int


@dataclass(frozen=True)
class Decision:
    allowed: bool
    resource: Resource | None = None
    limit: int = 0
    used: int = 0
    retry_after: int = 0  # seconds; 0 means "no retry will help"


async def load(session: AsyncSession) -> Limits:
    """Read the caller's effective limits under the session's RLS role.

    The caller is expected to have already invoked ``tenant.set_rls(session)``.
    Falls back to defaults when no row exists for the tenant.
    """
    row = (
        await session.execute(
            text(
                "SELECT docs_limit, storage_bytes_limit, queries_per_month_limit "
                "FROM tenant_quotas LIMIT 1"
            )
        )
    ).first()
    if row is None:
        return Limits(
            docs=DEFAULT_DOCS,
            storage_bytes=DEFAULT_STORAGE_BYTES,
            queries_per_month=DEFAULT_QUERIES_PER_MONTH,
        )
    return Limits(
        docs=int(row[0]),
        storage_bytes=int(row[1]),
        queries_per_month=int(row[2]),
    )


async def get_usage(session: AsyncSession) -> Usage:
    """Read docs / storage_bytes / queries-this-month for the request tenant.

    Caller must have already set RLS on the session.
    """
    doc_row = (
        await session.execute(
            text(
                "SELECT COUNT(*)::int, COALESCE(SUM(size_bytes), 0)::bigint "
                "FROM document_files"
            )
        )
    ).one()
    queries = (
        await session.execute(
            text(
                "SELECT COUNT(*)::int FROM usage_log "
                "WHERE created_at >= date_trunc('month', now())"
            )
        )
    ).scalar() or 0
    return Usage(
        docs=int(doc_row[0]),
        storage_bytes=int(doc_row[1]),
        queries_this_month=int(queries),
    )


def check_upload(lim: Limits, usage: Usage, incoming_bytes: int) -> Decision:
    if usage.docs + 1 > lim.docs:
        return Decision(
            allowed=False,
            resource=Resource.DOCS,
            limit=lim.docs,
            used=usage.docs,
            retry_after=0,
        )
    if usage.storage_bytes + incoming_bytes > lim.storage_bytes:
        return Decision(
            allowed=False,
            resource=Resource.STORAGE_BYTES,
            limit=lim.storage_bytes,
            used=usage.storage_bytes,
            retry_after=0,
        )
    return Decision(allowed=True)


def check_query(lim: Limits, usage: Usage) -> Decision:
    if usage.queries_this_month + 1 > lim.queries_per_month:
        return Decision(
            allowed=False,
            resource=Resource.QUERIES_PER_MONTH,
            limit=lim.queries_per_month,
            used=usage.queries_this_month,
            retry_after=_seconds_until_next_month(),
        )
    return Decision(allowed=True)


def _seconds_until_next_month() -> int:
    now = datetime.now(timezone.utc)
    y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    nxt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
    return int((nxt - now).total_seconds())
