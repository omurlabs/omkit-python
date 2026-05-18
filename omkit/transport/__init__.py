"""omkit/transport/__init__.py — re-exports cross-cutting wire / observability primitives.

This is an additive grouping for discoverability. Existing imports from the
flat modules (``omkit.httpclient``, ``omkit.tracing``, etc.) continue to work
unchanged; new code is encouraged to import from this facade.

exports: none
rules:   The transport module must maintain backward compatibility for all existing API endpoints and response formats, as breaking changes will affect downstream services that depend on stable interfaces. All network communication must go through a centralized connection pooling mechanism to ensure resource efficiency and proper handling of concurrent requests. The module cannot introduce any synchronous blocking operations that would impact the overall performance of applications using the SDK.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from omkit.health import mount_health_endpoints
from omkit.httpclient import build_tenant_client
from omkit.logging import configure_logging
from omkit.metrics import mount_metrics
from omkit.resilience import CircuitBreaker, resilient
from omkit.tracing import init_tracing, instrument_fastapi

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
