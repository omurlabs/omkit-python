"""packages/omur-sdk/tests/test_encryption.py — Tests for omur_sdk.encryption.

exports: test_roundtrip() | test_different_keys_fail() | test_encrypt_empty_string() | test_mask_secret_long() | test_mask_secret_medium() | test_mask_secret_very_short() | test_mask_secret_none() | test_mask_secret_empty() | test_mask_secret_exactly_4() | test_mask_secret_exactly_10()
used_by: none
rules:   The encryption module must maintain backward compatibility for all existing mask_secret behaviors and key generation methods. All test cases must continue to pass without modification to ensure consistent encryption handling. The module cannot introduce new dependencies or alter the public API of encryption functions.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import pytest
from cryptography.fernet import InvalidToken

from omur_sdk.encryption import (
    decrypt_value,
    encrypt_value,
    generate_key,
    mask_secret,
)


def test_roundtrip():
    key = generate_key()
    plaintext = "super-secret-value"
    assert decrypt_value(encrypt_value(plaintext, key), key) == plaintext


def test_different_keys_fail():
    key1 = generate_key()
    key2 = generate_key()
    ciphertext = encrypt_value("hello", key1)
    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext, key2)


def test_encrypt_empty_string():
    key = generate_key()
    assert decrypt_value(encrypt_value("", key), key) == ""


def test_mask_secret_long():
    # >= 10 chars: first 4 + '****' + last 4
    """
    Rules:   Secrets with length >= 10 are masked using the pattern: first 4 chars + '****' + last 4 chars.
    """
    result = mask_secret("sk-abcdefghij1234")
    assert result == "sk-a****1234"


def test_mask_secret_medium():
    # 4-9 chars: first 2 + '****' + last 2
    """
    Rules:   Secrets with length between 4 and 9 are masked using the pattern: first 2 chars + '****' + last 2 chars.
    """
    result = mask_secret("abcdefgh")  # 8 chars
    assert result == "ab****gh"


def test_mask_secret_very_short():
    # < 4 chars: '****'
    """
    Rules:   Secrets with length less than 4 are fully masked as '****'.
    """
    assert mask_secret("abc") == "****"
    assert mask_secret("a") == "****"


def test_mask_secret_none():
    """
    Rules:   Input of None returns None without raising an exception.
    """
    assert mask_secret(None) is None


def test_mask_secret_empty():
    """
    Rules:   Empty string input returns None.
    """
    assert mask_secret("") is None


def test_mask_secret_exactly_4():
    # 4 chars falls into 4-9 bucket: first 2 + last 2
    """
    Rules:   Secrets with exactly 4 characters follow the 4-9 length rule: first 2 + '****' + last 2.
    """
    assert mask_secret("abcd") == "ab****cd"


def test_mask_secret_exactly_10():
    # 10 chars falls into >= 10 bucket: first 4 + last 4
    """
    Rules:   Secrets with exactly 10 characters follow the >= 10 length rule: first 4 + '****' + last 4.
    """
    assert mask_secret("abcdefghij") == "abcd****ghij"
