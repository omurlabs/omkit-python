"""Tests for ProviderRegistry — all DB and Valkey calls are mocked."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from omur_sdk.providers.base import ProviderBase
from omur_sdk.providers.registry import ProviderRegistry


# ── Fixtures ─────────────────────────────────────────────────────

class StubProvider(ProviderBase):
    kind = "collector"
    name = "stub"

    def __init__(self, tenant_id, config):
        super().__init__(tenant_id, config)
        self.run_called = 0

    async def run(self):
        self.run_called += 1
        await asyncio.sleep(9999)  # blocked until cancelled


STUB_DB_ROWS = [
    {"tenant_id": "tid-1", "name": "stub", "config": {"key": "val"}},
]


@pytest.fixture
def registry():
    return ProviderRegistry(
        kind="collector",
        provider_classes={"stub": StubProvider},
        postgres_dsn="postgresql+asyncpg://fake/fake",
        valkey_url="redis://fake:6379",
    )


# ── Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_loads_providers_from_db(registry):
    """Registry starts one task per enabled provider row returned by DB."""
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        assert len(registry._tasks) == 1
        assert "tid-1:stub" in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_stop_cancels_all_tasks(registry):
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        await registry.stop()
        assert all(t.cancelled() or t.done() for t in registry._tasks.values())


@pytest.mark.asyncio
async def test_reload_tenant_replaces_tasks(registry):
    """After reload, old task is cancelled and new task started."""
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        old_task = registry._tasks["tid-1:stub"]

        # Reload same tenant
        with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)):
            await registry._reload_tenant("tid-1")

        assert old_task.cancelled() or old_task.done()
        assert "tid-1:stub" in registry._tasks
        assert registry._tasks["tid-1:stub"] is not old_task
        await registry.stop()


@pytest.mark.asyncio
async def test_reload_tenant_removes_disabled_providers(registry):
    """If DB returns no rows for a tenant, all its tasks are cancelled."""
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()

        with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=[])):
            await registry._reload_tenant("tid-1")

        assert "tid-1:stub" not in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_unknown_provider_name_is_skipped(registry):
    """Rows with names not in provider_classes are silently skipped."""
    unknown_rows = [{"tenant_id": "tid-1", "name": "unknown_thing", "config": {}}]
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=unknown_rows)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        assert len(registry._tasks) == 0
        await registry.stop()
