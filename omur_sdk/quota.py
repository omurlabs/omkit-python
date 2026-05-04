"""packages/omur-sdk/omur_sdk/quota.py — Per-tenant quota helpers (plan 1.7).

Mirrors ``packages/omur-go-sdk/quota/quota.go`` so marrow (Python) and
spine (Go) enforce identical defaults. Absence of a ``tenant_quotas`` row
means "use defaults below". Limits are integers; bytes are BIGINT.

exports: DEFAULT_DOCS | DEFAULT_STORAGE_BYTES | DEFAULT_QUERIES_PER_MONTH | class Resource | class Limits | class Usage | class Decision | load(session) | get_usage(session) | check_upload(lim, usage, incoming_bytes) | check_query(lim, usage)
rules:   The module must maintain backward compatibility with existing quota enforcement logic and cannot modify the public API of `load`, `get_usage`, `check_upload`, or `check_query` functions.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
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

    Rules:   The function assumes that `tenant.set_rls(session)` has already been called, and explicitly filters by `app.tenant_id` to prevent cross-tenant data leakage since `tenant_quotas` has no RLS policy.
    """
    # ``tenant_quotas`` intentionally has no RLS policy (operators need
    # cross-tenant visibility for capacity planning), so we filter by
    # the caller's app.tenant_id GUC explicitly. Without this WHERE the
    # helper would return an arbitrary row belonging to another tenant.
    row = (
        await session.execute(
            text(
                "SELECT docs_limit, storage_bytes_limit, queries_per_month_limit "
                "FROM tenant_quotas "
                "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid "
                "LIMIT 1"
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

    Services that don't hold SELECT on ``usage_log`` (e.g. marrow, which
    only enforces upload-side quotas) get ``queries_this_month=0`` from
    this helper — the upload-path checks never read that field, and the
    spine middleware that does enforce query quota will roll back and
    surface the real permission error instead.

    Rules:   The function requires the caller to have already set RLS on the session, and services without SELECT permission on `usage_log` will get `queries_this_month=0`, which may mask real permission errors in query enforcement.
    """
    doc_row = (
        await session.execute(
            text(
                "SELECT COUNT(*)::int, COALESCE(SUM(size_bytes), 0)::bigint "
                "FROM document_files"
            )
        )
    ).one()
    queries = 0
    nested = await session.begin_nested()
    try:
        queries = (
            await session.execute(
                text(
                    "SELECT COUNT(*)::int FROM usage_log "
                    "WHERE created_at >= date_trunc('month', now())"
                )
            )
        ).scalar() or 0
        await nested.commit()
    except Exception:
        # Permission denied / table missing: upload-side callers don't
        # need queries_this_month. Rolling back the savepoint keeps the
        # outer transaction usable so callers can still read `docs`.
        await nested.rollback()
    return Usage(
        docs=int(doc_row[0]),
        storage_bytes=int(doc_row[1]),
        queries_this_month=int(queries),
    )


def check_upload(lim: Limits, usage: Usage, incoming_bytes: int) -> Decision:
    """
    Rules:   The function does not validate that `incoming_bytes` is non-negative, which could lead to incorrect quota calculations if negative values are passed.
    """
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
    """
    Rules:   The function relies on `_seconds_until_next_month()` to calculate retry_after, which may not be accurate if the system clock is skewed or if the function is called outside of normal monthly boundaries.
    """
    if usage.queries_this_month + 1 > lim.queries_per_month:
        return Decision(
            allowed=False,
            resource=Resource.QUERIES_PER_MONTH,
            limit=lim.queries_per_month,
            used=usage.queries_this_month,
            retry_after=_seconds_until_next_month(),
        )
    return Decision(allowed=True)


def _cap_at_32_days(s: int) -> int:
    if s < 0:
        return 60
    if s > 32 * 24 * 3600:
        return 32 * 24 * 3600
    return s


def _seconds_until_next_month() -> int:
    now = datetime.now(timezone.utc)
    y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    nxt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
    return _cap_at_32_days(int((nxt - now).total_seconds()))
