"""omkit/crypto/kuser.py — KUser session-key type and self-test routine (port of omkit-go/crypto/kuser.go).

`KUser` is a 32-byte symmetric session key with three operations:

  * `new_self_test()` — produce `(nonce, ciphertext)` over the pinned payload
    `"OMUR-SELFTEST-V1"` with AAD `"omur-selftest"`.
  * `verify_self_test(nonce, ciphertext)` — round-trip check.
  * `zero()` — best-effort overwrite of the key material.

Note on `zero()`: Python's runtime makes truly secure wipe impossible — `bytes`
are immutable and `bytearray` may have been copied internally. The `zero()`
method overwrites the local `bytearray` so the live reference no longer holds
the secret, but other copies the runtime may have produced (interned tuples,
intermediate buffers) are out of reach. Treat this as defence-in-depth, not
as a guarantee. Go gets the same caveat at the language level (slices may
escape to the heap before `Zero()` runs).

exports: KUser | KUSER_SIZE
rules:   Self-test payload `OMUR-SELFTEST-V1` and AAD `omur-selftest` must match omkit-go/crypto/kuser.go byte-for-byte. Never log or pickle a KUser; never compare equality with another secret (use hmac.compare_digest if you must).
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/crypto
message:
"""

from __future__ import annotations

import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KUSER_SIZE: Final[int] = 32
_SELF_TEST_PAYLOAD: Final[bytes] = b"OMUR-SELFTEST-V1"
_SELF_TEST_AAD: Final[bytes] = b"omur-selftest"
_NONCE_SIZE: Final[int] = 12


class KUser:
    """32-byte symmetric session key. Construct via `KUser.generate()` or `KUser(raw)`.

    Internally stored as a mutable `bytearray` so `zero()` can overwrite in place.
    """

    __slots__ = ("_buf",)

    def __init__(self, raw: bytes | bytearray) -> None:
        if len(raw) != KUSER_SIZE:
            raise ValueError(f"KUser requires exactly {KUSER_SIZE} bytes, got {len(raw)}")
        self._buf = bytearray(raw)

    @classmethod
    def generate(cls) -> "KUser":
        """Generate a fresh KUser from `os.urandom`. Equivalent to Go's `NewKUser`."""
        return cls(os.urandom(KUSER_SIZE))

    @property
    def bytes(self) -> bytes:
        """Return a defensive copy of the key bytes."""
        return bytes(self._buf)

    def zero(self) -> None:
        """Overwrite the underlying buffer with zeros. See module docstring for caveats."""
        for i in range(len(self._buf)):
            self._buf[i] = 0

    def _aead(self) -> AESGCM:
        # AESGCM accepts a bytes-like; pass a fresh `bytes` view so the
        # cryptography library doesn't retain a reference to our mutable buffer.
        return AESGCM(bytes(self._buf))

    def new_self_test(self) -> tuple[bytes, bytes]:
        """Return `(nonce, ciphertext_with_tag)` for the pinned self-test payload.

        Matches `omkit-go/crypto.(*KUser).NewSelfTest`.
        """
        nonce = os.urandom(_NONCE_SIZE)
        ct = self._aead().encrypt(nonce, _SELF_TEST_PAYLOAD, _SELF_TEST_AAD)
        return nonce, ct

    def verify_self_test(self, nonce: bytes, ciphertext: bytes) -> None:
        """Round-trip verify. Raises `ValueError` on any failure.

        Matches `omkit-go/crypto.(*KUser).VerifySelfTest`.
        """
        try:
            pt = self._aead().decrypt(nonce, ciphertext, _SELF_TEST_AAD)
        except InvalidTag as exc:
            raise ValueError("selftest open: authentication failure") from exc
        if pt != _SELF_TEST_PAYLOAD:
            raise ValueError("selftest payload mismatch")

    def __repr__(self) -> str:  # never leak the key material
        return f"KUser(<{KUSER_SIZE} bytes redacted>)"


__all__ = ["KUser", "KUSER_SIZE"]
