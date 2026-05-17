"""tests/test_valkeystream.py — Round-trip tests for valkeystream.

Skipped when `VALKEY_URL` is unset (mirrors `tests/test_registry_polling.py`).
When set, exercises XADD / XREADGROUP / XACK / XAUTOCLAIM against a real
Redis or Valkey instance.

exports: test_add_and_read | test_ack | test_claim_stale | test_payload_field_bytes
rules:   Tests require a reachable Valkey/Redis at `VALKEY_URL`; otherwise
         skipped. Each test uses a unique stream key and cleans up after
         itself.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial tests for Go port
message:
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from omkit.valkeystream import StreamConsumer, StreamMessage, StreamProducer


def _valkey_url() -> str:
    url = os.getenv("VALKEY_URL")
    if not url:
        pytest.skip("VALKEY_URL not set")
    return url


@pytest.fixture
async def client():
    import redis.asyncio as aioredis

    url = _valkey_url()
    r = aioredis.from_url(url)
    try:
        await r.ping()
    except Exception as exc:
        pytest.skip(f"Valkey not reachable at {url}: {exc}")
    yield r
    await r.aclose()


@pytest.fixture
def stream_key() -> str:
    return f"test-valkeystream-{uuid.uuid4().hex}"


@pytest.fixture
async def producer_consumer(client, stream_key):
    producer = StreamProducer(client, stream_key)
    consumer = StreamConsumer(
        client,
        stream_key,
        group="test-group",
        consumer="test-consumer-a",
        block_ms=200,
    )
    await consumer.ensure_group()
    yield producer, consumer
    await client.delete(stream_key)


@pytest.mark.asyncio
async def test_add_and_read(producer_consumer):
    producer, consumer = producer_consumer

    msg_id = await producer.add({"key": "value", "foo": "bar"})
    assert msg_id

    msgs = await consumer.read()
    assert len(msgs) == 1
    m = msgs[0]
    assert isinstance(m, StreamMessage)
    assert m.id == msg_id
    assert m.fields["key"] == b"value"
    assert m.fields["foo"] == b"bar"


@pytest.mark.asyncio
async def test_ack(producer_consumer, client, stream_key):
    producer, consumer = producer_consumer

    msg_id = await producer.add({"payload": "{}"})
    msgs = await consumer.read()
    assert len(msgs) == 1
    await consumer.ack(msg_id)

    # After ack, a fresh read on the same consumer with ">" sees no pending.
    msgs2 = await consumer.read()
    assert msgs2 == []


@pytest.mark.asyncio
async def test_claim_stale(client, stream_key):
    producer = StreamProducer(client, stream_key)
    consumer_a = StreamConsumer(
        client, stream_key, "g", "consumer-a", block_ms=100
    )
    consumer_b = StreamConsumer(
        client, stream_key, "g", "consumer-b", block_ms=100
    )
    await consumer_a.ensure_group()

    try:
        await producer.add({"payload": "p1"})
        read = await consumer_a.read()
        assert len(read) == 1

        # Wait so the message becomes idle, then claim from consumer-b.
        await asyncio.sleep(0.25)
        claimed = await consumer_b.claim_stale(idle_ms=100)
        assert len(claimed) == 1
        assert claimed[0].fields["payload"] == b"p1"
    finally:
        await client.delete(stream_key)


@pytest.mark.asyncio
async def test_payload_field_bytes(producer_consumer):
    """Bytes values should round-trip unchanged — wire-compat with Go."""
    producer, consumer = producer_consumer

    await producer.add({"payload": b'{"hello":"world"}'})
    msgs = await consumer.read()
    assert len(msgs) == 1
    assert msgs[0].fields["payload"] == b'{"hello":"world"}'
