"""Tests for on-demand model loading with TTL-based idle unload."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from omur_sdk.model_lifecycle import ModelLifecycle, ModelRegistry


class FakeLifecycle(ModelLifecycle):
    """Concrete test implementation."""

    def __init__(self, name: str = "fake", load_time: float = 0):
        super().__init__(name)
        self._load_time = load_time
        self.load_count = 0
        self.unload_count = 0

    def _do_load(self):
        time.sleep(self._load_time)
        self.load_count += 1
        return {"model": "loaded"}

    def _do_unload(self) -> None:
        self.unload_count += 1


@pytest.mark.asyncio
async def test_ensure_loaded_loads_once():
    lc = FakeLifecycle("embed")
    assert not lc.is_loaded
    assert lc.model is None
    await lc.ensure_loaded()
    assert lc.is_loaded
    assert lc.model == {"model": "loaded"}
    assert lc.load_count == 1
    await lc.ensure_loaded()
    assert lc.load_count == 1


@pytest.mark.asyncio
async def test_ensure_loaded_updates_last_used():
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    t1 = lc.last_used
    assert t1 > 0
    await asyncio.sleep(0.05)
    await lc.ensure_loaded()
    assert lc.last_used > t1


@pytest.mark.asyncio
async def test_unload_clears_model():
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    assert lc.is_loaded
    await lc.unload()
    assert not lc.is_loaded
    assert lc.model is None
    assert lc.unload_count == 1


@pytest.mark.asyncio
async def test_unload_when_not_loaded_is_noop():
    lc = FakeLifecycle("embed")
    await lc.unload()
    assert lc.unload_count == 0


@pytest.mark.asyncio
async def test_reload_after_unload():
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    await lc.unload()
    await lc.ensure_loaded()
    assert lc.load_count == 2
    assert lc.is_loaded


@pytest.mark.asyncio
async def test_concurrent_ensure_loaded_loads_once():
    lc = FakeLifecycle("embed", load_time=0.1)
    await asyncio.gather(
        lc.ensure_loaded(),
        lc.ensure_loaded(),
        lc.ensure_loaded(),
    )
    assert lc.load_count == 1


@pytest.mark.asyncio
async def test_touch_updates_last_used():
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    t1 = lc.last_used
    await asyncio.sleep(0.05)
    lc.touch()
    assert lc.last_used > t1


@pytest.mark.asyncio
async def test_registry_status():
    reg = ModelRegistry()
    lc1 = FakeLifecycle("embed")
    lc2 = FakeLifecycle("ner")
    reg.register("embed", lc1)
    reg.register("ner", lc2)
    await lc1.ensure_loaded()
    status = reg.status()
    assert status == {"embed": True, "ner": False}


@pytest.mark.asyncio
async def test_registry_unload_all():
    reg = ModelRegistry()
    lc1 = FakeLifecycle("embed")
    lc2 = FakeLifecycle("ner")
    reg.register("embed", lc1)
    reg.register("ner", lc2)
    await lc1.ensure_loaded()
    await lc2.ensure_loaded()
    await reg.unload_all()
    assert not lc1.is_loaded
    assert not lc2.is_loaded


@pytest.mark.asyncio
async def test_reaper_unloads_idle_models():
    reg = ModelRegistry()
    lc = FakeLifecycle("embed")
    reg.register("embed", lc)
    await lc.ensure_loaded()
    lc._last_used = time.monotonic() - 100
    reg.start_reaper(ttl_seconds=1, sweep_interval=0.1)
    await asyncio.sleep(0.3)
    reg.stop_reaper()
    assert not lc.is_loaded
    assert lc.unload_count == 1


@pytest.mark.asyncio
async def test_reaper_does_not_unload_recently_used():
    reg = ModelRegistry()
    lc = FakeLifecycle("embed")
    reg.register("embed", lc)
    await lc.ensure_loaded()
    reg.start_reaper(ttl_seconds=60, sweep_interval=0.1)
    await asyncio.sleep(0.3)
    reg.stop_reaper()
    assert lc.is_loaded
    assert lc.unload_count == 0


@pytest.mark.asyncio
async def test_set_ttl_updates_reaper():
    reg = ModelRegistry()
    lc = FakeLifecycle("embed")
    reg.register("embed", lc)
    await lc.ensure_loaded()
    reg.start_reaper(ttl_seconds=3600, sweep_interval=0.1)
    await asyncio.sleep(0.2)
    assert lc.is_loaded
    lc._last_used = time.monotonic() - 10
    reg.set_ttl(1)
    await asyncio.sleep(0.3)
    reg.stop_reaper()
    assert not lc.is_loaded
