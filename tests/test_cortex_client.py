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
    """
    Rules:   The test assumes the API returns a specific JSON structure with 'embedding' and 'index' fields. Future developers must know that the response format is tightly coupled to this expectation.
    """
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
    """
    Rules:   The test assumes the API expects a specific payload format with 'model' and 'input' fields. Future developers must know that the request structure is fixed and must match the API contract.
    """
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
    """
    Rules:   The test assumes the API returns a specific JSON structure with a 'category' and 'confidence' field inside a 'content' string. Future developers must know that the response parsing logic depends on this exact format.
    """
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
    """
    Rules:   The test assumes the API returns a language code in BCP 47 format as a string. Future developers must know that the response format must match this expectation.
    """
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
    """
    Rules:   The test assumes the API returns a translated string inside a JSON object with a 'translated' key. Future developers must know that the response format is tightly coupled to this structure.
    """
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
    """
    Rules:   The test assumes that any HTTP error (like 502) will raise a generic Exception. Future developers must know that the exception type and handling logic may need to be updated if the client changes its error behavior.
    """
    respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(502, text="bad gateway")
    )
    with pytest.raises(Exception):
        await client.embed("text")


@respx.mock
@pytest.mark.asyncio
async def test_tenant_id_sent_as_header(client):
    """
    Rules:   The test assumes the client sends the tenant ID in a specific header 'x-tenant-id'. Future developers must know that the header name and value are hardcoded and must match the API's expectations.
    """
    route = respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"embedding": [1.0], "index": 0}]},
        )
    )
    await client.embed("text")
    assert route.calls[0].request.headers.get("x-tenant-id") == "tenant-abc"
