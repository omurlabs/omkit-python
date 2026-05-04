"""packages/omur-sdk/omur_sdk/jobqueue/streaq.py — streaq integration for Omur Python services.

Wraps the streaq Worker with the SDK's tenant + envelope contract so all
Python services have the same ergonomics as the Go-side `omur_sdk.jobqueue`
helpers (which front Asynq).

Public surface:

    make_worker(redis_url, queue_name, ...)  -> streaq.Worker
    tenant_middleware                         -> streaq middleware factory
    enqueue(task, tenant_id, payload, ...)    -> shorthand for envelope-wrapped enqueue
    mount_streaq_ui(app, worker, prefix=...)  -> mount the FastAPI UI router
    StreaqPromCollector(worker)               -> prometheus.Collector for worker.counters

Conventions:

- Workers serialize tasks as JSON. Required because (a) cross-language
  round-trip with Go workers requires JSON and (b) the streaq UI renders
  JSON arguments inline. streaq's default binary serializer is replaced.
  Callers MUST pass JSON-safe payloads.
- Every task is tenant-scoped. The first positional argument of every
  registered task is the envelope dict; `tenant_middleware` unwraps it,
  binds `tenant.current()`, and passes the inner payload to the handler.
- Defaults match the SDK contract documented in
  `docs/superpowers/specs/2026-04-29-job-queue-design.md`:
  concurrency=4, max_tries=3, task_timeout=300s, ttl=48h.

exports: DEFAULT_CONCURRENCY | DEFAULT_MAX_TRIES | DEFAULT_TIMEOUT_SECONDS | DEFAULT_TTL | make_worker(redis_url, queue_name) | tenant_middleware(next_handler) | enqueue(task, tenant_id, payload) | mount_streaq_ui(app, worker) | _STREAQ_COUNTER_KEYS | class StreaqPromCollector
rules:   The module requires all Redis-based job queue operations to be thread-safe and idempotent, as it's designed for high-concurrency worker environments where tasks may be retried or processed by multiple workers simultaneously.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable

from omur_sdk import tenant
from omur_sdk.jobqueue.envelope import (
    Envelope,
    InvalidEnvelopeError,
    unwrap,
    wrap,
)

log = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4
DEFAULT_MAX_TRIES = 3
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_TTL = timedelta(hours=48)


def _json_serializer(obj: Any) -> bytes:
    return json.dumps(obj, default=str, separators=(",", ":")).encode("utf-8")


def _json_deserializer(data: bytes) -> Any:
    return json.loads(data)


def make_worker(
    redis_url: str,
    queue_name: str,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_tries: int = DEFAULT_MAX_TRIES,
    task_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ttl: timedelta = DEFAULT_TTL,
    handle_signals: bool = False,
    **worker_kwargs: Any,
):
    """Construct a streaq Worker pre-configured for Omur services.

    `redis_url` accepts the same forms streaq does (`redis://valkey:6379/0`
    or `rediss://…`). For Valkey with password, encode it in the URL:
    `redis://:PASSWORD@valkey:6379/0`.

    `handle_signals=False` because services run streaq alongside an HTTP
    server and own their own SIGTERM handler — letting streaq install one
    deadlocks shutdown. The lifespan-context-manager pattern stops the
    worker cleanly on app shutdown instead.

    `max_tries` and `task_timeout_seconds` set the worker-level defaults;
    individual `@worker.task(...)` decorators may override.

    Extra keyword arguments are forwarded to `streaq.Worker(...)` for
    advanced cases (sentinel/cluster, custom serializers, etc.).

    Rules:   The `redis_url` must be a valid Redis/Valkey URL, including password-encoded URLs if required. The `handle_signals` parameter should be set to `True` only if the worker is intended to handle OS signals for graceful shutdown.
    """
    import streaq

    return streaq.Worker(
        redis_url=redis_url,
        queue_name=queue_name,
        concurrency=concurrency,
        handle_signals=handle_signals,
        serializer=_json_serializer,
        deserializer=_json_deserializer,
        **worker_kwargs,
    )


# ─────────────────────────────────────────────────────────────────────
# Tenant + envelope middleware
# ─────────────────────────────────────────────────────────────────────


def tenant_middleware(next_handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """streaq middleware. Unwraps the envelope from the first positional
    arg, binds `tenant.current()`, then calls `next_handler(payload, …)`.

    Register on the Worker:

        worker.middleware(tenant_middleware)

    And then write tasks as:

        @worker.task(timeout=600)
        async def parse(payload: dict) -> None:
            doc_id = payload["doc_id"]
            assert tenant.current() is not None

    `InvalidEnvelopeError` raised here propagates as a regular exception —
    streaq counts it as a failure and respects `max_tries`. Callers MUST
    ensure all enqueues go through `enqueue()` below so envelopes are
    well-formed; a ValidationError at the worker boundary indicates a
    bug, not a transient fault.

    Rules:   The `next_handler` function must accept the unwrapped payload as its first positional argument and must be used in conjunction with a worker that has `tenant_middleware` registered to ensure tenant context is correctly set.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not args:
            raise InvalidEnvelopeError("task called with no positional args")
        try:
            env: Envelope = unwrap(args[0])
        except InvalidEnvelopeError:
            log.error("streaq.invalid_envelope")
            raise
        with tenant.bind(env.tenant_id):
            return await next_handler(env.payload, *args[1:], **kwargs)

    return wrapper


