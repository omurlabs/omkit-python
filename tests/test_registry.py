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


TENANT_ID = "00000000-0000-0000-0000-000000000001"

STUB_DB_ROWS = [
    {"tenant_id": TENANT_ID, "name": "stub", "config": {"key": "val"}},
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
        assert f"{TENANT_ID}:stub" in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_stop_cancels_all_tasks(registry):
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        tasks_before_stop = list(registry._tasks.values())
        await registry.stop()
        assert len(tasks_before_stop) == 1
        assert all(t.cancelled() or t.done() for t in tasks_before_stop)


@pytest.mark.asyncio
async def test_reload_tenant_replaces_tasks(registry):
    """After reload, old task is cancelled and new task started."""
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        old_task = registry._tasks[f"{TENANT_ID}:stub"]

        # Reload same tenant
        with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)):
            await registry._reload_tenant(TENANT_ID)

        assert old_task.cancelled() or old_task.done()
        assert f"{TENANT_ID}:stub" in registry._tasks
        assert registry._tasks[f"{TENANT_ID}:stub"] is not old_task
        await registry.stop()


@pytest.mark.asyncio
async def test_reload_tenant_removes_disabled_providers(registry):
    """If DB returns no rows for a tenant, all its tasks are cancelled."""
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()

        with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=[])):
            await registry._reload_tenant(TENANT_ID)

        assert f"{TENANT_ID}:stub" not in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_unknown_provider_name_is_skipped(registry):
    """Rows with names not in provider_classes are silently skipped."""
    unknown_rows = [{"tenant_id": TENANT_ID, "name": "unknown_thing", "config": {}}]
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=unknown_rows)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        assert len(registry._tasks) == 0
        await registry.stop()
