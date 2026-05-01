"""packages/omur-sdk/omur_sdk/security/events.py — write-side helper for the security_events table.

Evidence must be structured metadata (pattern names, classifier verdicts,
stripped URLs). Never pass full document content — the column comment in
the migration is the canonical reminder.

exports: log_security_event()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger(__name__)


async def log_security_event(
    *,
    pool: "asyncpg.Pool",
    tenant_id: UUID,
    kind: str,
    severity: str,
    doc_id: UUID | None = None,
    chunk_id: str | None = None,
    evidence: dict | None = None,
    classifier_version: str | None = None,
    request_id: str | None = None,
) -> None:
    """Insert one row into security_events under the caller-supplied pool.

    The pool must already be configured with SET ROLE omur_app (via
    dbpool.create_pool) so RLS enforcement is active. The caller is
    responsible for setting the app.tenant_id GUC in the same transaction
    when the pool uses the restricted role with RLS enabled.

    Logs to stderr via stdlib logging at WARNING level when severity=='block'
    so ops can tail stdout/stderr without a separate query.
    """
    evidence_json = json.dumps(evidence or {})

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO security_events
                (tenant_id, kind, severity, doc_id, chunk_id,
                 evidence, classifier_version, request_id)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            """,
            tenant_id,
            kind,
            severity,
            doc_id,
            chunk_id,
            evidence_json,
            classifier_version,
            request_id,
        )

    if severity == "block":
        _log.warning(
            "security_event_block",
            extra={
                "tenant_id": str(tenant_id),
                "kind": kind,
                "doc_id": str(doc_id) if doc_id else None,
                "request_id": request_id,
            },
        )
