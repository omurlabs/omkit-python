"""packages/omur-sdk/tests/test_settings_factory.py — Tests for SettingsManager.create() factory.

exports: test_create_factory_returns_settings_manager()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from unittest.mock import MagicMock, AsyncMock

from omur_sdk.settings import SettingsManager


def test_create_factory_returns_settings_manager():
    """create() builds a SettingsManager from a BaseServiceSettings instance."""
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
