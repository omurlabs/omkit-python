"""Unit tests for omur_sdk.jobqueue.streaq.

Avoids spinning up an actual streaq Worker / Valkey by exercising the
middleware, enqueue helper, and Prometheus collector in isolation. The
full Worker contract is covered upstream in streaq's own tests.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from omur_sdk import tenant
from omur_sdk.jobqueue import wrap
from omur_sdk.jobqueue.envelope import InvalidEnvelopeError
from omur_sdk.jobqueue.streaq import (
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_TRIES,
    DEFAULT_TIMEOUT_SECONDS,
    StreaqPromCollector,
    enqueue,
    tenant_middleware,
)

TENANT = "11111111-1111-1111-1111-111111111111"


# ─────────────────────────────────────────────────────────────────────
# Defaults — surface contract
# ─────────────────────────────────────────────────────────────────────


def test_defaults_match_spec() -> None:
    assert DEFAULT_CONCURRENCY == 4
    assert DEFAULT_MAX_TRIES == 3
    assert DEFAULT_TIMEOUT_SECONDS == 300


# ─────────────────────────────────────────────────────────────────────
# tenant_middleware — happy path + failures
# ─────────────────────────────────────────────────────────────────────


def test_tenant_middleware_unwraps_and_binds() -> None:
    received: dict[str, object] = {}

    async def handler(payload: dict) -> str:
        received["payload"] = payload
        received["tenant"] = tenant.current_or_none()
        return "ok"

    wrapped = tenant_middleware(handler)
    envelope_dict = json.loads(wrap(TENANT, {"doc_id": "abc", "stage": "parse"}))

    result = asyncio.run(wrapped(envelope_dict))

    assert result == "ok"
    assert received["payload"] == {"doc_id": "abc", "stage": "parse"}
    assert received["tenant"] == TENANT


def test_tenant_middleware_unbinds_after_handler() -> None:
    async def handler(payload: dict) -> None:
        return None

    wrapped = tenant_middleware(handler)
    envelope_dict = json.loads(wrap(TENANT, {"x": 1}))

    asyncio.run(wrapped(envelope_dict))

    # Outside the handler, the tenant ContextVar must be unset.
    assert tenant.current_or_none() is None


def test_tenant_middleware_rejects_no_args() -> None:
    async def handler(payload: dict) -> None:
        pytest.fail("handler should not be called")

    wrapped = tenant_middleware(handler)
    with pytest.raises(InvalidEnvelopeError):
        asyncio.run(wrapped())


def test_tenant_middleware_rejects_malformed_envelope() -> None:
    async def handler(payload: dict) -> None:
        pytest.fail("handler should not be called")

    wrapped = tenant_middleware(handler)
    with pytest.raises(InvalidEnvelopeError):
        # Missing version key — Envelope.validate() rejects.
        asyncio.run(wrapped({"tenant_id": TENANT, "payload": {"x": 1}}))


def test_tenant_middleware_rejects_non_uuid_tenant() -> None:
    async def handler(payload: dict) -> None:
        pytest.fail("handler should not be called")

    wrapped = tenant_middleware(handler)
    with pytest.raises(InvalidEnvelopeError):
        asyncio.run(wrapped({"version": 1, "tenant_id": "not-a-uuid", "payload": {"x": 1}}))


def test_tenant_middleware_passes_extra_args() -> None:
    received: list[object] = []

    async def handler(payload: dict, *args: object, **kwargs: object) -> None:
        received.append(payload)
        received.append(args)
        received.append(kwargs)

    wrapped = tenant_middleware(handler)
    envelope_dict = json.loads(wrap(TENANT, {"a": 1}))

    asyncio.run(wrapped(envelope_dict, "extra1", kw="x"))

    assert received[0] == {"a": 1}
    assert received[1] == ("extra1",)
    assert received[2] == {"kw": "x"}


# ─────────────────────────────────────────────────────────────────────
# enqueue helper
# ─────────────────────────────────────────────────────────────────────


def test_enqueue_wraps_payload_in_envelope() -> None:
    captured: list[object] = []

    class FakeTask:
        async def enqueue(self, *args: object, **kwargs: object) -> str:
            captured.append(args)
            captured.append(kwargs)
            return "fake-task-id"

    async def runner() -> str:
        return await enqueue(FakeTask(), TENANT, {"doc_id": "abc"}, foo="bar")

    result = asyncio.run(runner())
    assert result == "fake-task-id"
    args, _kwargs = captured[0], captured[1]
    envelope = args[0]
    assert envelope["version"] == 1
    assert envelope["tenant_id"] == TENANT
    assert envelope["payload"] == {"doc_id": "abc"}
    assert _kwargs == {"foo": "bar"}


def test_enqueue_rejects_invalid_tenant() -> None:
    class FakeTask:
        async def enqueue(self, *args: object, **kwargs: object) -> str:
            pytest.fail("should not enqueue with bad tenant")
            return ""

    async def runner() -> None:
        await enqueue(FakeTask(), "not-a-uuid", {"x": 1})

    with pytest.raises(InvalidEnvelopeError):
        asyncio.run(runner())


# ─────────────────────────────────────────────────────────────────────
# StreaqPromCollector
# ─────────────────────────────────────────────────────────────────────


class _FakeWorker:
    """Just enough surface for the collector. Mirrors streaq.Worker."""

    def __init__(self, queue_name: str = "marrow", **counters: int) -> None:
        self.queue_name = queue_name
        self.counters = counters


def test_prom_collector_emits_six_gauges() -> None:
    worker = _FakeWorker(
        queue_name="marrow",
        completed=42,
        failed=2,
        running=1,
        retried=3,
        aborted=0,
        relinquished=0,
    )
    collector = StreaqPromCollector(worker)
    metrics = list(collector.collect())

    names = sorted(m.name for m in metrics)
    assert names == [
        "streaq_worker_aborted",
        "streaq_worker_completed",
        "streaq_worker_failed",
        "streaq_worker_relinquished",
        "streaq_worker_retried",
        "streaq_worker_running",
    ]

    by_name = {m.name: m for m in metrics}
    completed = by_name["streaq_worker_completed"].samples[0]
    assert completed.value == 42.0
    assert completed.labels == {"queue": "marrow"}


def test_prom_collector_handles_missing_counters() -> None:
    """A freshly constructed Worker may not have populated counters yet."""
    worker = _FakeWorker(queue_name="empty")
    collector = StreaqPromCollector(worker)
    metrics = list(collector.collect())
    assert len(metrics) == 6
    for m in metrics:
        assert m.samples[0].value == 0.0
        assert m.samples[0].labels == {"queue": "empty"}


def test_prom_collector_describe_is_empty() -> None:
    """describe() returning [] is allowed by prometheus_client; collect()
    runs on every scrape regardless. Verifies no static-name surface."""
    collector = StreaqPromCollector(_FakeWorker())
    assert list(collector.describe()) == []


# ─────────────────────────────────────────────────────────────────────
# Cross-language envelope round-trip
# ─────────────────────────────────────────────────────────────────────


def test_envelope_roundtrip_through_middleware() -> None:
    """The bytes produced by `wrap()` (cross-SDK contract) decode cleanly
    into a dict that `tenant_middleware` accepts. Catches future drift
    between Envelope.model_dump_json() and Envelope.model_validate()."""
    tid = str(uuid.uuid4())
    raw = wrap(tid, {"doc_id": "abc"})
    envelope_dict = json.loads(raw)

    received: dict[str, object] = {}

    async def handler(payload: dict) -> None:
        received["payload"] = payload
        received["tenant"] = tenant.current_or_none()

    asyncio.run(tenant_middleware(handler)(envelope_dict))
    assert received["payload"] == {"doc_id": "abc"}
    assert received["tenant"] == tid
