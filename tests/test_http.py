"""packages/omur-sdk/tests/test_http.py — tenant header auto-injection via event hook.

exports: test_injects_tenant_header_from_context() | test_omits_tenant_header_when_no_context() | test_explicit_tenant_header_wins()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import pytest
import httpx

from omur_sdk.http import build_tenant_client
from omur_sdk.tenant import bind


def _mock_transport(captured: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_injects_tenant_header_from_context():
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
    captured: dict = {}
    client = build_tenant_client(transport=_mock_transport(captured))
    try:
        await client.get("http://up.test/ping")
    finally:
        await client.aclose()

    assert "x-tenant-id" not in captured["headers"]


@pytest.mark.asyncio
async def test_explicit_tenant_header_wins():
    captured: dict = {}
    client = build_tenant_client(transport=_mock_transport(captured))
    try:
        with bind("tenant-abc"):
            await client.get("http://up.test/ping", headers={"X-Tenant-ID": "override"})
    finally:
        await client.aclose()

    assert captured["headers"].get("x-tenant-id") == "override"
