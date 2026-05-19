"""omkit/security/events.py — write-side helpers for the security_events table.

Two entry points:

  * `write_security_event(pool, event)` — struct-style API mirroring Go's
    `security.WriteSecurityEvent`. Validates required fields up front and
    raises `ValueError` on missing tenant_id/kind/severity.
  * `log_security_event(*, pool, ...)` — kwargs-style API kept for back
    compat with existing call sites (cortex, spine).

Both go through the same INSERT, both honor RLS via the caller-supplied
pool. Severity == "block" emits a stdlib WARNING for tail-based ops.

Evidence must be structured metadata (pattern names, classifier verdicts,
stripped URLs). Never pass full document content — the column comment in
the migration is the canonical reminder.

exports: SecurityEvent | write_security_event | log_security_event
rules:   The security events module must maintain immutable evidence
         logging to ensure audit trail integrity. SecurityEvent is frozen;
         validation lives in write_security_event so both APIs stay in sync.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/security
message:
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityEvent:
    """One RAG security observation to be written to the security_events table.

    Mirrors Go's `security.SecurityEvent` field-for-field. Optional fields
    default to None so callers only set what they have. Evidence is any
    JSON-serializable value (dict, list, scalar); None is normalized to
    an empty object on write.

    Kind taxonomy:
      - "sanitiser_pattern_hit"   — input sanitiser matched a blocked pattern
      - "classifier_malicious"    — injection classifier returned malicious verdict
      - "output_filter_strip"     — output filter removed a URL or unsafe element
      - "doc_quarantined"         — document quarantined during ingest
      - "citation_invalid"        — citation validation failed at retrieval time
      - "rls_assert_failed"       — tenant RLS assertion mismatch detected

    Severity values: "info" | "warn" | "block"
    """

    tenant_id: UUID
    kind: str
    severity: str
    doc_id: UUID | None = None
    chunk_id: str | None = None
    evidence: Any = field(default=None)
    classifier_version: str | None = None
    request_id: str | None = None


async def write_security_event(
    pool: "asyncpg.Pool",
    event: SecurityEvent,
) -> None:
    """Persist a SecurityEvent. Validates required fields then INSERTs.

    Mirrors Go's `WriteSecurityEvent(ctx, pool, e)`. Caller is responsible
    for setting the `app.tenant_id` GUC on the pool/connection — this helper
    does not, so it composes inside caller-managed transactions.

    Raises:
        ValueError: pool is None, or tenant_id / kind / severity are empty.
    """
    if pool is None:
        raise ValueError("security: nil pool")
    if not event.tenant_id:
        raise ValueError("security: tenant_id required")
    if not event.kind:
        raise ValueError("security: kind required")
    if not event.severity:
        raise ValueError("security: severity required")

    await log_security_event(
        pool=pool,
        tenant_id=event.tenant_id,
        kind=event.kind,
        severity=event.severity,
        doc_id=event.doc_id,
        chunk_id=event.chunk_id,
        evidence=event.evidence if isinstance(event.evidence, dict) else (
            None if event.evidence is None else event.evidence
        ),
        classifier_version=event.classifier_version,
        request_id=event.request_id,
    )


async def log_security_event(
    *,
    pool: "asyncpg.Pool",
    tenant_id: UUID,
    kind: str,
    severity: str,
    doc_id: UUID | None = None,
    chunk_id: str | None = None,
    evidence: Any = None,
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
    if evidence is None:
        evidence_json = "{}"
    elif isinstance(evidence, (dict, list)):
        evidence_json = json.dumps(evidence)
    else:
        evidence_json = json.dumps(evidence)

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
