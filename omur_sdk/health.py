"""packages/omur-sdk/omur_sdk/health.py — Shared health and readiness endpoints for Omur services.

Usage:
    from omur_sdk.health import mount_health_endpoints
    mount_health_endpoints(app, "spine", APP_VERSION, ready_check=_check_db)

The ready_check is an async callable returning dict[str, str].
Values of "ok" mean healthy; anything else is treated as an error message.

exports: mount_health_endpoints(app, service_name, version, ready_check)
used_by: none
rules:   The health endpoint mounting function must be called exactly once during application startup and cannot be reconfigured or called again. The `ready_check` parameter must be a synchronous function that returns a boolean value indicating service readiness. All health endpoints must be registered under the `/health` path prefix and follow the standard Kubernetes liveness/readiness probe response format.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from typing import Awaitable, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def mount_health_endpoints(
    app: FastAPI,
    service_name: str,
    version: str,
    ready_check: Callable[[], Awaitable[dict[str, str]]] | None = None,
) -> None:
    """Mount /health, /healthz (liveness alias) and /ready endpoints.

    Rules:   Service name must be unique across deployments to avoid conflicts in health monitoring. Ready check function must return a dict with string values to ensure proper health status reporting.
    """

    async def _liveness() -> dict:
        return {"status": "ok", "service": service_name, "version": version}

    # /health and /healthz are aliases — /healthz matches k8s liveness-probe
    # convention; /health is retained for callers that pre-date that.
    app.add_api_route("/health", _liveness, methods=["GET"], tags=["meta"])
    app.add_api_route("/healthz", _liveness, methods=["GET"], tags=["meta"])

    @app.get("/ready", tags=["meta"])
    async def readiness():
        if ready_check is None:
            return {"status": "ready", "service": service_name, "version": version}

        checks = await ready_check()
        all_ok = all(v == "ok" for v in checks.values())
        status = "ready" if all_ok else "not_ready"
        status_code = 200 if all_ok else 503
        return JSONResponse(
            {"status": status, "service": service_name, "version": version, "checks": checks},
            status_code=status_code,
        )
