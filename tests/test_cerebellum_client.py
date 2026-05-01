"""packages/omur-sdk/tests/test_cerebellum_client.py — circuit breaker, batch splitting, fallback.

exports: client() | test_available_when_healthy(client) | test_circuit_opens_after_failures(client) | test_circuit_closes_after_cooldown(client) | test_batch_splitting() | test_embed_returns_none_when_unavailable(client) | test_disabled_returns_none() | test_post_sends_tenant_header_from_contextvar(client) | test_post_explicit_tenant_id_wins_over_contextvar(client) | test_post_omits_tenant_header_when_both_unset(client) | test_post_sends_service_token_header() | test_post_omits_service_token_when_unset() | test_rerank_returns_full_response_dict(client) | test_rerank_short_circuits_empty_passages(client) | test_rerank_returns_none_on_5xx(client) | test_rerank_returns_none_on_timeout(client) | test_rerank_returns_none_when_circuit_open(client)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from omur_sdk.cerebellum_client import CerebellumClient


@pytest.fixture
def client():
    return CerebellumClient(
        base_url="http://cerebellum:8006",
        timeout=5.0,
        failure_threshold=3,
        cooldown_seconds=10,
    )


@pytest.mark.asyncio
async def test_available_when_healthy(client):
    assert client.available is True


@pytest.mark.asyncio
async def test_circuit_opens_after_failures(client):
    """Circuit should open after N consecutive failures."""
    for _ in range(3):
        client._record_failure()
    assert client.available is False


@pytest.mark.asyncio
async def test_circuit_closes_after_cooldown(client):
    for _ in range(3):
        client._record_failure()
    assert client.available is False
    # Simulate cooldown passed
    client._circuit_opened_at = 0  # epoch = long time ago
    assert client.available is True  # half-open


def test_batch_splitting():
    """Batches > 32 should be split."""
    client = CerebellumClient(base_url="http://cerebellum:8006")
    batches = client._split_batch(list(range(50)), max_size=32)
    assert len(batches) == 2
    assert len(batches[0]) == 32
    assert len(batches[1]) == 18


@pytest.mark.asyncio
async def test_embed_returns_none_when_unavailable(client):
    """When circuit is open, embed should return None."""
    for _ in range(3):
        client._record_failure()
    result = await client.embed(["test"])
    assert result is None


@pytest.mark.asyncio
async def test_disabled_returns_none():
    client = CerebellumClient(base_url="http://cerebellum:8006", enabled=False)
    result = await client.embed(["test"])
    assert result is None


# --- Tenant header propagation (X-Tenant-ID) ---

def _mock_response(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_post_sends_tenant_header_from_contextvar(client):
    """When no tenant_id is passed, _post should pull it from the SDK contextvar."""
    from omur_sdk.tenant import _tenant_id_var

    tid = "11111111-1111-1111-1111-111111111111"
    token = _tenant_id_var.set(tid)
    try:
        mock_post = AsyncMock(return_value=_mock_response({"embeddings": [[0.1]]}))
        with patch.object(client, "_get_client") as mock_get_client:
            mock_get_client.return_value = MagicMock(post=mock_post)
            result = await client._post("/embed", {"texts": ["hi"]})
        assert result == {"embeddings": [[0.1]]}
        _, kwargs = mock_post.call_args
        assert kwargs["headers"].get("X-Tenant-ID") == tid
    finally:
        _tenant_id_var.reset(token)


@pytest.mark.asyncio
async def test_post_explicit_tenant_id_wins_over_contextvar(client):
    """Explicit tenant_id argument should override the contextvar."""
    from omur_sdk.tenant import _tenant_id_var

    ctx_tid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    explicit_tid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    token = _tenant_id_var.set(ctx_tid)
    try:
        mock_post = AsyncMock(return_value=_mock_response({"ok": True}))
        with patch.object(client, "_get_client") as mock_get_client:
            mock_get_client.return_value = MagicMock(post=mock_post)
            await client._post("/embed", {"texts": ["hi"]}, tenant_id=explicit_tid)
        _, kwargs = mock_post.call_args
        assert kwargs["headers"].get("X-Tenant-ID") == explicit_tid
    finally:
        _tenant_id_var.reset(token)


@pytest.mark.asyncio
async def test_post_omits_tenant_header_when_both_unset(client):
    """No contextvar and no explicit arg => no X-Tenant-ID header (caller handles 401)."""
    from omur_sdk.tenant import _tenant_id_var

    # Defensively ensure contextvar is unset for this test.
    token = _tenant_id_var.set(None)
    try:
        mock_post = AsyncMock(return_value=_mock_response({"ok": True}))
        with patch.object(client, "_get_client") as mock_get_client:
            mock_get_client.return_value = MagicMock(post=mock_post)
            await client._post("/embed", {"texts": ["hi"]})
        _, kwargs = mock_post.call_args
        assert "X-Tenant-ID" not in kwargs["headers"]
    finally:
        _tenant_id_var.reset(token)


# --- Service token forwarding (X-Service-Token) ---


@pytest.mark.asyncio
async def test_post_sends_service_token_header():
    """When constructed with service_token, _post should forward X-Service-Token."""
    client = CerebellumClient(base_url="http://cb.test", service_token="secret-abc")
    mock_post = AsyncMock(return_value=_mock_response({"results": []}))
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        await client._post("/ner", {"texts": ["hello"]}, tenant_id="t-1")
    _, kwargs = mock_post.call_args
    assert kwargs["headers"].get("X-Service-Token") == "secret-abc"
    assert kwargs["headers"].get("X-Tenant-ID") == "t-1"


@pytest.mark.asyncio
async def test_post_omits_service_token_when_unset():
    """No service_token on constructor => no X-Service-Token header."""
    client = CerebellumClient(base_url="http://cb.test")
    mock_post = AsyncMock(return_value=_mock_response({"results": []}))
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        await client._post("/ner", {"texts": ["hello"]}, tenant_id="t-1")
    _, kwargs = mock_post.call_args
    assert "X-Service-Token" not in kwargs["headers"]


# --- rerank() helper ---


@pytest.mark.asyncio
async def test_rerank_returns_full_response_dict(client):
    """Happy path: rerank returns the server payload verbatim."""
    payload = {
        "results": [
            {"index": 1, "score": 0.9, "truncated": False},
            {"index": 0, "score": 0.2, "truncated": False},
        ],
        "model": "bge-reranker-base",
    }
    mock_post = AsyncMock(return_value=_mock_response(payload))
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        result = await client.rerank("aspirin", ["banana", "aspirin 100mg"], top_k=2)
    assert result == payload
    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert body == {"query": "aspirin", "passages": ["banana", "aspirin 100mg"], "top_k": 2}


@pytest.mark.asyncio
async def test_rerank_short_circuits_empty_passages(client):
    """Empty passages must NOT hit the wire — return an empty result locally."""
    mock_post = AsyncMock()
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        result = await client.rerank("q", [], top_k=5)
    assert result == {"results": [], "model": ""}
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_rerank_returns_none_on_5xx(client):
    """A 5xx response must surface as None so frontal falls back to
    pre-rerank order rather than failing the RAG request."""
    import httpx

    err = httpx.HTTPStatusError(
        "boom",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    failing_resp = MagicMock()
    failing_resp.status_code = 500
    failing_resp.raise_for_status = MagicMock(side_effect=err)
    mock_post = AsyncMock(return_value=failing_resp)
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        result = await client.rerank("q", ["p1", "p2"], top_k=1)
    assert result is None


@pytest.mark.asyncio
async def test_rerank_returns_none_on_timeout(client):
    """Timeout path must also surface as None (same fallback contract)."""
    import httpx

    mock_post = AsyncMock(side_effect=httpx.TimeoutException("slow"))
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        result = await client.rerank("q", ["p1"], top_k=1)
    assert result is None


@pytest.mark.asyncio
async def test_rerank_returns_none_when_circuit_open(client):
    """Circuit open => rerank returns None without issuing a request."""
    for _ in range(3):
        client._record_failure()
    mock_post = AsyncMock()
    with patch.object(client, "_get_client") as mock_get_client:
        mock_get_client.return_value = MagicMock(post=mock_post)
        result = await client.rerank("q", ["p1"], top_k=1)
    assert result is None
    mock_post.assert_not_called()