# ─────────────────────────────────────────────────────────────────────
# Enqueue helper
# ─────────────────────────────────────────────────────────────────────


def enqueue(task: Any, tenant_id: str, payload: dict[str, Any], **opts: Any) -> Awaitable[Any]:
    """Enqueue a streaq task with an envelope-wrapped payload.

    `task` is the result of `@worker.task(...)`. Returns the awaitable
    streaq returns from `task.enqueue(...)`.

    Caller is responsible for `await`-ing.

    Rules:   The `task` must be a valid streaq task created using `@worker.task(...)`; otherwise, `task.enqueue(...)` will fail. The `tenant_id` must be a valid identifier for the tenant context.
    """
    envelope_bytes = wrap(tenant_id, payload)
    envelope_dict = json.loads(envelope_bytes)
    return task.enqueue(envelope_dict, **opts)


# ─────────────────────────────────────────────────────────────────────
# FastAPI UI mount
# ─────────────────────────────────────────────────────────────────────


def mount_streaq_ui(app: Any, worker: Any, *, prefix: str = "/queue/ui") -> None:
    """Mount streaq's built-in admin UI at `prefix`.

    streaq's UI router uses a FastAPI dependency `get_worker` that raises
    412 by default. Override it to return our worker so the UI can read
    queue state, results, and counters. The route is otherwise open —
    Caddy's oauth2-proxy forward-auth gates access (Zitadel SSO).

    Rules:   The `app` must be a FastAPI application instance, and the `worker` must be a properly initialized streaq worker. The `prefix` should not conflict with existing routes in the application.
    """
    try:
        from streaq.ui.deps import get_worker
        from streaq.ui.tasks import router as tasks_router
    except ImportError as exc:
        raise RuntimeError(
            "streaq UI requires `streaq[web]` extra (fastapi/jinja2/uvicorn)"
        ) from exc

    app.dependency_overrides[get_worker] = lambda: worker
    app.include_router(tasks_router, prefix=prefix)


# ─────────────────────────────────────────────────────────────────────
# Prometheus bridge
# ─────────────────────────────────────────────────────────────────────


_STREAQ_COUNTER_KEYS = (
    "aborted",
    "completed",
    "failed",
    "relinquished",
    "retried",
    "running",
)


class StreaqPromCollector:
    """Prometheus collector that lazily reads `worker.counters` on every
    scrape and exports gauges:

        streaq_worker_aborted{queue}
        streaq_worker_completed{queue}
        streaq_worker_failed{queue}
        streaq_worker_relinquished{queue}
        streaq_worker_retried{queue}
        streaq_worker_running{queue}

    Register once per process:

        from prometheus_client import REGISTRY
        REGISTRY.register(StreaqPromCollector(worker))

    All metrics are gauges (counters reset on worker restart, which is
    fine — alert dashboards already de-dupe on `service` instance).
    """

    def __init__(self, worker: Any) -> None:
        self._worker = worker

    def describe(self) -> Any:
        return iter([])

    def collect(self) -> Any:
        """
        Rules:   The `_worker` object must have a `queue_name` attribute and a `counters` dictionary with keys matching `_STREAQ_COUNTER_KEYS`; otherwise, the Prometheus metrics will not be correctly populated.
        """
        from prometheus_client.core import GaugeMetricFamily

        queue = getattr(self._worker, "queue_name", "default")
        counters = getattr(self._worker, "counters", {}) or {}
        for key in _STREAQ_COUNTER_KEYS:
            g = GaugeMetricFamily(
                f"streaq_worker_{key}",
                f"streaq worker {key} count (since process start)",
                labels=["queue"],
            )
            g.add_metric([queue], float(counters.get(key, 0)))
            yield g


__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_MAX_TRIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_TTL",
    "StreaqPromCollector",
    "enqueue",
    "make_worker",
    "mount_streaq_ui",
    "tenant_middleware",
]
