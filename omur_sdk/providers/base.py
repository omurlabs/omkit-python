"""ProviderBase ABC and shared data contracts for all Omur providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, field_validator


class ProviderDocument(BaseModel):
    """Document emitted by an indexer provider."""
    source: str
    source_id: str
    title: str
    content: str
    doc_type: str | None = None
    doc_date: str | None = None
    meta: dict[str, Any] = {}


class ProviderMetric(BaseModel):
    """Time-series metric emitted by a collector or sensor provider."""
    source: str
    metric: str
    value: float
    unit: str
    ts: int           # nanoseconds UTC epoch
    tenant_id: str
    meta: dict[str, Any] = {}

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v: Any) -> float:
        return float(v)


class ProviderBase(ABC):
    """
    Base class for all Omur data providers.

    Subclasses must declare class-level `kind` and `name` and implement `run()`.
    `run()` is called once per active tenant instance and must handle
    asyncio.CancelledError for clean shutdown.
    """

    kind: str   # 'collector' | 'indexer' | 'sensor'
    name: str   # e.g. 'fitbit', 'gdrive', 'weather_station'

    def __init__(self, tenant_id: str, config: dict[str, Any]) -> None:
        self.tenant_id = tenant_id
        self.config = config

    @abstractmethod
    async def run(self) -> None:
        """Main loop. Must handle asyncio.CancelledError for clean shutdown."""
        ...
