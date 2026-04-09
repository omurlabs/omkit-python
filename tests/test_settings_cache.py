"""Tests for SettingsManager write-through cache."""

import json
import os
import tempfile
import pytest


class TestWriteThroughCache:
    def test_write_cache_creates_file(self, tmp_path):
        from omur_sdk.settings import SettingsManager

        cache_path = str(tmp_path / "settings-cache.json")
        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {"models.chat_model": "gemma4:e2b", "pipeline.extract_timeout": 120}
        mgr._cache_path = cache_path
        mgr._write_cache()

        assert os.path.exists(cache_path)
        with open(cache_path) as f:
            data = json.load(f)
        assert data["models.chat_model"] == "gemma4:e2b"

    def test_write_cache_excludes_secrets(self, tmp_path):
        from omur_sdk.settings import SettingsManager

        cache_path = str(tmp_path / "settings-cache.json")
        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {"models.chat_model": "gemma4:e2b", "integrations.anthropic_api_key": "sk-secret"}
        mgr._secret_keys = {"integrations.anthropic_api_key"}
        mgr._cache_path = cache_path
        mgr._write_cache()

        with open(cache_path) as f:
            data = json.load(f)
        assert "integrations.anthropic_api_key" not in data
        assert data["models.chat_model"] == "gemma4:e2b"

    def test_read_cache_fallback(self, tmp_path):
        from omur_sdk.settings import SettingsManager

        cache_path = str(tmp_path / "settings-cache.json")
        with open(cache_path, "w") as f:
            json.dump({"models.chat_model": "cached-model"}, f)

        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {}
        mgr._cache_path = cache_path
        mgr._read_cache()

        assert mgr._cache["models.chat_model"] == "cached-model"

    def test_read_cache_missing_file(self, tmp_path):
        from omur_sdk.settings import SettingsManager

        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {}
        mgr._cache_path = str(tmp_path / "nonexistent.json")
        mgr._read_cache()

        assert mgr._cache == {}

    def test_cache_file_permissions(self, tmp_path):
        from omur_sdk.settings import SettingsManager

        cache_path = str(tmp_path / "settings-cache.json")
        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {"key": "value"}
        mgr._secret_keys = set()
        mgr._cache_path = cache_path
        mgr._write_cache()

        mode = os.stat(cache_path).st_mode & 0o777
        assert mode == 0o600
