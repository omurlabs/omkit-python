"""Shared structlog configuration for all Omur services.

Usage:
    from omur_sdk.logging import configure_logging
    configure_logging("spine")  # Call once at startup, before get_logger()
"""

import structlog


def configure_logging(service_name: str) -> None:
    """Configure structlog with ISO timestamps, log level, and contextvars."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
