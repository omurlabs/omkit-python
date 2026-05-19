"""omkit/featureflags/postgres.py — TTL-cached flag store backed by app_settings.

Concurrency model:

  * Current map held as a single dict reference behind an asyncio.Lock for
    swap; reads are lock-free (just read the attribute).
  * Concurrent refresh calls collapse to one DB roundtrip — the first call
    holds the lock, others await its completion and reuse the result.
  * On refresh error, the cache is NOT zeroed — stale served, warning logged.
  * invalidate(key) publishes a new map with the key removed. Local to this
    process; other replicas pick up changes within TTL (typically 30s).

The TTL bounds FLAG staleness, not USER-ROLE staleness — roles come from
forward-auth headers via `omkit.auth.roles_from_context()` every request.

exports: PostgresStore | load_for_service
rules:   The `app_settings.key LIKE 'flag.%'` query shape is part of the
         cross-SDK contract — coordinate with omkit-go before changing.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable, Mapping

from omkit.featureflags.flag import Flag, parse_from_json

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger(__name__)

RefresherFunc = Callable[[], Awaitable[Mapping[str, Flag]]]


class PostgresStore:
    """TTL-cached Store reading flag.* rows from app_settings."""

    def __init__(
        self,
        refresh: RefresherFunc,
        ttl: float,
    ):
        """Test-friendly constructor — caller supplies the async refresher."""
        self._refresh: RefresherFunc = refresh
        self._ttl = ttl
        self._flags: dict[str, Flag] = {}
        self._last_refreshed: float = 0.0
        self._refresh_lock = asyncio.Lock()

    @classmethod
    def from_pool(cls, pool: "asyncpg.Pool", ttl: float) -> "PostgresStore":
        """Production constructor — refreshes from `app_settings`."""

        async def _refresh() -> Mapping[str, Flag]:
            return await _load_from_pool(pool)

        return cls(refresh=_refresh, ttl=ttl)

    def get(self, key: str) -> Flag | None:
        """Return the flag, or None if unknown. Triggers a background refresh
        when stale (fire-and-forget; current snapshot returned without blocking).
        """
        if self._stale():
            self._kick_refresh()
        return self._flags.get(key)

    def all_flags(self) -> Mapping[str, Flag]:
        """Snapshot of the current cached map. Triggers background refresh on stale."""
        if self._stale():
            self._kick_refresh()
        return dict(self._flags)

    async def refresh(self) -> None:
        """Synchronously reload the flag map. Errors leave the cache intact."""
        async with self._refresh_lock:
            try:
                fresh = await self._refresh()
            except Exception as exc:
                _log.warning("featureflags.refresh_failed: %s", exc)
                return
            self._flags = dict(fresh)
            self._last_refreshed = time.monotonic()

    async def invalidate(self, key: str) -> None:
        """Delete the entry for key from the local cache. No DB read.

        Local to this process — other replicas pick up changes within TTL.
        """
        async with self._refresh_lock:
            self._flags.pop(key, None)

    def _stale(self) -> bool:
        if self._last_refreshed == 0.0:
            return True
        return (time.monotonic() - self._last_refreshed) > self._ttl

    def _kick_refresh(self) -> None:
        """Fire-and-forget refresh. If no running loop, skip silently."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.refresh())


async def load_for_service(pool: "asyncpg.Pool") -> Mapping[str, Flag]:
    """One-shot read without a cache — for tests or handlers without a store."""
    return await _load_from_pool(pool)


async def _load_from_pool(pool: "asyncpg.Pool") -> dict[str, Flag]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value_json FROM app_settings WHERE key LIKE 'flag.%'"
        )
    out: dict[str, Flag] = {}
    for row in rows:
        out[row["key"]] = parse_from_json(row["value_json"])
    return out
