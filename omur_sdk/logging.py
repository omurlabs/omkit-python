"""Shared structlog configuration for all Omur services.

Default output is JSON, suitable for production log aggregation. Set
``LOG_FORMAT=console`` to switch to the human-readable renderer during dev.

Usage:
    from omur_sdk.logging import configure_logging
    configure_logging("spine")  # Call once at startup, before get_logger()
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
