"""Transport facade — re-exports cross-cutting wire / observability primitives.

This is an additive grouping for discoverability. Existing imports from the
flat modules (``omur_sdk.http``, ``omur_sdk.tracing``, etc.) continue to work
unchanged; new code is encouraged to import from this facade.
"""

from omur_sdk.health import mount_health_endpoints
from omur_sdk.http import build_tenant_client
from omur_sdk.logging import configure_logging
from omur_sdk.metrics import mount_metrics
from omur_sdk.resilience import CircuitBreaker, resilient
from omur_sdk.tracing import init_tracing, instrument_fastapi

__all__ = [
    "build_tenant_client",
    "init_tracing",
    "instrument_fastapi",
    "mount_metrics",
    "mount_health_endpoints",
    "configure_logging",
    "CircuitBreaker",
    "resilient",
]
