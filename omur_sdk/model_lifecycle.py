"""packages/omur-sdk/omur_sdk/model_lifecycle.py — On-demand model loading with TTL-based idle unloading.

exports: MODEL_LOAD_DURATION | MODEL_LOAD_ERRORS | MODEL_UNLOAD_TOTAL | MODEL_LOADED | class ModelLifecycle | class ModelRegistry
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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
        return self._model is not None

    @property
    def model(self) -> Any:
        return self._model

    @property
    def last_used(self) -> float:
        return self._last_used

    def touch(self) -> None:
        self._last_used = time.monotonic()

    async def ensure_loaded(self) -> None:
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
        self._models[name] = lifecycle

    def status(self) -> dict[str, bool]:
        return {name: lc.is_loaded for name, lc in self._models.items()}

    def set_ttl(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        log.info("registry.ttl_updated", ttl=ttl_seconds)

    def start_reaper(self, ttl_seconds: int, sweep_interval: float = 30) -> None:
        self._ttl = ttl_seconds
        if self._reaper_task and not self._reaper_task.done():
            self._reaper_task.cancel()
        self._reaper_task = asyncio.create_task(
            self._reap_loop(sweep_interval), name="model-reaper"
        )

    def stop_reaper(self) -> None:
        if self._reaper_task and not self._reaper_task.done():
            self._reaper_task.cancel()
            self._reaper_task = None

    async def unload_all(self) -> None:
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
