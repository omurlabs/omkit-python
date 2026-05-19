"""omkit/scheduler/__init__.py — DB-driven cron reconciler.

Wraps any cron-capable scheduler backend (streaq, asynq via adapter, or a
test stub) with a poll-and-diff reconcile loop driven by a `providers`
table. For services that derive schedules from DB rows (one entry per
(tenant, provider)), this package owns the reconcile pattern.

Backend-agnostic: pass a `SchedulerBackend` implementation. The streaq
adapter lives in the consuming service today — promote to omkit when a
second backend appears.

Cross-replica caveat: most underlying schedulers do NOT dedupe firings
across replicas. Deploy as a single replica until either (a) leader
election is added, or (b) handler-side idempotency makes duplicate
firings harmless.

exports: Provider | ProviderSource | PgxProviderSource | SchedulerBackend |
         Enqueuer | CronDeriver | Scheduler | DEFAULT_POLL_INTERVAL
rules:   The reconcile loop must be cooperative-cancellable via stop().
         Failures inside reconcile are logged and retried next tick — never
         crash the loop.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/scheduler
message:
"""

from __future__ import annotations

from omkit.scheduler.scheduler import DEFAULT_POLL_INTERVAL, Scheduler
from omkit.scheduler.source import PgxProviderSource
from omkit.scheduler.types import (
    CronDeriver,
    Enqueuer,
    Provider,
    ProviderSource,
    SchedulerBackend,
)

__all__ = [
    "Provider",
    "ProviderSource",
    "PgxProviderSource",
    "SchedulerBackend",
    "Enqueuer",
    "CronDeriver",
    "Scheduler",
    "DEFAULT_POLL_INTERVAL",
]
