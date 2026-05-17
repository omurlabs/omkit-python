"""tests/test_encryption.py — Tests for omkit.encryption (AES-256-GCM).

exports: test_roundtrip | test_different_keys_fail | test_encrypt_empty_string | test_token_version_prefix | test_tamper_detection | test_invalid_key_size | test_mask_secret_*
rules:   API surface (`generate_key`, `encrypt_value`, `decrypt_value`, `mask_secret`) is stable and must remain wire-compatible with omkit-go/encryption. AAD changes require a `v2` version prefix.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | replaced Fernet tests with AES-256-GCM
"""

import base64

import pytest

from omkit.encryption import (
    InvalidKey,
    InvalidToken,
    KEY_SIZE,
    decrypt_value,
    encrypt_value,
    generate_key,
    mask_secret,
)


def test_roundtrip():
    """
    Rules:   Encryption and decryption functions must handle arbitrary string inputs consistently. The key generation function should produce keys compatible with both encrypt and decrypt operations.
    """
    key = generate_key()
    plaintext = "super-secret-value"
    assert decrypt_value(encrypt_value(plaintext, key), key) == plaintext


def test_different_keys_fail():
    """
    Rules:   When using different keys for encryption and decryption, the decryption will fail with an InvalidToken exception. Future developers must understand that key consistency is required for successful decryption.
    """
    key1 = generate_key()
    key2 = generate_key()
    ciphertext = encrypt_value("hello", key1)
    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext, key2)


def test_encrypt_empty_string():
    """Empty plaintext round-trips."""
    key = generate_key()
    assert decrypt_value(encrypt_value("", key), key) == ""


def test_token_version_prefix():
    """Tokens carry the `v1` version prefix so future rotations remain detectable."""
    key = generate_key()
    token = encrypt_value("hello", key)
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    assert raw[:2] == b"v1"


def test_tamper_detection():
    """Mutating any byte in the ciphertext trips the GCM auth tag."""
    key = generate_key()
    token = encrypt_value("hello", key)
    raw = bytearray(base64.urlsafe_b64decode(token.encode("ascii")))
    raw[-1] ^= 0x01  # flip last byte of tag
    tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(InvalidToken):
        decrypt_value(tampered, key)


def test_invalid_key_size():
    """Keys that don't decode to 32 bytes raise InvalidKey."""
    short = base64.urlsafe_b64encode(b"too-short").decode("ascii")
    with pytest.raises(InvalidKey):
        encrypt_value("x", short)
    with pytest.raises(InvalidKey):
        decrypt_value(short, short)


def test_key_size_constant():
    """Generated keys decode to exactly KEY_SIZE raw bytes."""
    raw = base64.urlsafe_b64decode(generate_key().encode("ascii"))
    assert len(raw) == KEY_SIZE


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
