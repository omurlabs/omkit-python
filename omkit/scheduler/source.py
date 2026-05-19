"""omkit/scheduler/source.py — PgxProviderSource (asyncpg-backed).

The reconcile loop reads the providers table cross-tenant. Callers should
pass a BYPASSRLS schema-owner pool because RLS would otherwise hide rows
the scheduler needs to see.

exports: PgxProviderSource
rules:   Query shape `SELECT tenant_id::text, name, config FROM providers
         WHERE kind = $1 AND enabled = TRUE` is part of the cross-SDK
         contract — coordinate with omkit-go before changing.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/scheduler
message:
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from omkit.scheduler.types import Provider

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger(__name__)


class PgxProviderSource:
    """Async ProviderSource backed by an asyncpg.Pool.

    Name kept as Pgx (rather than Asyncpg) for cross-SDK API symmetry with
    Go's `PgxProviderSource`.
    """

    def __init__(self, pool: "asyncpg.Pool"):
        self._pool = pool

    async def fetch_providers(self, kind: str) -> list[Provider]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tenant_id::text AS tenant_id, name, config "
                "FROM providers WHERE kind = $1 AND enabled = TRUE",
                kind,
            )
        out: list[Provider] = []
        for row in rows:
            raw = row["config"]
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            try:
                cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except (json.JSONDecodeError, TypeError):
                _log.warning(
                    "scheduler.config_unparseable tenant=%s name=%s",
                    row["tenant_id"],
                    row["name"],
                )
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            out.append(
                Provider(
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    config=cfg,
                )
            )
        return out
