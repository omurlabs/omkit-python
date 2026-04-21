"""Tenant-aware httpx.AsyncClient factory.

Callers construct one long-lived client per service (NOT per request) via
``build_tenant_client`` and rely on the attached ``event_hook`` to inject
``X-Tenant-ID`` from the SDK tenant context on every outbound request. This
removes a whole class of bugs where ad-hoc per-request clients forgot the
header and silently stripped tenant context.

Example:
    from omur_sdk.http import build_tenant_client
    client = build_tenant_client(service_token=settings.omur_tenant_token)

    async def query_upstream(body):
        # Tenant header is injected automatically from the current context.
        resp = await client.post("http://svc:8080/q", json=body)
        resp.raise_for_status()
        return resp.json()
"""
from __future__ import annotations

from typing import Any

import httpx

from omur_sdk.tenant import current_or_none, request_id


def _build_request_hook(service_token: str | None):
    """Return an httpx event hook that sets tenant + service-token headers.

    The hook respects caller-set headers: if X-Tenant-ID was already present
    on the request, we leave it alone. This preserves escape hatches like
    'I am making a deliberate cross-tenant admin call'.
    """

    async def _hook(request: httpx.Request) -> None:
        if "X-Tenant-ID" not in request.headers:
            tid = current_or_none()
            if tid:
                request.headers["X-Tenant-ID"] = tid
        if service_token and "X-Service-Token" not in request.headers:
            request.headers["X-Service-Token"] = service_token
        if "X-Request-ID" not in request.headers:
            rid = request_id()
            if rid:
                request.headers["X-Request-ID"] = rid

    return _hook


def build_tenant_client(
    *,
    service_token: str | None = None,
    timeout: float = 30.0,
    limits: httpx.Limits | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Return a long-lived ``httpx.AsyncClient`` that auto-injects the SDK
    tenant header (and optionally the service token and request ID) on every
    outbound call.

    Call sites own the lifecycle: ``await client.aclose()`` on shutdown.
    """
    hook = _build_request_hook(service_token)
    event_hooks = kwargs.pop("event_hooks", {"request": []})
    request_hooks = list(event_hooks.get("request", []))
    request_hooks.append(hook)
    event_hooks["request"] = request_hooks

    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits or httpx.Limits(max_connections=100, max_keepalive_connections=20),
        event_hooks=event_hooks,
        **kwargs,
    )
