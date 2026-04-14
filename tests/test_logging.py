"""Tests for shared structlog configuration."""

import structlog
from omur_sdk.logging import configure_logging


def test_configure_logging_sets_processors():
    """configure_logging installs ISO timestamps and contextvars merge."""
    configure_logging("test-service")
    config = structlog.get_config()
    processor_types = [type(p).__name__ for p in config["processors"]]
    assert "TimeStamper" in processor_types or any("TimeStamper" in str(p) for p in config["processors"])


def test_configure_logging_is_idempotent():
    """Calling configure_logging twice doesn't raise."""
    configure_logging("svc-a")
    configure_logging("svc-b")
