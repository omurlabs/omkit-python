"""omkit/encryption.py — AES-256-GCM string encryption for tenant settings secrets.

Thin string-in / string-out wrapper around `omkit.crypto.aes_gcm`. Used by
settings stores (tenant_settings, account_keys, system_keys) that hold a
short, latency-insensitive secret as a URL-safe base64 token.

Wire format (versioned):
    base64.urlsafe(b"v1" || nonce(12) || ciphertext || tag(16))

`v1` is a hard prefix so future rotations can ship a `v2` next to it without
guesswork. AAD is fixed to ``b"omkit.encryption.v1"``; cross-module ciphertext
swaps fail at the GCM auth tag rather than silently decrypting.

Cross-SDK contract: byte-identical to `github.com/omurlabs/omkit-go/encryption`.

exports: generate_key | encrypt_value | decrypt_value | mask_secret | KEY_SIZE | InvalidToken | InvalidKey
rules:   API surface (`generate_key`, `encrypt_value`, `decrypt_value`, `mask_secret`) is stable. Internal crypto MUST come from omkit.crypto.aes_gcm — no second AEAD impl in this module.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | replaced Fernet with AES-256-GCM
"""

from __future__ import annotations

import base64
import secrets

from omkit.crypto.aes_gcm import (
    InvalidEnvelopeError as InvalidToken,
    InvalidKeyError as InvalidKey,
    unwrap_with_key,
    wrap_with_key,
)

KEY_SIZE = 32
_VERSION = b"v1"
_AAD = b"omkit.encryption.v1"


__all__ = [
    "generate_key",
    "encrypt_value",
    "decrypt_value",
    "mask_secret",
    "KEY_SIZE",
    "InvalidToken",
    "InvalidKey",
]


def _decode_key(key: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise InvalidKey(f"key must be URL-safe base64: {exc}") from exc
    if len(raw) != KEY_SIZE:
        raise InvalidKey(f"key must decode to {KEY_SIZE} bytes, got {len(raw)}")
    return raw


def generate_key() -> str:
    """Generate a fresh URL-safe base64 32-byte key.

    Output decodes back to exactly 32 raw bytes via `_decode_key`. Store in a
    secret manager; never log the value.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_SIZE)).decode("ascii")


def encrypt_value(plaintext: str, key: str) -> str:
    """Encrypt `plaintext` under `key`. Returns URL-safe base64 token.

    The token carries a 2-byte version prefix so future rotations are safe.
    Empty plaintext is supported (produces a valid token).
    """
    kek = _decode_key(key)
    blob = wrap_with_key(kek, plaintext.encode("utf-8"), _AAD)
    return base64.urlsafe_b64encode(_VERSION + blob).decode("ascii")


def decrypt_value(ciphertext: str, key: str) -> str:
    """Decrypt a token produced by `encrypt_value`.

    Raises `InvalidToken` on version mismatch, base64 decode failure, or AEAD
    auth tag failure (wrong key, mutated bytes, AAD drift). Raises `InvalidKey`
    when the key isn't a 32-byte URL-safe base64 value.
    """
    kek = _decode_key(key)
    try:
        raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise InvalidToken(f"invalid base64: {exc}") from exc
    if len(raw) < len(_VERSION) + 12 + 16:
        raise InvalidToken("token too short")
    if raw[: len(_VERSION)] != _VERSION:
        raise InvalidToken("unsupported version prefix")
    blob = raw[len(_VERSION) :]
    plain = unwrap_with_key(kek, blob, _AAD)
    return plain.decode("utf-8")


def mask_secret(value: str | None) -> str | None:
    """Mask a secret for API display.

    - >= 10 chars: first 4 + '****' + last 4 (e.g. 'sk-a****Xk2f')
    - 4–9 chars:   first 2 + '****' + last 2 (e.g. 'ab****ef')
    - < 4 chars:   '****'
    - None / empty: returns None
    """
    if not value:
        return None
    n = len(value)
    if n >= 10:
        return value[:4] + "****" + value[-4:]
    if n >= 4:
        return value[:2] + "****" + value[-2:]
    return "****"
