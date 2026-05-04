"""packages/omur-sdk/tests/test_settings_manager.py — test_settings_manager module.

exports: manager() | test_get_returns_cached_value(manager) | test_get_returns_default_when_missing(manager) | test_on_change_registers_callback(manager) | test_handle_message_updates_cache_and_fires_callback(manager) | test_handle_message_secret_does_not_cache_value(manager)
rules:   The settings manager must maintain thread-safe cache access and ensure all callback executions are non-blocking to prevent UI freezes.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
# packages/omur-sdk/tests/test_settings_manager.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from omur_sdk.settings import SettingsManager


@pytest.fixture
def manager():
    db = AsyncMock()
    mgr = SettingsManager(
        service_name="test",
        db_session_factory=db,
        valkey_url="redis://localhost:6379",
        tenant_id="00000000-0000-0000-0000-000000000001",
        encryption_key="test-key",
    )
    return mgr


def test_get_returns_cached_value(manager):
    manager._cache["models.chat_model"] = "llama3.2"
    assert manager.get("models.chat_model") == "llama3.2"


def test_get_returns_default_when_missing(manager):
    assert manager.get("nonexistent.key", default="fallback") == "fallback"


def test_on_change_registers_callback(manager):
    callback = MagicMock()
    manager.on_change("sync.ow_interval", callback)
    assert "sync.ow_interval" in manager._listeners
    assert callback in manager._listeners["sync.ow_interval"]


@pytest.mark.asyncio
async def test_handle_message_updates_cache_and_fires_callback(manager):
    callback = AsyncMock()
    manager.on_change("models.chat_model", callback)

    message = {"key": "models.chat_model", "value": "mistral", "requires_restart": False}
    await manager._handle_message(json.dumps(message))

    assert manager._cache["models.chat_model"] == "mistral"
    callback.assert_called_once_with("mistral")


@pytest.mark.asyncio
async def test_handle_message_secret_does_not_cache_value(manager):
    manager._cache["integrations.api_key"] = "old"
    message = {"key": "integrations.api_key", "changed": True, "requires_restart": False}
    await manager._handle_message(json.dumps(message))
    assert manager._cache.get("integrations.api_key") is None
