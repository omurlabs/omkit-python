"""omkit/auth/audit.py — write-side helper for the admin_audit_log table.

Mirrors omkit-go/auth/audit.go. Caller pre-extracts the actor/request fields
from whatever HTTP framework they use (FastAPI, Starlette, raw ASGI) and
passes them in — this helper has no framework dependency.

Schema (mirrored from spine migration `admin_audit_log_*.sql`):

    CREATE TABLE admin_audit_log (
        id            BIGSERIAL PRIMARY KEY,
        ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
        actor_uid     TEXT NOT NULL,
        actor_email   TEXT,
        actor_groups  TEXT,
        role          TEXT NOT NULL CHECK (role IN ('admin','support','user')),
        action        TEXT NOT NULL,
        target_kind   TEXT,
        target_id     TEXT,
        diff          JSONB,
        request_id    TEXT,
        ip            TEXT,
        user_agent    TEXT
    );

SECURITY — Diff handling (caller discipline, no automated enforcement):

  * Diff is None for reads, `{"before": ..., "after": ...}` for mutations.
  * NEVER include decrypted secrets, raw API keys, encryption material, PHI,
    plaintext credentials, or any sensitive value. Use masked forms only
    (e.g. `{"masked_key": "sk-***abc"}` — matches api_keys handler).
  * There is no type-level guard.

exports: AuditEntry | write_audit_entry
rules:   Validation: action and role are required. Diff is marshalled to a
         JSON STRING (not bytes) so it round-trips through PgBouncer's
         simple-protocol mode without being mis-encoded as bytea.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/auth
message:
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from omkit.auth.roles import Role

if TYPE_CHECKING:
    import asyncpg


@dataclass(frozen=True)
class AuditEntry:
    """One admin action to be written to admin_audit_log.

    Mirrors Go's `auth.AuditEntry`. `diff` is opaque JSON; None omits the
    column (NULL).
    """

    role: Role
    action: str
    target_kind: str = ""
    target_id: str = ""
    diff: Any = None


async def write_audit_entry(
    pool: "asyncpg.Pool",
    entry: AuditEntry,
    *,
    actor_uid: str = "",
    actor_email: str | None = None,
    actor_groups: str | None = None,
    request_id: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Persist an audit row. Synchronous to the handler — call after the
    underlying mutation succeeds.

    Caller pre-extracts the actor/request metadata:

      * actor_uid    ← X-Auth-Request-User header (defaults to "service")
      * actor_email  ← X-Auth-Request-Email header
      * actor_groups ← X-Auth-Request-Groups header (raw, pipe-separated)
      * request_id   ← OTel trace ID (16-byte hex) or upstream X-Request-ID
      * client_ip    ← first hop of X-Forwarded-For, or RemoteAddr
      * user_agent   ← User-Agent header

    Raises:
        ValueError: pool is None, or action / role are empty.
    """
    if pool is None:
        raise ValueError("audit: nil pool")
    if not entry.action:
        raise ValueError("audit: action required")
    if not entry.role:
        raise ValueError("audit: role required")

    uid = actor_uid or "service"

    diff_param: str | None
    if entry.diff is None:
        diff_param = None
    else:
        diff_param = json.dumps(entry.diff)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO admin_audit_log
                (actor_uid, actor_email, actor_groups, role, action,
                 target_kind, target_id, diff, request_id, ip, user_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11)
            """,
            uid,
            actor_email or None,
            actor_groups or None,
            entry.role.value,
            entry.action,
            entry.target_kind or None,
            entry.target_id or None,
            diff_param,
            request_id or None,
            client_ip or None,
            user_agent or None,
        )
