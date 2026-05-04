"""packages/omur-sdk/tests/test_model_lifecycle.py — Tests for on-demand model loading with TTL-based idle unload.

exports: class FakeLifecycle | test_ensure_loaded_loads_once() | test_ensure_loaded_updates_last_used() | test_unload_clears_model() | test_unload_when_not_loaded_is_noop() | test_reload_after_unload() | test_concurrent_ensure_loaded_loads_once() | test_touch_updates_last_used() | test_registry_status() | test_registry_unload_all() | test_reaper_unloads_idle_models() | test_reaper_does_not_unload_recently_used() | test_set_ttl_updates_reaper()
rules:   The `FakeLifecycle` class must not modify the `load_time` parameter during `_do_load()` execution, and all test methods must instantiate fresh `FakeLifecycle` or `ModelRegistry` objects to ensure test isolation. The module's lifecycle management logic must handle concurrent access without race conditions, and the reaper mechanism must accurately track model last-used timestamps to prevent premature unloading.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

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
    """
    Rules:   ensure_loaded should only load the model once even if called multiple times concurrently, ensuring thread safety and idempotency.
    """
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
    """
    Rules:   ensure_loaded updates the last_used timestamp on each call, which is used for tracking model usage and idle cleanup.
    """
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    t1 = lc.last_used
    assert t1 > 0
    await asyncio.sleep(0.05)
    await lc.ensure_loaded()
    assert lc.last_used > t1


@pytest.mark.asyncio
async def test_unload_clears_model():
    """
    Rules:   unload clears the model reference and sets is_loaded to False, but does not affect the load_count.
    """
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    assert lc.is_loaded
    await lc.unload()
    assert not lc.is_loaded
    assert lc.model is None
    assert lc.unload_count == 1


@pytest.mark.asyncio
async def test_unload_when_not_loaded_is_noop():
    """
    Rules:   unload is a no-op if the model is not currently loaded, preventing errors or unexpected behavior.
    """
    lc = FakeLifecycle("embed")
    await lc.unload()
    assert lc.unload_count == 0


@pytest.mark.asyncio
async def test_reload_after_unload():
    """
    Rules:   After unloading and reloading, the load_count increases to reflect the new load operation, ensuring accurate tracking.
    """
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    await lc.unload()
    await lc.ensure_loaded()
    assert lc.load_count == 2
    assert lc.is_loaded


@pytest.mark.asyncio
async def test_concurrent_ensure_loaded_loads_once():
    """
    Rules:   Concurrent calls to ensure_loaded should not trigger multiple loads; only one load should occur regardless of how many concurrent calls are made.
    """
    lc = FakeLifecycle("embed", load_time=0.1)
    await asyncio.gather(
        lc.ensure_loaded(),
        lc.ensure_loaded(),
        lc.ensure_loaded(),
    )
    assert lc.load_count == 1


@pytest.mark.asyncio
async def test_touch_updates_last_used():
    """
    Rules:   touch updates the last_used timestamp without reloading the model, useful for extending model lifetime in registry.
    """
    lc = FakeLifecycle("embed")
    await lc.ensure_loaded()
    t1 = lc.last_used
    await asyncio.sleep(0.05)
    lc.touch()
    assert lc.last_used > t1


@pytest.mark.asyncio
async def test_registry_status():
    """
    Rules:   The registry status reflects the loaded state of each registered model, enabling monitoring and debugging.
    """
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
    """
    Rules:   unload_all unloads all registered models in the registry, setting their is_loaded flag to False and clearing their model references.
    """
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
    """
    Rules:   The reaper unloads models that have not been used for longer than the specified TTL, based on last_used timestamp.
    """
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
    """
    Rules:   Models recently used (within TTL) are not unloaded by the reaper, ensuring active models remain loaded.
    """
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
    """
    Rules:   Changing TTL via set_ttl immediately affects the reaper's behavior, causing models to be unloaded sooner if necessary.
    """
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
