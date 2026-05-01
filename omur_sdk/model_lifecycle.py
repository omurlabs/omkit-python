"""packages/omur-sdk/omur_sdk/model_lifecycle.py — On-demand model loading with TTL-based idle unloading.

exports: MODEL_LOAD_DURATION | MODEL_LOAD_ERRORS | MODEL_UNLOAD_TOTAL | MODEL_LOADED | class ModelLifecycle | class ModelRegistry
used_by: none
rules:   The `ModelLifecycle` class must ensure thread-safe access to `_model`, `_last_used`, and `_lock` attributes, as all methods that modify or read these shared state elements are intended to be concurrently accessible. The `ModelRegistry` class requires all `ModelLifecycle` instances it manages to be properly registered before any unload operations can occur, and the reaper task must be stopped before the registry is destroyed to prevent orphaned tasks. The `ensure_loaded()` and `unload()` methods in `ModelLifecycle` are designed to be called concurrently, so the internal `_lock` mechanism must prevent race conditions during model loading and unloading operations.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import abc
import asyncio
import gc
import time
from typing import Any

import structlog
from prometheus_client import Histogram, Counter, Gauge

log = structlog.get_logger()

MODEL_LOAD_DURATION = Histogram(
    "model_load_duration_seconds",
    "Time to load a model into memory",
    ["model"],
    buckets=[1, 2, 5, 10, 15, 20, 30, 60],
)
MODEL_LOAD_ERRORS = Counter(
    "model_load_errors_total",
    "Number of model load failures",
    ["model"],
)
MODEL_UNLOAD_TOTAL = Counter(
    "model_unload_total",
    "Number of model unloads",
    ["model", "reason"],
)
MODEL_LOADED = Gauge(
    "model_loaded",
    "Whether a model is currently loaded (1=yes, 0=no)",
    ["model"],
)


class ModelLifecycle(abc.ABC):
    """Abstract base for on-demand model loading with idle tracking."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._model: Any = None
        self._last_used: float = 0
        self._lock = asyncio.Lock()

    @abc.abstractmethod
    def _do_load(self) -> Any:
        """Load model into memory. Runs in thread executor. Return model object."""

    @abc.abstractmethod
    def _do_unload(self) -> None:
        """Release model resources. Runs in thread executor."""

    @property
    def is_loaded(self) -> bool:
        """
        Rules:   none
        """
        return self._model is not None

    @property
    def model(self) -> Any:
        return self._model

    @property
    def last_used(self) -> float:
        return self._last_used

    def touch(self) -> None:
        """
        Rules:   none
        """
        self._last_used = time.monotonic()

    async def ensure_loaded(self) -> None:
        """
        Rules:   Model loading is async and uses a lock; concurrent calls may result in redundant loading if not properly synchronized.
        """
        async with self._lock:
            if self._model is not None:
                self._last_used = time.monotonic()
                return
            log.info("model.loading", model=self.name)
            t0 = time.monotonic()
            loop = asyncio.get_running_loop()
            try:
                self._model = await loop.run_in_executor(None, self._do_load)
            except Exception:
                MODEL_LOAD_ERRORS.labels(model=self.name).inc()
                raise
            duration = time.monotonic() - t0
            self._last_used = time.monotonic()
            MODEL_LOAD_DURATION.labels(model=self.name).observe(duration)
            MODEL_LOADED.labels(model=self.name).set(1)
            log.info("model.loaded", model=self.name, duration_s=round(duration, 2))

    async def unload(self) -> None:
        """
        Rules:   Model unloading is async and uses a lock; calling unload on an already unloaded model is safe but does nothing.
        """
        async with self._lock:
            if self._model is None:
                return
            log.info("model.unloading", model=self.name)
            MODEL_LOADED.labels(model=self.name).set(0)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._do_unload)
            self._model = None
            self._last_used = 0
            gc.collect()
            log.info("model.unloaded", model=self.name)


class ModelRegistry:
    """Manages a set of ModelLifecycle instances with a shared reaper task."""

    def __init__(self) -> None:
        self._models: dict[str, ModelLifecycle] = {}
        self._ttl: int = 300
        self._reaper_task: asyncio.Task | None = None

    def register(self, name: str, lifecycle: ModelLifecycle) -> None:
        """
        Rules:   none
        """
        self._models[name] = lifecycle

    def status(self) -> dict[str, bool]:
        """
        Rules:   none
        """
        return {name: lc.is_loaded for name, lc in self._models.items()}

    def set_ttl(self, ttl_seconds: int) -> None:
        """
        Rules:   none
        """
        self._ttl = ttl_seconds
        log.info("registry.ttl_updated", ttl=ttl_seconds)

    def start_reaper(self, ttl_seconds: int, sweep_interval: float = 30) -> None:
        """
        Rules:   Starting a new reaper task cancels any existing one; ensure the registry is not used concurrently during this operation.
        """
        self._ttl = ttl_seconds
        if self._reaper_task and not self._reaper_task.done():
            self._reaper_task.cancel()
        self._reaper_task = asyncio.create_task(
            self._reap_loop(sweep_interval), name="model-reaper"
        )

    def stop_reaper(self) -> None:
        """
        Rules:   none
        """
        if self._reaper_task and not self._reaper_task.done():
            self._reaper_task.cancel()
            self._reaper_task = None

    async def unload_all(self) -> None:
        """
        Rules:   Unloading all models stops the reaper task and may cause a delay due to garbage collection and async I/O.
        """
        self.stop_reaper()
        for name, lc in self._models.items():
            if lc.is_loaded:
                MODEL_UNLOAD_TOTAL.labels(model=name, reason="shutdown").inc()
                await lc.unload()

    async def _reap_loop(self, interval: float) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                if self._ttl <= 0:
                    continue
                now = time.monotonic()
                for name, lc in list(self._models.items()):
                    try:
                        if lc.is_loaded and (now - lc.last_used) >= self._ttl:
                            MODEL_UNLOAD_TOTAL.labels(model=name, reason="idle").inc()
                            await lc.unload()
                    except Exception:
                        log.error("reaper.unload_failed", model=name, exc_info=True)
        except asyncio.CancelledError:
            pass
