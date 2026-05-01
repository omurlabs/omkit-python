"""packages/omur-sdk/tests/test_tracing.py — Tests for OpenTelemetry tracing bootstrap.

exports: test_init_tracing_disabled_when_no_endpoint() | test_init_tracing_returns_provider() | test_init_tracing_sets_service_name() | test_instrument_fastapi_idempotent()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import sys
import pytest
from unittest.mock import patch, MagicMock


def _make_otel_mocks():
    """Return a dict of sys.modules patches that stub all OTel packages."""
    trace_mod = MagicMock()
    sdk_trace_mod = MagicMock()
    sdk_export_mod = MagicMock()
    sdk_resources_mod = MagicMock()
    exporter_mod = MagicMock()

    return {
        "opentelemetry": MagicMock(trace=trace_mod),
        "opentelemetry.trace": trace_mod,
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.trace": sdk_trace_mod,
        "opentelemetry.sdk.trace.export": sdk_export_mod,
        "opentelemetry.sdk.resources": sdk_resources_mod,
        "opentelemetry.exporter": MagicMock(),
        "opentelemetry.exporter.otlp": MagicMock(),
        "opentelemetry.exporter.otlp.proto": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": exporter_mod,
    }, sdk_trace_mod, sdk_resources_mod, exporter_mod, sdk_export_mod, trace_mod


def test_init_tracing_disabled_when_no_endpoint():
    """Returns None when endpoint is empty string."""
    from omur_sdk.tracing import init_tracing
    result = init_tracing("test-service", endpoint="")
    assert result is None


def test_init_tracing_returns_provider():
    """init_tracing returns a configured TracerProvider when endpoint is set."""
    mocks, sdk_trace_mod, _, _, _, _ = _make_otel_mocks()
    provider = MagicMock()
    sdk_trace_mod.TracerProvider.return_value = provider

    with patch.dict(sys.modules, mocks):
        # Force reload so lazy imports pick up mocked modules
        import importlib
        import omur_sdk.tracing as tracing_mod
        importlib.reload(tracing_mod)
        result = tracing_mod.init_tracing("test-service", endpoint="http://localhost:4318")
        assert result is provider


def test_init_tracing_sets_service_name():
    """Service name is passed as a resource attribute."""
    mocks, sdk_trace_mod, sdk_resources_mod, _, _, _ = _make_otel_mocks()
    resource_instance = MagicMock()
    sdk_resources_mod.Resource.create.return_value = resource_instance

    with patch.dict(sys.modules, mocks):
        import importlib
        import omur_sdk.tracing as tracing_mod
        importlib.reload(tracing_mod)
        tracing_mod.init_tracing("spine", endpoint="http://localhost:4318")
        attrs = sdk_resources_mod.Resource.create.call_args[0][0]
        assert attrs["service.name"] == "spine"


def test_instrument_fastapi_idempotent():
    from fastapi import FastAPI

    from omur_sdk.tracing import instrument_fastapi

    app = FastAPI()
    instrument_fastapi(app)
    instrument_fastapi(app)  # second call must not raise
