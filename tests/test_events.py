"""Tests for EventBus SDK primitive."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from omur_sdk.events import EventBus


@pytest.fixture
def redis_client():
    client = MagicMock()
    client.xadd = AsyncMock()
    client.xread = AsyncMock()
    client.xack = AsyncMock()
    return client


@pytest.fixture
def bus(redis_client):
    return EventBus(redis_client, service_name="test-service")


@pytest.mark.asyncio
async def test_publish_adds_to_stream(bus, redis_client):
    redis_client.xadd.return_value = "1234-0"
    msg_id = await bus.publish("user.created", {"user_id": "abc"})
    assert msg_id == "1234-0"
    redis_client.xadd.assert_called_once()
    call_args = redis_client.xadd.call_args
    stream_key = call_args[0][0]
    assert stream_key == "omur:events:user.created"
    fields = call_args[0][1]
    assert "payload" in fields
    payload = json.loads(fields["payload"])
    assert payload["user_id"] == "abc"


@pytest.mark.asyncio
async def test_publish_includes_source_service(bus, redis_client):
    redis_client.xadd.return_value = "1234-0"
    await bus.publish("order.placed", {"order_id": "xyz"})
    call_args = redis_client.xadd.call_args
    fields = call_args[0][1]
    payload = json.loads(fields["payload"])
    assert payload["source"] == "test-service"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_consume_returns_parsed_events(bus, redis_client):
    raw_payload = json.dumps({"user_id": "abc", "source": "test-service", "timestamp": 1234567890.0})
    redis_client.xread.return_value = [
        (b"omur:events:user.created", [
            (b"1234-0", {b"payload": raw_payload.encode()}),
            (b"1235-0", {b"payload": raw_payload.encode()}),
        ])
    ]
    results = await bus.consume("user.created", last_id="0-0", count=10)
    assert len(results) == 2
    assert results[0]["msg_id"] == b"1234-0"
    assert results[0]["data"]["user_id"] == "abc"
    assert results[1]["msg_id"] == b"1235-0"


@pytest.mark.asyncio
async def test_consume_empty_stream(bus, redis_client):
    redis_client.xread.return_value = None
    results = await bus.consume("user.created")
    assert results == []


@pytest.mark.asyncio
async def test_consume_empty_list(bus, redis_client):
    redis_client.xread.return_value = []
    results = await bus.consume("user.created")
    assert results == []


@pytest.mark.asyncio
async def test_ack_calls_xack(bus, redis_client):
    await bus.ack("user.created", "my-group", "1234-0")
    redis_client.xack.assert_called_once_with("omur:events:user.created", "my-group", "1234-0")
