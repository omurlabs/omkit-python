"""packages/omur-sdk/omkit/sessions.py — Session store abstractions for services that persist short-lived per-user.

sessions. Two backends are provided:

- ``PostgresSessionStore`` (default) — stores sessions in the ``sessions``
  table and lets Postgres expire them.
- ``RedisSessionStore`` — opt-in via ``SESSION_BACKEND=redis``; wraps
  ``redis.asyncio`` for legacy/low-latency deployments.

The ``Session`` dataclass is the wire shape exchanged between Store
implementations and callers.

exports: class NotFound | class Session | class SessionStore | class PostgresSessionStore | class RedisSessionStore | backend_from_env() | new_store()
rules:   The session store implementation must support both PostgreSQL and Redis backends, with the backend selection determined at runtime via the `SESSION_BACKEND` environment variable. Any new session store implementation must conform to the `SessionStore` protocol and handle asynchronous operations correctly. The `Session` class and `NotFound` exception are central to the module's behavior and must remain consistent across all store implementations.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
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
    async def get(self, token: str, *, tenant_id: str | None = None) -> Session:
        """
        Rules:   The token parameter must be a valid non-empty string representing an authentication token. The tenant_id parameter is optional but if provided must be a non-empty string. The function returns a Session object containing the user's session data. The function may raise exceptions for invalid tokens, unauthorized access, or tenant-specific errors. The returned Session object must contain valid session data and is expected to be used for subsequent authenticated requests.
        """
        ...
    async def put(self, session: Session) -> None:
        """
        Rules:   The session parameter must be a valid Session object that is not already associated with another async operation, and the function will asynchronously associate the session with the current object's context. The function must be called in an async context and will not raise exceptions for invalid session states, but may fail silently if the session cannot be properly associated.
        """
        ...
    async def delete(self, token: str, *, tenant_id: str | None = None) -> None:
        """
        Rules:   The delete method requires a valid token string and optional tenant_id, must be called asynchronously, and performs no return value operations. Implementations must handle token validation and tenant scoping logic while ensuring thread-safe deletion operations.
        """
        ...
    async def list(self, tenant_id: str) -> list[Session]:
        """
        Rules:   The tenant_id parameter must be a non-empty string representing a valid tenant identifier. The function must return a list of Session objects associated with the specified tenant, and may raise exceptions if the tenant does not exist or if there are insufficient permissions to access the sessions.
        """
        ...
    async def close(self) -> None:
        """
        Rules:   Async close method must be idempotent and handle concurrent calls gracefully, ensuring all resources are properly released and no further operations should be performed after calling close. Implementations must not raise exceptions during cleanup, and the method should complete within a reasonable timeout period.
        """
        ...


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
        """
        Rules:   Function requires a valid token string and optional tenant_id; raises NotFound if token is not found or belongs to a different tenant. Returns a Session object with parsed payload, or raises NotFound if session is expired or not found.
        """
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
        """
        Rules:   Function accepts a Session object and stores it in the database, updating existing records if the token already exists. The implementation must ensure tenant isolation through transaction-local configuration and handle JSON serialization of the session payload.
        """
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
        """
        Rules:   Function deletes a session token from the database, optionally scoped to a tenant ID; if tenant_id is provided, the operation runs within a transaction that sets the tenant context before deletion. The function requires a valid database connection pool and will raise exceptions on database errors or invalid inputs.
        """
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
        """
        Rules:   Function requires valid UUID tenant_id string input and returns list of Session objects ordered by creation time, with no side effects beyond database queries. Implementation must handle database connection and transaction management internally, and the tenant_id must exist in the database for meaningful results.
        """
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
        """
        Rules:   Async close method should gracefully terminate any ongoing operations and release all resources, with no return value expected. Implementations must ensure thread safety and idempotency, allowing multiple calls to succeed without error.
        """
        return None


class RedisSessionStore:
    """Store backed by redis.asyncio. List uses SCAN and filters client-side."""

    def __init__(self, redis_client, key_prefix: str = "omur:session:"):
        self._r = redis_client
        self._prefix = key_prefix

    def _key(self, token: str) -> str:
        return self._prefix + token

    async def get(self, token: str) -> Session:
        """
        Rules:   Function requires token string input and returns a Session object with parsed datetime fields; raises NotFound exception when token is not found in storage. Function performs async Redis get operation and JSON deserialization, with caller responsible for handling the NotFound exception and ensuring token exists before calling.
        """
        b = await self._r.get(self._key(token))
        if b is None:
            raise NotFound(token)
        d = json.loads(b)
        d["expires_at"] = datetime.fromisoformat(d["expires_at"])
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        return Session(**d)

    async def put(self, s: Session) -> None:
        """
        Rules:   Function requires Session object with valid expires_at, tenant_id, and token attributes; stores session data with TTL expiration in Redis using JSON serialization; caller must ensure Session attributes are properly initialized and that _r.setex method is available.
        """
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
        """
        Rules:   The delete method requires a valid string token parameter and asynchronously removes the corresponding key-value pair from the underlying storage system. The method has no return value and may raise exceptions if the token is invalid or the storage operation fails.
        """
        await self._r.delete(self._key(token))

    async def list(self, tenant_id: str) -> list[Session]:
        """
        Rules:   Function must be called with a valid tenant_id string, returns list of Session objects belonging to that tenant, and may raise NotFound exception during iteration. Function performs asynchronous operations and should be called within an async context.
        """
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
        """
        Rules:   The close method must be called to properly terminate the underlying resource manager, and implementations must ensure the async context manager is safely closed without leaving resources open. The method should handle any cleanup operations asynchronously and not raise exceptions during the closing process.
        """
        await self._r.aclose()


def backend_from_env() -> str:
    """
    Rules:   Function reads SESSION_BACKEND environment variable and returns "postgres" if not set or invalid, raising ValueError for unknown values. Caller must ensure environment variable is properly set or handle potential ValueError exceptions.
    """
    v = os.getenv("SESSION_BACKEND", "postgres")
    if v not in {"postgres", "redis"}:
        raise ValueError(f"unknown SESSION_BACKEND: {v}")
    return v


async def new_store(*, pool=None, redis_client=None) -> SessionStore:
    """
    Rules:   Function requires either pool= or redis_client= arguments depending on the backend type determined by backend_from_env(), with postgres backend requiring pool and redis backend either accepting a redis_client or creating one from environment variables. The function may raise ValueError for missing required arguments or RuntimeError for unexpected backend states.
    """
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
