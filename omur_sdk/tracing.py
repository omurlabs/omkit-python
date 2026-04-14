"""OpenTelemetry tracing bootstrap for Omur services.

Usage:
    from omur_sdk.tracing import init_tracing
    init_tracing("spine")  # Call once at startup

Requires OTEL_EXPORTER_OTLP_ENDPOINT env var (e.g. http://alloy:4318).
Set to empty string to disable tracing.
"""

from __future__ import annotations

import os
import structlog

log = structlog.get_logger()

DEFAULT_ENDPOINT = "http://alloy:4318"


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

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    log.info("tracing.enabled", service=service_name, endpoint=endpoint)
    return provider
