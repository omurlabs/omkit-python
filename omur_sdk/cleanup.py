"""packages/omur-sdk/omur_sdk/cleanup.py — Coordinated periodic cleanup task runner.

Loop.run() fires the provided ``task`` coroutine every ``interval`` seconds
while holding ``pg_try_advisory_lock(lock_key)`` — horizontally scaled
replicas of the same service won't double-execute the cleanup. Lock
contention turns the tick into a silent no-op.

exports: class Loop
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


class Loop:
    def __init__(
        self,
        pool,
        *,
        lock_key: int,
        interval: float,
        task: Callable[[], Awaitable[None]],
        name: str = "cleanup-loop",
    ):
        self._pool = pool
        self._lock_key = lock_key
        self._interval = interval
        self._task = task
        self._name = name

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as e:
                log.warning("%s: tick failed: %s", self._name, e)
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        async with self._pool.acquire() as conn:
            got = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", self._lock_key
            )
            if not got:
                return
            try:
                await self._task()
            finally:
                await conn.execute(
                    "SELECT pg_advisory_unlock($1)", self._lock_key
                )
