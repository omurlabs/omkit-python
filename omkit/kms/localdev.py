"""omkit/kms/localdev.py — In-process KMS adapter for dev/integration (port of omkit-go/kms/localdev.go).

Derives every wrapping key from a single 32-byte master secret via HMAC-SHA256
with the exact same labels as the Go adapter:

  * Static key:  `HMAC(master, "omur-kms-derive-v1:" + key_id)`
  * DEK key:     `HMAC(master, "user-" + user_id + "-" + purpose)`

The DEK AAD binding follows Go's `bindAAD`:
  effective_aad = (purpose + "|" + user_id + "|").encode() + caller_aad

A blob wrapped by `omkit-go/kms.LocalDevKMS` with the same master is
unwrappable by this Python adapter and vice versa.

NEVER use in production — there is no access-control surface.

Convenience: `LocalDevKMS.from_env()` reads `OMKIT_LOCALDEV_MASTER` (hex or
base64-encoded 32-byte master). The Go adapter does NOT read env; this is a
Python-only convenience that the Go side does not require for interop.

exports: LocalDevKMS
rules:   HMAC labels and AAD binding format must remain identical to omkit-go/kms/localdev.go — any drift breaks cross-SDK interop. Master must be exactly 32 bytes after decoding.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/kms
message:
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from omkit.crypto.aes_gcm import unwrap_with_key, wrap_with_key
from omkit.kms.base import KMSAuthError

_MASTER_SIZE = 32
_STATIC_KEY_LABEL_PREFIX = b"omur-kms-derive-v1:"
_VERSION_TOKEN = "localdev-v1"


def _bind_aad(purpose: str, user_id: str, aad: bytes) -> bytes:
    """Prefix `aad` with `"purpose|user_id|"`. Matches Go `bindAAD`."""
    return f"{purpose}|{user_id}|".encode() + aad


class LocalDevKMS:
    """In-process KMS adapter. Derives keys deterministically from a 32-byte master.

    Wire-compatible with `omkit-go/kms.LocalDevKMS` when constructed with the
    same master secret.
    """

    __slots__ = ("_master",)

    def __init__(self, master: bytes) -> None:
        if len(master) < _MASTER_SIZE:
            raise ValueError(
                f"LocalDevKMS master must be at least {_MASTER_SIZE} bytes, got {len(master)}"
            )
        # Go's `copy(k.master[:], master)` silently truncates / zero-pads to 32.
        # We mirror the truncate-to-32 semantic for interop (zero-pad is rejected
        # above to avoid surprising weak keys).
        self._master = bytes(master[:_MASTER_SIZE])

    @classmethod
    def from_env(cls, env_var: str = "OMKIT_LOCALDEV_MASTER") -> "LocalDevKMS":
        """Construct from `env_var` (hex or base64 32-byte master).

        Python-only convenience; the Go SDK requires the master to be passed
        explicitly. Tries hex first, falls back to base64.
        """
        raw = os.environ.get(env_var)
        if not raw:
            raise RuntimeError(f"{env_var} not set")
        # Try hex.
        decoded: bytes | None
        try:
            decoded = bytes.fromhex(raw.strip())
        except ValueError:
            decoded = None
        if decoded is None or len(decoded) != _MASTER_SIZE:
            # Try base64 (std + url-safe).
            try:
                decoded = base64.b64decode(raw.strip(), validate=True)
            except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
                try:
                    decoded = base64.urlsafe_b64decode(raw.strip() + "==")
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(
                        f"{env_var} must be hex or base64-encoded {_MASTER_SIZE} bytes"
                    ) from exc
        if len(decoded) != _MASTER_SIZE:
            raise ValueError(
                f"{env_var} decoded to {len(decoded)} bytes, need {_MASTER_SIZE}"
            )
        return cls(decoded)

    # --- key derivation -----------------------------------------------------

    def _static_key(self, key_id: str) -> bytes:
        """`HMAC-SHA256(master, "omur-kms-derive-v1:" + key_id)`. Matches Go `key()`."""
        return hmac.new(
            self._master,
            _STATIC_KEY_LABEL_PREFIX + key_id.encode(),
            hashlib.sha256,
        ).digest()

    def _user_key(self, user_id: str, purpose: str) -> bytes:
        """`HMAC-SHA256(master, "user-" + user_id + "-" + purpose)`. Matches Go `userKey()`."""
        return hmac.new(
            self._master,
            f"user-{user_id}-{purpose}".encode(),
            hashlib.sha256,
        ).digest()

    # --- KMS protocol --------------------------------------------------------

    async def wrap(self, key_id: str, plaintext: bytes, aad: bytes) -> bytes:
        return wrap_with_key(self._static_key(key_id), plaintext, aad)

    async def unwrap(self, key_id: str, blob: bytes, aad: bytes) -> bytes:
        return unwrap_with_key(self._static_key(key_id), blob, aad)

    async def current_version(self, key_id: str) -> str:
        # Static "v1" for parity with Go.
        return "v1"

    async def wrap_dek(
        self,
        user_id: str,
        purpose: str,
        plain_dek: bytes,
        aad: bytes,
    ) -> tuple[bytes, str]:
        kek = self._user_key(user_id, purpose)
        bound = _bind_aad(purpose, user_id, aad)
        wrapped = wrap_with_key(kek, plain_dek, bound)
        return wrapped, _VERSION_TOKEN

    async def unwrap_dek(
        self,
        user_id: str,
        purpose: str,
        wrapped: bytes,
        aad: bytes,
    ) -> bytes:
        kek = self._user_key(user_id, purpose)
        bound = _bind_aad(purpose, user_id, aad)
        try:
            return unwrap_with_key(kek, wrapped, bound)
        except Exception as exc:
            # Surface as KMSAuthError so callers can treat all auth failures
            # uniformly across LocalDev / OpenBao adapters.
            raise KMSAuthError(str(exc), status=400) from exc

    async def delete_user_keys(self, user_id: str) -> None:
        """No-op. Keys are derived on demand; deleting the master would erase ALL users.

        Production adapters MUST implement per-user key destruction — see
        `OpenBaoKMS.delete_user_keys` for the tombstone-based approximation.
        """
        return None


__all__ = ["LocalDevKMS"]
