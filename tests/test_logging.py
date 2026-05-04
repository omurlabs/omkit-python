"""packages/omur-sdk/tests/test_logging.py — Tests for shared structlog configuration.

exports: test_configure_logging_sets_processors() | test_configure_logging_is_idempotent() | test_default_is_json(monkeypatch) | test_console_format(monkeypatch)
used_by: none
rules:   none
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import json
import logging
from io import StringIO

import structlog
from omur_sdk.logging import configure_logging


def test_configure_logging_sets_processors():
    """configure_logging installs ISO timestamps and contextvars merge.

    Rules:   Logging configuration must be idempotent and should not raise exceptions when called multiple times with different service names.
    """
    configure_logging("test-service")
    config = structlog.get_config()
    processor_types = [type(p).__name__ for p in config["processors"]]
    assert "TimeStamper" in processor_types or any("TimeStamper" in str(p) for p in config["processors"])


def test_configure_logging_is_idempotent():
    """Calling configure_logging twice doesn't raise.

    Rules:   Calling configure_logging multiple times with different service names should not raise an exception, but the last call's service name will be used.
    """
    configure_logging("svc-a")
    configure_logging("svc-b")


def _capture_line(monkeypatch, env_value: str | None) -> str:
    if env_value is None:
        monkeypatch.delenv("LOG_FORMAT", raising=False)
    else:
        monkeypatch.setenv("LOG_FORMAT", env_value)

    buf = StringIO()

    class _StreamLoggerFactory:
        def __call__(self, *args, **kwargs):
            logger = logging.Logger("test")
            handler = logging.StreamHandler(buf)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            return logger

    structlog.reset_defaults()
    configure_logging("test-svc")
    structlog.configure(
        processors=structlog.get_config()["processors"],
        wrapper_class=structlog.get_config()["wrapper_class"],
        context_class=structlog.get_config()["context_class"],
        logger_factory=_StreamLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    log = structlog.get_logger()
    log.info("hello", user="vadim")
    return buf.getvalue().strip()


def test_default_is_json(monkeypatch):
    """
    Rules:   The default logging format must produce valid JSON output with standard log fields like 'event', 'user', and 'level'.
    """
    line = _capture_line(monkeypatch, None)
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["user"] == "vadim"
    assert payload["level"] == "info"


def test_console_format(monkeypatch):
    """
    Rules:   Console format should output plain text logs that are not JSON encoded, while JSON format should be used for structured logging.
    """
    line = _capture_line(monkeypatch, "console")
    assert "hello" in line
    try:
        json.loads(line)
    except json.JSONDecodeError:
        return
    raise AssertionError("console format produced JSON unexpectedly")


def test_service_name_bound_to_records(monkeypatch):
    """Every log record must carry the configured service name.

    Rules:   The service name must be consistently attached to all log records, and this test verifies that the default service name 'test-svc' is correctly set in the log output.
    """
    line = _capture_line(monkeypatch, None)
    payload = json.loads(line)
    assert payload["service"] == "test-svc"


def test_correlation_fields_emitted_when_tenant_bound(monkeypatch):
    """When tenant + request_id are bound, logs auto-carry both fields.

    Rules:   When tenant and request_id are bound to the logging context, they must automatically appear in all subsequent log records without explicit inclusion in the log message.
    """
    from omur_sdk import tenant

    monkeypatch.delenv("LOG_FORMAT", raising=False)
    buf = StringIO()

    class _StreamLoggerFactory:
        def __call__(self, *args, **kwargs):
            logger = logging.Logger("test")
            handler = logging.StreamHandler(buf)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            return logger

    structlog.reset_defaults()
    configure_logging("test-svc")
    structlog.configure(
        processors=structlog.get_config()["processors"],
        wrapper_class=structlog.get_config()["wrapper_class"],
        context_class=structlog.get_config()["context_class"],
        logger_factory=_StreamLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    with tenant.bind("11111111-1111-4111-8111-111111111111", "req-abc"):
        log = structlog.get_logger()
        log.info("hello")
    payload = json.loads(buf.getvalue().strip())
    assert payload["tenant_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["request_id"] == "req-abc"


def test_service_name_can_be_overridden_per_call(monkeypatch):
    """Explicit service kwarg on a log call wins over default.

    Rules:   A service name passed explicitly as a keyword argument in a log call takes precedence over the default service name configured for the logger.
    """
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    buf = StringIO()

    class _StreamLoggerFactory:
        def __call__(self, *args, **kwargs):
            logger = logging.Logger("test")
            handler = logging.StreamHandler(buf)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            return logger

    structlog.reset_defaults()
    configure_logging("default-svc")
    structlog.configure(
        processors=structlog.get_config()["processors"],
        wrapper_class=structlog.get_config()["wrapper_class"],
        context_class=structlog.get_config()["context_class"],
        logger_factory=_StreamLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    log = structlog.get_logger()
    log.info("hello", service="override-svc")
    payload = json.loads(buf.getvalue().strip())
    assert payload["service"] == "override-svc"
