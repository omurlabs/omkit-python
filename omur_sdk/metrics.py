"""Shared Prometheus metrics wiring for FastAPI services.

Usage:
    from omur_sdk.metrics import mount_metrics
    mount_metrics(app, "spine")  # exposes /metrics, instruments all routes
"""

from fastapi import FastAPI


def mount_metrics(app: FastAPI, service_name: str) -> None:
    """Wire prometheus-fastapi-instrumentator with default labels and a /metrics endpoint.

    Idempotent: calling twice on the same app is a no-op.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError as e:
        raise ImportError(
            "prometheus-fastapi-instrumentator is required. "
            "Install with: pip install omur-sdk[metrics]"
        ) from e

    if getattr(app, "_omur_metrics_mounted", False):
        return

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/health", "/ready"],
    ).instrument(app, metric_namespace="omur", metric_subsystem=service_name).expose(app)

    app._omur_metrics_mounted = True
