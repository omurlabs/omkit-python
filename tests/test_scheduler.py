"""tests/test_scheduler.py — Tests for omkit.scheduler.

Stub SchedulerBackend + ProviderSource so the suite runs without Postgres
or a real cron engine. Covers:

  * initial reconcile registers desired rows
  * removal of a row unregisters it next reconcile
  * config change re-registers (hash drift)
  * derive_cron returning ok=False skips a row
  * fetch_providers errors don't crash the loop
  * enqueuer fires once per new registration

exports: test_*
rules:   Stub backend MUST mirror the SchedulerBackend Protocol contract
         (return entry_id from register, raise on unregister of unknown id
         only if you want to test that path).
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/scheduler
message:
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omkit.scheduler import (
    Provider,
    Scheduler,
)


class StubBackend:
    def __init__(self):
        self.registered: dict[str, tuple[str, str, bytes, str]] = {}
        self._next_id = 0
        self.started = False
        self.shutdown_called = False
        self.unregister_calls: list[str] = []

    async def register(self, cronspec, task_type, body, *, queue):
        self._next_id += 1
        entry_id = f"e{self._next_id}"
        self.registered[entry_id] = (cronspec, task_type, body, queue)
        return entry_id

    async def unregister(self, entry_id):
        self.unregister_calls.append(entry_id)
        self.registered.pop(entry_id, None)

    async def start(self):
        self.started = True

    async def shutdown(self):
        self.shutdown_called = True


class StubSource:
    def __init__(self, rows: list[Provider], *, error: bool = False):
        self.rows = rows
        self.error = error
        self.fetch_count = 0

    async def fetch_providers(self, kind):
        self.fetch_count += 1
        if self.error:
            raise RuntimeError("source down")
        return list(self.rows)


class StubEnqueuer:
    def __init__(self):
        self.calls: list[tuple[str, str, Any, str]] = []

    async def enqueue(self, task_type, tenant_id, payload, *, queue):
        self.calls.append((task_type, tenant_id, payload, queue))


def _always_minute(_: Provider) -> tuple[str, bool]:
    return ("@every 1m", True)


TID_A = "11111111-1111-1111-1111-111111111111"
TID_B = "22222222-2222-2222-2222-222222222222"


@pytest.mark.asyncio
async def test_start_runs_initial_reconcile():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {})])
    s = Scheduler(
        backend,
        src,
        kind="collector",
        queue="scheduler",
        task_type="scheduler:provider-sync",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()
    try:
        assert backend.started
        assert len(backend.registered) == 1
        assert s.entries() == [f"{TID_A}:openai"]
    finally:
        await s.stop()
    assert backend.shutdown_called


@pytest.mark.asyncio
async def test_removed_row_unregisters_on_next_reconcile():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {})])
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()
    try:
        assert s.entries() == [f"{TID_A}:openai"]
        src.rows = []
        await s._reconcile()  # noqa: SLF001 — direct call to avoid timing flake
        assert s.entries() == []
        assert len(backend.unregister_calls) == 1
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_config_change_reregisters():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {"region": "us"})])
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()
    try:
        first_id = next(iter(backend.registered.keys()))
        src.rows = [Provider(TID_A, "openai", {"region": "eu"})]
        await s._reconcile()
        assert first_id in backend.unregister_calls
        assert len(backend.registered) == 1
        assert next(iter(backend.registered.keys())) != first_id
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_derive_cron_skip_does_not_register():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "ghost", {})])

    def derive_skip(_):
        return ("", False)

    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=derive_skip,
        poll_interval=60.0,
    )
    await s.start()
    try:
        assert len(backend.registered) == 0
        assert s.entries() == []
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_fetch_error_does_not_crash_loop():
    backend = StubBackend()
    src = StubSource([], error=True)
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()  # initial reconcile swallows the error
    try:
        assert s.entries() == []
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_enqueuer_fires_on_new_registration():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {"k": "v"})])
    enq = StubEnqueuer()
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
        enqueuer=enq,
    )
    await s.start()
    try:
        assert len(enq.calls) == 1
        task_type, tenant_id, payload, queue = enq.calls[0]
        assert task_type == "t"
        assert tenant_id == TID_A
        assert payload["provider_name"] == "openai"
        assert queue == "q"

        # Re-reconcile with same config → no second enqueue (hash unchanged).
        await s._reconcile()
        assert len(enq.calls) == 1
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_register_body_is_envelope_wrapped():
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {})])
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()
    try:
        _, _, body, _ = next(iter(backend.registered.values()))
        # Body is JSON envelope: contains tenant_id, version, payload.
        text = body.decode("utf-8")
        assert TID_A in text
        assert '"version":1' in text
        assert "provider_name" in text
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_multi_tenant_keys_distinct():
    backend = StubBackend()
    src = StubSource(
        [
            Provider(TID_A, "openai", {}),
            Provider(TID_B, "openai", {}),
        ]
    )
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=60.0,
    )
    await s.start()
    try:
        assert set(s.entries()) == {f"{TID_A}:openai", f"{TID_B}:openai"}
    finally:
        await s.stop()


@pytest.mark.asyncio
async def test_loop_ticks_after_interval(monkeypatch):
    backend = StubBackend()
    src = StubSource([Provider(TID_A, "openai", {})])
    s = Scheduler(
        backend,
        src,
        kind="k",
        queue="q",
        task_type="t",
        derive_cron=_always_minute,
        poll_interval=0.05,
    )
    await s.start()
    try:
        baseline = src.fetch_count
        await asyncio.sleep(0.18)  # ~3 ticks
        assert src.fetch_count > baseline
    finally:
        await s.stop()
