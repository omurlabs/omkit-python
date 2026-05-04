"""packages/omur-sdk/tests/test_settings_cache.py — Tests for SettingsManager write-through cache.

exports: class TestWriteThroughCache
rules:   The cache module must ensure atomic file operations to prevent corruption during concurrent access, maintain consistent file permissions across all cache files, and guarantee that sensitive data is never written to disk in plaintext format.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import json
import os
import tempfile
import pytest


class TestWriteThroughCache:
    def test_write_cache_creates_file(self, tmp_path):
        """
        Rules:   Cache file is created with correct JSON structure and content matching the internal cache state.
        """
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
        """
        Rules:   Secret keys are excluded from the cache file during write operations, ensuring sensitive data is not persisted.
        """
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
        """
        Rules:   If cache file exists, it's read and merged into the current cache; missing keys are not overwritten.
        """
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
        """
        Rules:   When cache file does not exist, the cache remains empty without raising an error.
        """
        from omur_sdk.settings import SettingsManager

        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {}
        mgr._cache_path = str(tmp_path / "nonexistent.json")
        mgr._read_cache()

        assert mgr._cache == {}

    def test_cache_file_permissions(self, tmp_path):
        """
        Rules:   Cache files are written with strict permissions (0o600) to prevent unauthorized access.
        """
        from omur_sdk.settings import SettingsManager

        cache_path = str(tmp_path / "settings-cache.json")
        mgr = SettingsManager.__new__(SettingsManager)
        mgr._cache = {"key": "value"}
        mgr._secret_keys = set()
        mgr._cache_path = cache_path
        mgr._write_cache()

        mode = os.stat(cache_path).st_mode & 0o777
        assert mode == 0o600
