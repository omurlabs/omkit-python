"""tests/test_http.py — tenant header auto-injection via event hook.

exports: test_injects_tenant_header_from_context() | test_omits_tenant_header_when_no_context() | test_explicit_tenant_header_wins()
rules:   The module must maintain backward compatibility with existing HTTP request handling while ensuring tenant header injection occurs only when context is explicitly provided. All test cases must validate header behavior in isolation without external dependencies. The transport mock implementation cannot alter global HTTP client configuration.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import pytest
import httpx

from omkit.http import build_tenant_client
from omkit.tenant import bind


def _mock_transport(captured: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_injects_tenant_header_from_context():
    """
    Rules:   When a tenant context is active, the tenant header is automatically injected into outgoing requests. Future developers must know that this behavior depends on the active context and that the header name is 'x-tenant-id'.
    """
    captured: dict = {}
    client = build_tenant_client(service_token="svc-tok", transport=_mock_transport(captured))
    try:
        with bind("tenant-abc"):
            resp = await client.get("http://up.test/ping")
    finally:
        await client.aclose()

    assert resp.status_code == 200
    assert captured["headers"].get("x-tenant-id") == "tenant-abc"
    assert captured["headers"].get("x-service-token") == "svc-tok"


@pytest.mark.asyncio
async def test_omits_tenant_header_when_no_context():
    """
    Rules:   When no tenant context is active, the tenant header is omitted from outgoing requests. Future developers must know that the absence of context results in no tenant header being added.
    """
    captured: dict = {}
    client = build_tenant_client(transport=_mock_transport(captured))
    try:
        await client.get("http://up.test/ping")
    finally:
        await client.aclose()

    assert "x-tenant-id" not in captured["headers"]


@pytest.mark.asyncio
async def test_explicit_tenant_header_wins():
    """
    Rules:   If an explicit 'X-Tenant-ID' header is provided in the request, it overrides the automatically injected tenant header from the context. Future developers must know that explicit headers take precedence over context-based ones.
    """
    captured: dict = {}
    client = build_tenant_client(transport=_mock_transport(captured))
    try:
        with bind("tenant-abc"):
            await client.get("http://up.test/ping", headers={"X-Tenant-ID": "override"})
    finally:
        await client.aclose()

    assert captured["headers"].get("x-tenant-id") == "override"
