"""packages/omur-sdk/omkit/health.py — Shared health and readiness endpoints for Omur services.

Usage:
    from omkit.health import mount_health_endpoints
    mount_health_endpoints(app, "spine", APP_VERSION, ready_check=_check_db)

Mounted paths:
    /health, /healthz  — liveness (process up; never depends on external deps)
    /ready,  /readyz   — readiness (deps reachable; orchestrator routes traffic when 200)

`ready_check` is an async callable returning `dict[str, str]`.
Values of "ok" mean healthy; anything else is an error message and the
endpoint returns HTTP 503 with status="not_ready".

exports: mount_health_endpoints(app, service_name, version, ready_check)
rules:   Liveness handlers must never call external dependencies — they only confirm the process is running. Readiness handlers may call dependencies but must complete fast (under 3s); a slow dependency must surface as not_ready, not as a hung probe. Both /health/ and /healthz/ paths must always be 200 once the process accepts connections, even when readiness is failing.
agent:   claude-opus-4-7 | anthropic | 2026-05-03 | track-9-health-ready-audit | extend with /readyz alias and clarify liveness vs readiness contract
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
    """Mount /health, /healthz (liveness) and /ready, /readyz (readiness) endpoints.

    Liveness paths return 200 unconditionally — they only signal the process is
    up. Readiness paths run the optional ready_check and return 503 if any
    component reports anything other than "ok".

    Rules:   The ready_check function must return a dict[str, str] where each value should indicate the health status of a component, and any value other than 'ok' will result in a 503 response for readiness endpoints.
    """

    async def _liveness() -> dict:
        return {"status": "ok", "service": service_name, "version": version}

    async def _readiness():
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

    # /health + /healthz are liveness aliases. /healthz matches the k8s
    # convention; /health is retained for callers that pre-date that.
    app.add_api_route("/health", _liveness, methods=["GET"], tags=["meta"])
    app.add_api_route("/healthz", _liveness, methods=["GET"], tags=["meta"])

    # /ready + /readyz are readiness aliases. /readyz matches the k8s
    # convention; /ready is retained for callers that pre-date that.
    app.add_api_route("/ready", _readiness, methods=["GET"], tags=["meta"])
    app.add_api_route("/readyz", _readiness, methods=["GET"], tags=["meta"])
