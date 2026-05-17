"""omkit/kms/base.py — KMS Protocol and shared error types (port of omkit-go/kms/kms.go).

Defines the abstract surface every adapter (LocalDev, OpenBao, AWS, GCP)
must implement. Method signatures use `async def` because the production
adapters all hit network KMS endpoints; sync-only adapters can `return`
immediately without an `await`.

Error model:
  * `KMSAuthError`  — 4xx / permanent (don't retry). Mirrors Go `ErrKMSAuth`.
  * `KMSUnavailableError` — 5xx or network failure / transient (retry with
    backoff). Mirrors Go `ErrKMSUnavailable`.
  * `KMSError` — base class for both, so callers can `except KMSError`.

exports: KMS | KMSError | KMSAuthError | KMSUnavailableError
rules:   Method signatures must remain symmetrical with omkit-go/kms.KMS. WrapDEK implementations MUST prefix the caller-supplied AAD with "purpose|userID|" before passing to the underlying AEAD (or use an equivalent Transit derived-key context); cross-user/cross-purpose unwrap attempts must fail at the auth-tag layer, not at application-level checks.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/kms
message:
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class KMSError(Exception):
    """Base class for KMS errors. Catch this if you don't care which kind."""

    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class KMSUnavailableError(KMSError):
    """Backend is unreachable or returned 5xx. Transient — callers may retry with backoff.

    Mirrors Go `*kms.ErrKMSUnavailable`.
    """

    def __str__(self) -> str:
        return f"kms: unavailable (status {self.status}): {self.message}"


class KMSAuthError(KMSError):
    """Backend returned 4xx (auth failure, bad context, invalid ciphertext).

    Permanent — retrying will not help. Mirrors Go `*kms.ErrKMSAuth`.
    """

    def __str__(self) -> str:
        return f"kms: auth error (status {self.status}): {self.message}"


@runtime_checkable
class KMS(Protocol):
    """Ops-held wrapping interface. Cross-SDK mirror of `omkit-go/kms.KMS`.

    Static-key flow (tenant / system api_key encryption):
      * `wrap` / `unwrap` operate on a named `key_id` owned by ops.

    DEK envelope flow (per-user document encryption):
      * `wrap_dek` / `unwrap_dek` derive a per-(user_id, purpose) wrapping
        key. The implementation MUST prefix `aad` with `"purpose|user_id|"`
        before using it as GCM AAD (or use a Transit derived-key context
        with the same semantics) so cross-user / cross-purpose unwrap
        attempts fail at the authentication tag.
      * `delete_user_keys` is the cryptographic-shred primitive for GDPR
        Art. 17.
    """

    async def wrap(self, key_id: str, plaintext: bytes, aad: bytes) -> bytes:
        ...

    async def unwrap(self, key_id: str, blob: bytes, aad: bytes) -> bytes:
        ...

    async def current_version(self, key_id: str) -> str:
        """Opaque version token (e.g. `"v1"`) for `key_id`."""
        ...

    async def wrap_dek(
        self,
        user_id: str,
        purpose: str,
        plain_dek: bytes,
        aad: bytes,
    ) -> tuple[bytes, str]:
        """Encrypt `plain_dek` under a key derived for `(user_id, purpose)`.

        Returns `(wrapped, version)`. Callers store `version` alongside the
        wrapped blob for rotation bookkeeping.
        """
        ...

    async def unwrap_dek(
        self,
        user_id: str,
        purpose: str,
        wrapped: bytes,
        aad: bytes,
    ) -> bytes:
        """Reverse `wrap_dek`. Any `(user_id, purpose, aad)` mismatch raises an auth error."""
        ...

    async def delete_user_keys(self, user_id: str) -> None:
        """Crypto-shred for right-to-erasure. Backend-specific semantics — see adapter docs."""
        ...


__all__ = [
    "KMS",
    "KMSError",
    "KMSAuthError",
    "KMSUnavailableError",
]
