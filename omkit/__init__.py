"""omkit — multi-tenant SaaS scaffolding for Python services.

Public surface re-exports a small set of commonly-used helpers. Internal
primitives are available via the submodules directly.
"""
from omkit.httpclient import build_tenant_client
from omkit.metrics import mount_metrics
from omkit.settings import SettingsManager
from omkit import tenant
from omkit.tracing import instrument_fastapi

__all__ = [
    "build_tenant_client",
    "mount_metrics",
    "SettingsManager",
    "tenant",
    "instrument_fastapi",
]
