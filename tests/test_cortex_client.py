"""packages/omur-sdk/tests/test_cortex_client.py — packages/omur-sdk/tests/test_cortex_client.py.

Tests for CortexClient — all HTTP stubbed with respx.

exports: BASE | client() | test_embed_returns_vector(client) | test_embed_sends_correct_payload(client) | test_classify_returns_dict(client) | test_detect_language_returns_bcp47(client) | test_translate_returns_string(client) | test_embed_raises_on_http_error(client) | test_tenant_id_sent_as_header(client)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-04 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import json
import pytest
import respx
import httpx

from omur_sdk.cortex import CortexClient


BASE = "http://cortex-test:4000"


@pytest.fixture
def client():
    return CortexClient(base_url=BASE, api_key="test-key", tenant_id="tenant-abc")


@respx.mock
@pytest.mark.asyncio
async def test_embed_returns_vector(client):
    respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}]},
        )
    )
    result = await client.embed("hello world")
    assert result == [0.1, 0.2, 0.3]


@respx.mock
@pytest.mark.asyncio
async def test_embed_sends_correct_payload(client):
    route = respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"embedding": [1.0], "index": 0}]},
        )
    )
    await client.embed("test text")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "embed"
    assert sent["input"] == ["test text"]


@respx.mock
@pytest.mark.asyncio
async def test_classify_returns_dict(client):
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"category":"lab_result","confidence":0.9}'}}]
            },
        )
    )
    result = await client.classify("blood test results")
    assert result["category"] == "lab_result"


@respx.mock
@pytest.mark.asyncio
async def test_detect_language_returns_bcp47(client):
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"language":"ru"}'}}]
            },
        )
    )
    result = await client.detect_language("Привет мир")
    assert result == "ru"


@respx.mock
@pytest.mark.asyncio
async def test_translate_returns_string(client):
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"translated":"Hello world"}'}}]
            },
        )
    )
    result = await client.translate("Bonjour monde", target_lang="en")
    assert result == "Hello world"


@respx.mock
@pytest.mark.asyncio
async def test_embed_raises_on_http_error(client):
    respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(502, text="bad gateway")
    )
    with pytest.raises(Exception):
        await client.embed("text")


@respx.mock
@pytest.mark.asyncio
async def test_tenant_id_sent_as_header(client):
    route = respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"embedding": [1.0], "index": 0}]},
        )
    )
    await client.embed("text")
    assert route.calls[0].request.headers.get("x-tenant-id") == "tenant-abc"
