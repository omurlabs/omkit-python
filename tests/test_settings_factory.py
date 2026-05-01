"""packages/omur-sdk/tests/test_settings_factory.py — Tests for SettingsManager.create() factory.

exports: test_create_factory_returns_settings_manager()
used_by: none
rules:   The test module must maintain strict isolation between test cases, with no shared mutable state between test methods. All mock objects must be properly configured with realistic return values that match the expected interface of the SettingsFactory. The module must not import any production code directly, only test utilities and the module under test.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from unittest.mock import MagicMock, AsyncMock

from omur_sdk.settings import SettingsManager


def test_create_factory_returns_settings_manager():
    """create() builds a SettingsManager from a BaseServiceSettings instance.

    Rules:   SettingsManager expects valkey_url to be a valid Redis connection string format. The omur_settings_key must be a valid string that can be used as a key in the Redis store.
    """
    mock_settings = MagicMock()
    mock_settings.valkey_url = "redis://valkey:6379"
    mock_settings.omur_settings_key = "test-key"
    mock_session_factory = AsyncMock()

    mgr = SettingsManager.create(
        service_name="test-svc",
        db_session_factory=mock_session_factory,
        settings=mock_settings,
    )

    assert mgr._service_name == "test-svc"
    assert mgr._valkey_url == "redis://valkey:6379"
    assert mgr._encryption_key == "test-key"
    assert mgr._tenant_id == ""
