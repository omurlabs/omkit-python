"""Tests for CerebellumClient — circuit breaker, batch splitting, fallback."""

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
