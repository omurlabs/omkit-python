"""omkit/crypto/aes_gcm.py — AES-256-GCM envelope helpers, byte-for-byte compatible with omkit-go/crypto.

Wraps `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Envelope layout
matches `omkit-go/crypto/aes_gcm.go`:

    envelope = nonce(12 bytes) || ciphertext_with_tag

There is no magic / version / key-id header — the calling KMS layer owns
key identity. The 16-byte GCM authentication tag is appended to the
ciphertext by AESGCM itself (same as Go's `cipher.AEAD.Seal`).

Two surfaces are exposed:

  * Low-level (matches Go positional API): `wrap_with_key(kek, plaintext, aad)`
    and `unwrap_with_key(kek, blob, aad)`. Use these from KMS adapters.
  * Keyword-style requested by the caller spec: `wrap(plaintext, *, key_id,
    aad, key_resolver)` and `unwrap(envelope, *, aad, key_resolver)`. The
    resolver is a callable `(key_id: str) -> bytes` returning the 32-byte KEK.

Pure-CPU sync — KMS layers add async wrappers when network I/O is involved.

exports: wrap | unwrap | wrap_with_key | unwrap_with_key | NONCE_SIZE | TAG_SIZE | InvalidEnvelopeError | InvalidKeyError
rules:   Envelope bytes must remain identical to omkit-go/crypto. Never store or log the KEK. Treat any AESGCM decrypt failure as authentication failure — never leak why (tag vs short blob) to callers beyond the exception type.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/crypto
message:
"""

from __future__ import annotations

from typing import Callable

NONCE_SIZE: int = 12  # AES-GCM standard nonce; matches Go cipher.NewGCM default.
TAG_SIZE: int = 16  # AES-GCM authentication tag length.
KEK_SIZE: int = 32  # AES-256.


def _load_cryptography():
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise ImportError(
            "omkit.crypto.aes_gcm requires `cryptography`. "
            "Install with: pip install omkit[crypto]"
        ) from e
    return AESGCM, InvalidTag


class InvalidKeyError(ValueError):
    """KEK is not exactly 32 bytes. Mirrors Go: `fmt.Errorf("kek must be 32 bytes, got %d", ...)`."""


class InvalidEnvelopeError(ValueError):
    """Envelope is malformed (too short) or fails authentication. Mirrors Go's `ErrInvalidEnvelope`-style sentinel.

    Raised for: blob shorter than `NONCE_SIZE`, GCM tag mismatch, or AAD mismatch.
    """


def _validate_kek(kek: bytes) -> None:
    if len(kek) != KEK_SIZE:
        raise InvalidKeyError(f"kek must be {KEK_SIZE} bytes, got {len(kek)}")


def wrap_with_key(kek: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Encrypt `plaintext` under `kek` (32 bytes) with AES-256-GCM, binding `aad`.

    Returns `nonce || ciphertext || tag`. Byte-for-byte equivalent to
    `omkit-go/crypto.Wrap(kek, plaintext, aad)`.
    """
    _validate_kek(kek)
    AESGCM, _ = _load_cryptography()
    aead = AESGCM(kek)
    # AESGCM.encrypt generates random nonce externally — we generate it here
    # so the returned blob is `nonce || ciphertext_with_tag`, matching Go.
    import os  # local import — keep the top-level import surface minimal.

    nonce = os.urandom(NONCE_SIZE)
    ct = aead.encrypt(nonce, plaintext, aad if aad else None)
    return nonce + ct


def unwrap_with_key(kek: bytes, blob: bytes, aad: bytes) -> bytes:
    """Reverse `wrap_with_key`. Raises `InvalidEnvelopeError` on any failure.

    Byte-for-byte equivalent to `omkit-go/crypto.Unwrap(kek, blob, aad)`.
    """
    _validate_kek(kek)
    if len(blob) < NONCE_SIZE:
        raise InvalidEnvelopeError(f"blob too short: {len(blob)} bytes (need >= {NONCE_SIZE})")
    nonce, ct = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    AESGCM, InvalidTag = _load_cryptography()
    aead = AESGCM(kek)
    try:
        return aead.decrypt(nonce, ct, aad if aad else None)
    except InvalidTag as exc:
        raise InvalidEnvelopeError("authentication failed (kek/aad mismatch or tampered ciphertext)") from exc


# --- Keyword API (resolver-based) -------------------------------------------


KeyResolver = Callable[[str], bytes]


def wrap(
    plaintext: bytes,
    *,
    key_id: str,
    aad: bytes,
    key_resolver: KeyResolver,
) -> bytes:
    """Resolve KEK via `key_resolver(key_id)` then call `wrap_with_key`.

    The keyword surface mirrors the caller's port spec; on-wire bytes are
    identical to `wrap_with_key` and to Go's `crypto.Wrap`. The `key_id`
    is NOT embedded in the envelope — it must be tracked alongside the blob
    (matches Go semantics where the KMS layer holds key identity).
    """
    kek = key_resolver(key_id)
    return wrap_with_key(kek, plaintext, aad)


def unwrap(
    envelope: bytes,
    *,
    aad: bytes,
    key_resolver: KeyResolver,
    key_id: str | None = None,
) -> bytes:
    """Resolve KEK via `key_resolver(key_id)` then call `unwrap_with_key`.

    `key_id` is optional only for resolvers that ignore it (single-key bags);
    cross-SDK callers should pass the same `key_id` they used at wrap time.
    """
    kek = key_resolver(key_id) if key_id is not None else key_resolver("")
    return unwrap_with_key(kek, envelope, aad)


__all__ = [
    "wrap",
    "unwrap",
    "wrap_with_key",
    "unwrap_with_key",
    "NONCE_SIZE",
    "TAG_SIZE",
    "KEK_SIZE",
    "InvalidEnvelopeError",
    "InvalidKeyError",
    "KeyResolver",
]
