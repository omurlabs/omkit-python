"""packages/omur-sdk/omur_sdk/logging.py — Shared structlog configuration for all Omur services.

Default output is JSON, suitable for production log aggregation. Set
``LOG_FORMAT=console`` to switch to the human-readable renderer during dev.

Usage:
    from omur_sdk.logging import configure_logging
    configure_logging("spine")  # Call once at startup, before get_logger()

exports: configure_logging(service_name)
used_by: none
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

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
