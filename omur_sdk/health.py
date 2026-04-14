"""Shared health and readiness endpoints for Omur services.

Usage:
    from omur_sdk.health import mount_health_endpoints
    mount_health_endpoints(app, "spine", APP_VERSION, ready_check=_check_db)

The ready_check is an async callable returning dict[str, str].
Values of "ok" mean healthy; anything else is treated as an error message.
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
    """Mount /health and /ready endpoints on a FastAPI app."""

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "service": service_name, "version": version}

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
