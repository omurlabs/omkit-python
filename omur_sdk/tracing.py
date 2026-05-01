"""packages/omur-sdk/omur_sdk/tracing.py — OpenTelemetry tracing bootstrap for Omur services.

Usage:
    from omur_sdk.tracing import init_tracing
    init_tracing("spine")  # Call once at startup

Tracing is OFF by default since the 2026-04 infra consolidation (Alloy,
Tempo, and VictoriaLogs were removed). Set OTEL_EXPORTER_OTLP_ENDPOINT
to a reachable collector (e.g. ``http://alloy:4318``) to re-enable.

exports: DEFAULT_ENDPOINT | init_tracing(service_name, endpoint) | instrument_fastapi(app)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import os
import structlog

log = structlog.get_logger()

DEFAULT_ENDPOINT = ""


def init_tracing(
    service_name: str,
    endpoint: str | None = None,
) -> "TracerProvider | None":
    """Initialize OpenTelemetry with OTLP/HTTP export.

    Returns the TracerProvider, or None if tracing is disabled.
    """
    if endpoint is None:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)

    if not endpoint:
        log.info("tracing.disabled", service=service_name)
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:
        log.info("tracing.not_installed", service=service_name)
        return None

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    log.info("tracing.enabled", service=service_name, endpoint=endpoint)
    return provider


def instrument_fastapi(app) -> None:
    """Wrap a FastAPI app with OpenTelemetry server-side instrumentation.

    Idempotent: calling twice on the same app is a no-op. Silently no-ops if
    opentelemetry-instrumentation-fastapi is not installed (in-tree optional).
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return

    if getattr(app, "_omur_otel_instrumented", False):
        return
    FastAPIInstrumentor.instrument_app(app)
    app._omur_otel_instrumented = True
