"""Shared Prometheus metrics wiring for FastAPI services.

Usage:
    from omkit.metrics import mount_metrics
    mount_metrics(app, "my-service")  # exposes /metrics, instruments all routes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def mount_metrics(app: "FastAPI", service_name: str) -> None:
    """Wire prometheus-fastapi-instrumentator with default labels and a /metrics endpoint.

    Idempotent: calling twice on the same app is a no-op.

    Rules:   The function requires the 'prometheus-fastapi-instrumentator' package to be installed, and the app parameter must be a FastAPI instance that supports the '_omkit_metrics_mounted' attribute for idempotency checks.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError as e:
        raise ImportError(
            "prometheus-fastapi-instrumentator is required. "
            "Install with: pip install omkit[metrics]"
        ) from e

    if getattr(app, "_omkit_metrics_mounted", False):
        return

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/health", "/ready"],
    ).instrument(app, metric_namespace="omur", metric_subsystem=service_name).expose(app)

    app._omkit_metrics_mounted = True
