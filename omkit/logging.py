"""omkit/logging.py — Shared structlog configuration for all Omur services.

Default output is JSON, suitable for production log aggregation. Set
``LOG_FORMAT=console`` to switch to the human-readable renderer during dev.

Usage:
    from omkit.logging import configure_logging
    configure_logging("spine")  # Call once at startup, before get_logger()

exports: configure_logging(service_name)
rules:   The logging module must maintain backward compatibility with existing log format configurations and service name resolution patterns across all SDK versions. The module cannot introduce breaking changes to its public API or alter the default logging behavior without explicit versioned migration paths. All logging configurations must remain thread-safe and support concurrent service initialization without race conditions.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import os

import structlog


def configure_logging(service_name: str) -> None:
    """Configure structlog with ISO timestamps, log level, contextvars, and
    a renderer selected by the ``LOG_FORMAT`` environment variable.

    Every log record emitted after this call carries a ``service`` field set
    to ``service_name`` (unless the call site overrides it explicitly).

    ``LOG_FORMAT`` values:
        * ``json`` (default) — JSONRenderer for production / log aggregation.
        * ``console`` — ConsoleRenderer for local development.

    Rules:   LOG_FORMAT environment variable must be either 'json' or 'console' (case insensitive), with 'json' as default. Future developers must ensure these specific values are handled or risk runtime errors.
    """
    fmt = os.environ.get("LOG_FORMAT", "json").lower()
    if fmt == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    def _add_service(_logger, _method, event_dict):
        event_dict.setdefault("service", service_name)
        return event_dict

    def _add_correlation(_logger, _method, event_dict):
        # Pull tenant + request_id off the SDK-managed contextvars so every
        # log record is auto-tagged with cross-service correlation fields.
        # Lazy import keeps this module decoupled from tenant.
        try:
            from omkit.tenant import current_or_none, request_id
        except Exception:
            return event_dict
        try:
            tid = current_or_none()
            rid = request_id()
        except Exception:
            return event_dict
        if tid:
            event_dict.setdefault("tenant_id", tid)
        if rid:
            event_dict.setdefault("request_id", rid)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service,
            _add_correlation,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
