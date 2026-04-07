"""Tests for omur_sdk.encryption."""

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
    result = mask_secret("sk-abcdefghij1234")
    assert result == "sk-a****1234"


def test_mask_secret_medium():
    # 4-9 chars: first 2 + '****' + last 2
    result = mask_secret("abcdefgh")  # 8 chars
    assert result == "ab****gh"


def test_mask_secret_very_short():
    # < 4 chars: '****'
    assert mask_secret("abc") == "****"
    assert mask_secret("a") == "****"


def test_mask_secret_none():
    assert mask_secret(None) is None


def test_mask_secret_empty():
    assert mask_secret("") is None


def test_mask_secret_exactly_4():
    # 4 chars falls into 4-9 bucket: first 2 + last 2
    assert mask_secret("abcd") == "ab****cd"


def test_mask_secret_exactly_10():
    # 10 chars falls into >= 10 bucket: first 4 + last 4
    assert mask_secret("abcdefghij") == "abcd****ghij"
