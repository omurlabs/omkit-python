"""packages/omur-sdk/tests/test_valkey.py — Tests for valkey.new_client factory.

exports: test_new_client_uses_settings_url() | test_new_client_passes_kwargs() | test_new_client_no_password()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from omur_sdk import valkey
from omur_sdk.config import BaseServiceSettings


class _Settings(BaseServiceSettings):
    OMUR_SERVICE_NAME: str = "test-svc"


def test_new_client_uses_settings_url():
    s = _Settings(
        VALKEY_HOST="vk.local", VALKEY_PORT=6380, VALKEY_PASSWORD="secret"
    )
    expected_url = "redis://:secret@vk.local:6380"
    assert s.valkey_url == expected_url

    with patch("redis.asyncio.from_url") as m:
        valkey.new_client(s)
        m.assert_called_once_with(expected_url)


def test_new_client_passes_kwargs():
    s = _Settings()
    with patch("redis.asyncio.from_url") as m:
        valkey.new_client(s, decode_responses=True, socket_timeout=5.0)
        _, kwargs = m.call_args
        assert kwargs == {"decode_responses": True, "socket_timeout": 5.0}


def test_new_client_no_password():
    s = _Settings(VALKEY_HOST="vk", VALKEY_PORT=6379, VALKEY_PASSWORD="")
    assert s.valkey_url == "redis://vk:6379"
