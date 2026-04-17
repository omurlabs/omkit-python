"""Session store abstractions for services that persist short-lived per-user
sessions. Two backends are provided:

- ``PostgresSessionStore`` (default) — stores sessions in the ``sessions``
  table and lets Postgres expire them.
- ``RedisSessionStore`` — opt-in via ``OMUR_SESSION_BACKEND=redis``; wraps
  ``redis.asyncio`` for legacy/low-latency deployments.

The ``Session`` dataclass is the wire shape exchanged between Store
implementations and callers.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


class NotFound(Exception):
    """Raised when a Session lookup returns no (non-expired) row."""


@dataclass
class Session:
    token: str
    tenant_id: str
    payload: dict[str, Any]
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionStore(Protocol):
    async def get(self, token: str, *, tenant_id: str | None = None) -> Session: ...
    async def put(self, session: Session) -> None: ...
    async def delete(self, token: str, *, tenant_id: str | None = None) -> None: ...
    async def list(self, tenant_id: str) -> list[Session]: ...
    async def close(self) -> None: ...


def _parse_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


class PostgresSessionStore:
    """Store backed by an asyncpg pool and the ``sessions`` table.

    Contract with respect to Postgres RLS (``sessions_tenant_isolation``
    policy):

    - ``put(session)`` and ``list(tenant_id)`` always work because the
      tenant is known; both run inside a transaction that sets
      ``app.tenant_id`` so the policy is satisfied under any role.
    - ``get(token)`` and ``delete(token)`` accept the opaque token as
      the capability. If the pool has ``SET ROLE omur_app`` applied, RLS
      will filter the SELECT/DELETE to zero rows. Build the session
      pool with :func:`new_session_pool` (no ``SET ROLE``; superuser
      bypasses RLS) so token lookup crosses tenants.

    Defense-in-depth: callers that already know the expected tenant may
    pass ``tenant_id=`` to ``get``/``delete``; the store will then
    verify/scope the operation in-Python so a stolen token can't be used
    against a different tenant's row.
    """

    def __init__(self, pool):
        self._pool = pool

    async def get(self, token: str, *, tenant_id: str | None = None) -> Session:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT token, tenant_id::text, payload, created_at, expires_at "
                "FROM sessions WHERE token = $1 AND expires_at > now()",
                token,
            )
        if not row:
            raise NotFound(token)
        if tenant_id is not None and row["tenant_id"] != tenant_id:
            # Token belongs to a different tenant — treat as missing.
            raise NotFound(token)
        return Session(
            token=row["token"],
            tenant_id=row["tenant_id"],
            payload=_parse_payload(row["payload"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    async def put(self, s: Session) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Satisfy the sessions_tenant_isolation RLS policy
                # regardless of whether the pool runs as omur_app or a
                # BYPASSRLS superuser. set_config(..., true) is
                # transaction-local so it doesn't leak across checkouts.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    s.tenant_id,
                )
                await conn.execute(
                    "INSERT INTO sessions (token, tenant_id, payload, expires_at) "
                    "VALUES ($1, $2::uuid, $3::jsonb, $4) "
                    "ON CONFLICT (token) DO UPDATE SET "
                    "payload = EXCLUDED.payload, expires_at = EXCLUDED.expires_at",
                    s.token,
                    s.tenant_id,
                    json.dumps(s.payload),
                    s.expires_at,
                )

    async def delete(self, token: str, *, tenant_id: str | None = None) -> None:
        async with self._pool.acquire() as conn:
            if tenant_id is not None:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        tenant_id,
                    )
                    await conn.execute(
                        "DELETE FROM sessions WHERE token = $1 AND tenant_id = $2::uuid",
                        token,
                        tenant_id,
                    )
            else:
                await conn.execute("DELETE FROM sessions WHERE token = $1", token)

    async def list(self, tenant_id: str) -> list[Session]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    tenant_id,
                )
                rows = await conn.fetch(
                    "SELECT token, tenant_id::text, payload, created_at, expires_at "
                    "FROM sessions WHERE tenant_id = $1::uuid AND expires_at > now() "
                    "ORDER BY created_at DESC",
                    tenant_id,
                )
        return [
            Session(
                token=r["token"],
                tenant_id=r["tenant_id"],
                payload=_parse_payload(r["payload"]),
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
            for r in rows
        ]

    async def close(self) -> None:
        return None


class RedisSessionStore:
    """Store backed by redis.asyncio. List uses SCAN and filters client-side."""

    def __init__(self, redis_client, key_prefix: str = "omur:session:"):
        self._r = redis_client
        self._prefix = key_prefix

    def _key(self, token: str) -> str:
        return self._prefix + token

    async def get(self, token: str) -> Session:
        b = await self._r.get(self._key(token))
        if b is None:
            raise NotFound(token)
        d = json.loads(b)
        d["expires_at"] = datetime.fromisoformat(d["expires_at"])
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        return Session(**d)

    async def put(self, s: Session) -> None:
        ttl = int((s.expires_at - datetime.now(timezone.utc)).total_seconds())
        if ttl < 1:
            ttl = 1
        d = {
            "token": s.token,
            "tenant_id": s.tenant_id,
            "payload": s.payload,
            "expires_at": s.expires_at.isoformat(),
            "created_at": s.created_at.isoformat(),
        }
        await self._r.setex(self._key(s.token), ttl, json.dumps(d))

    async def delete(self, token: str) -> None:
        await self._r.delete(self._key(token))

    async def list(self, tenant_id: str) -> list[Session]:
        out: list[Session] = []
        async for key in self._r.scan_iter(self._prefix + "*"):
            key_str = key.decode() if isinstance(key, (bytes, bytearray)) else key
            try:
                s = await self.get(key_str.removeprefix(self._prefix))
            except NotFound:
                continue
            if s.tenant_id == tenant_id:
                out.append(s)
        return out

    async def close(self) -> None:
        await self._r.aclose()


def backend_from_env() -> str:
    v = os.getenv("OMUR_SESSION_BACKEND", "postgres")
    if v not in {"postgres", "redis"}:
        raise ValueError(f"unknown OMUR_SESSION_BACKEND: {v}")
    return v


async def new_store(*, pool=None, redis_client=None) -> SessionStore:
    backend = backend_from_env()
    if backend == "postgres":
        if pool is None:
            raise ValueError("postgres backend requires pool=")
        return PostgresSessionStore(pool)
    if backend == "redis":
        if redis_client is None:
            import redis.asyncio as aioredis

            host = os.getenv("VALKEY_HOST", "valkey")
            port = os.getenv("VALKEY_PORT", "6379")
            password = os.getenv("VALKEY_PASSWORD") or None
            url = (
                f"redis://:{password}@{host}:{port}"
                if password
                else f"redis://{host}:{port}"
            )
            redis_client = aioredis.from_url(url)
        return RedisSessionStore(redis_client)
    raise RuntimeError("unreachable")
