"""omkit/scheduler/types.py — data + protocol types for the scheduler.

exports: Provider | ProviderSource | SchedulerBackend | Enqueuer | CronDeriver
rules:   Protocols are framework-agnostic — never bake in streaq, asynq, or
         asyncpg specifics here. Concrete adapters belong in source.py or
         consuming services.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/scheduler
message:
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class Provider:
    """One row from the providers table, after JSON-decoding config."""

    tenant_id: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)


# (cronspec, ok) — ok=False skips the row (unknown provider, missing config).
CronDeriver = Callable[[Provider], tuple[str, bool]]


@runtime_checkable
class ProviderSource(Protocol):
    """Data path the reconcile loop reads from. Production: PgxProviderSource."""

    async def fetch_providers(self, kind: str) -> list[Provider]: ...


@runtime_checkable
class SchedulerBackend(Protocol):
    """Narrow interface the reconciler needs from the underlying cron engine.

    Adapters wrap streaq.Scheduler, asynq.Scheduler, or an in-memory test
    double. `body` is the wire-format task envelope (typically from
    `omkit.jobqueue.envelope.wrap`).
    """

    async def register(
        self,
        cronspec: str,
        task_type: str,
        body: bytes,
        *,
        queue: str,
    ) -> str:
        """Return a backend-specific entry_id used later by unregister()."""
        ...

    async def unregister(self, entry_id: str) -> None: ...

    async def start(self) -> None: ...

    async def shutdown(self) -> None: ...


@runtime_checkable
class Enqueuer(Protocol):
    """Optional: enqueue one task immediately on first registration.

    Restores "first poll on start" behaviour from legacy ticker loops so
    callers don't wait for the first cron firing.
    """

    async def enqueue(
        self,
        task_type: str,
        tenant_id: str,
        payload: Any,
        *,
        queue: str,
    ) -> None: ...


# Convenience alias for documentation.
RefresherFn = Callable[[], Awaitable[list[Provider]]]
