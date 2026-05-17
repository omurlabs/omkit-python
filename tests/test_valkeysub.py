"""tests/test_valkeysub.py — Round-trip tests for valkeysub.

Skipped when `VALKEY_URL` is unset (mirrors `tests/test_registry_polling.py`).
When set, publishes via a separate client and verifies the subscriber
yields the payload bytes.

exports: test_subscriber_receives_published_message | test_default_backoff
rules:   Tests require a reachable Valkey/Redis at `VALKEY_URL`; otherwise
         skipped. Subscriber lifecycle is bounded by `asyncio.wait_for` to
         avoid hangs on regression.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial tests for Go port
message:
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from omkit.valkeysub import Subscriber


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


def test_default_backoff():
    """Constructor records the configured backoff (no I/O)."""
    sub = Subscriber.__new__(Subscriber)
    Subscriber.__init__(sub, client=None, channel="x")  # type: ignore[arg-type]
    assert sub.reconnect_backoff_s == 1.0

    sub2 = Subscriber.__new__(Subscriber)
    Subscriber.__init__(
        sub2, client=None, channel="x", reconnect_backoff_s=2.5  # type: ignore[arg-type]
    )
    assert sub2.reconnect_backoff_s == 2.5


@pytest.mark.asyncio
async def test_subscriber_receives_published_message(client):
    channel = f"test-valkeysub-{uuid.uuid4().hex}"
    sub = Subscriber(client, channel, reconnect_backoff_s=0.1)

    received: list[bytes] = []

    async def consume() -> None:
        async for payload in sub.messages():
            received.append(payload)
            if received:
                break

    task = asyncio.create_task(consume())

    # Let the subscribe call register before publishing.
    for _ in range(20):
        await asyncio.sleep(0.05)
        n = await client.publish(channel, b"hello-world")
        if n > 0:
            break

    try:
        await asyncio.wait_for(task, timeout=3.0)
    except asyncio.TimeoutError:
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task
        pytest.fail("subscriber did not receive message in time")

    assert received == [b"hello-world"]
