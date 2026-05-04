"""packages/omur-sdk/omur_sdk/metrics.py — Shared Prometheus metrics wiring for FastAPI services.

Usage:
    from omur_sdk.metrics import mount_metrics
    mount_metrics(app, "spine")  # exposes /metrics, instruments all routes

exports: mount_metrics(app, service_name)
rules:   The metrics module must maintain backward compatibility with all existing metric collection patterns and cannot introduce breaking changes to the public API. All metric collection must be thread-safe and non-blocking to prevent performance degradation of the main application. The module cannot have any external dependencies beyond what's already defined in the project's requirements.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def mount_metrics(app: "FastAPI", service_name: str) -> None:
    """Wire prometheus-fastapi-instrumentator with default labels and a /metrics endpoint.

    Idempotent: calling twice on the same app is a no-op.

    Rules:   The function requires the 'prometheus-fastapi-instrumentator' package to be installed, and the app parameter must be a FastAPI instance that supports the '_omur_metrics_mounted' attribute for idempotency checks.
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
