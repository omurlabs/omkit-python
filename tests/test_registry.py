"""packages/omur-sdk/tests/test_registry.py — all DB and Valkey calls are mocked.

exports: class StubProvider | TENANT_ID | STUB_DB_ROWS | registry() | test_start_loads_providers_from_db(registry) | test_stop_cancels_all_tasks(registry) | test_reload_tenant_replaces_tasks(registry) | test_reload_tenant_removes_disabled_providers(registry) | test_unknown_provider_name_is_skipped(registry)
rules:   The ProviderRegistry must maintain thread-safe operations when loading and reloading providers, as concurrent access during tenant reloads is expected. All provider lifecycle methods (start, stop, reload) must be idempotent and handle partial failures gracefully without leaving the registry in an inconsistent state. The registry's `_fetch_providers` method is the sole source of provider configuration and must be mocked consistently across all tests to ensure deterministic behavior.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

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
        """
        Rules:   none
        """
        self.run_called += 1
        await asyncio.sleep(9999)  # blocked until cancelled


TENANT_ID = "00000000-0000-0000-0000-000000000001"

STUB_DB_ROWS = [
    {"tenant_id": TENANT_ID, "name": "stub", "config": {"key": "val"}},
]


@pytest.fixture
def registry():
    """
    Rules:   none
    """
    return ProviderRegistry(
        kind="collector",
        provider_classes={"stub": StubProvider},
        postgres_dsn="postgresql+asyncpg://fake/fake",
        valkey_url="redis://fake:6379",
    )


# ── Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_loads_providers_from_db(registry):
    """Registry starts one task per enabled provider row returned by DB.

    Rules:   YES: The test assumes that _fetch_providers returns STUB_DB_ROWS, and that the provider name 'stub' exists in provider_classes. Future developers must ensure these dependencies align with actual implementation.
    """
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        assert len(registry._tasks) == 1
        assert f"{TENANT_ID}:stub" in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_stop_cancels_all_tasks(registry):
    """
    Rules:   YES: The test depends on the registry starting exactly one task; if more or fewer tasks are started, the assertion will fail. Developers must understand that the number of tasks is directly tied to the DB row count and provider configuration.
    """
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        tasks_before_stop = list(registry._tasks.values())
        await registry.stop()
        assert len(tasks_before_stop) == 1
        assert all(t.cancelled() or t.done() for t in tasks_before_stop)


@pytest.mark.asyncio
async def test_reload_tenant_replaces_tasks(registry):
    """After reload, old task is cancelled and new task started.

    Rules:   YES: The test assumes that reloading a tenant cancels the old task and starts a new one. Developers must know that the task replacement logic relies on the internal structure of _tasks and how _reload_tenant is implemented.
    """
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
    """If DB returns no rows for a tenant, all its tasks are cancelled.

    Rules:   YES: The test assumes that when _fetch_providers returns an empty list, the corresponding tenant's tasks are removed from _tasks. Developers must know this behavior is tied to the reload logic and not just task cancellation.
    """
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=STUB_DB_ROWS)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()

        with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=[])):
            await registry._reload_tenant(TENANT_ID)

        assert f"{TENANT_ID}:stub" not in registry._tasks
        await registry.stop()


@pytest.mark.asyncio
async def test_unknown_provider_name_is_skipped(registry):
    """Rows with names not in provider_classes are silently skipped.

    Rules:   YES: The test assumes that unknown provider names in DB rows are silently skipped. Developers must understand that this behavior is handled by checking provider_classes and not raising exceptions.
    """
    unknown_rows = [{"tenant_id": TENANT_ID, "name": "unknown_thing", "config": {}}]
    with patch.object(registry, "_fetch_providers", new=AsyncMock(return_value=unknown_rows)), \
         patch.object(registry, "_subscribe_valkey", new=AsyncMock()):
        await registry.start()
        assert len(registry._tasks) == 0
        await registry.stop()
