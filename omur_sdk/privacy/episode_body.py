"""omur_sdk.privacy.episode_body — encrypted-body wire shape for gnokee ingest.

Reference implementation of ADR-029 "Encrypted Episode Body for gnokee Ingest".
The envelope is intentionally narrow:

* Single fixed schema (``omur.encrypted_body.v1``).
* AES-256-GCM only.
* AAD constructed from a four-part tuple, never freeform.
* Wrapped DEK travels in the envelope alongside the ciphertext so gnokee replay
  has everything it needs (the wrapped DEK is useless without KMS access).

The KMS adapter is injected. In production it is OpenBao Transit, AWS KMS, or
GCP KMS (ADR-024). In tests a stub adapter suffices — see
``packages/omur-sdk/tests/test_privacy_episode_body.py``.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA_V1 = "omur.encrypted_body.v1"
ALG_AES_256_GCM = "AES-256-GCM"

_AAD_PREFIX = "omur:gnokee:episode:"


class UnsupportedSchemaError(ValueError):
    """Raised when an envelope advertises a schema this SDK cannot handle."""


class AADMismatchError(ValueError):
    """Raised when the four-part AAD does not match the envelope's AAD field.

    Failing here gives a clear error before invoking KMS / GCM, which would
    otherwise fail with an opaque authentication-tag error.
    """


class KMSAdapter(Protocol):
    """Subset of the KMS interface the privacy helpers need.

    Production adapters in Go SDK (``packages/omur-go-sdk/kms``) implement the
    full interface; the Python side calls into them via Spine for now. Helper
    accepts any object providing these two methods so tests can inject stubs.
    """

    def wrap_dek(
        self,
        *,
        user_id: str,
        purpose: str,
        plain_dek: bytes,
        aad: bytes,
    ) -> tuple[bytes, str]:
        """Wrap ``plain_dek`` for ``(user_id, purpose)`` with the given AAD.

        Returns ``(wrapped_dek, version_token)``. The version token is what the
        envelope's ``key_id`` carries through to ``unwrap_dek``.
        """

    def unwrap_dek(
        self,
        *,
        user_id: str,
        purpose: str,
        wrapped_dek: bytes,
        aad: bytes,
        version: str,
    ) -> bytes:
        """Reverse ``wrap_dek``. Implementations check ``aad`` and ``version``."""


@dataclass(frozen=True)
class EncryptedBody:
    """Wire envelope handed across the Omur ↔ gnokee boundary.

    All bytes-shaped fields are base64url strings on the wire. The dataclass
    keeps them as ``str`` to make JSON / dict round-trips total.
    """

    schema: str
    key_id: str
    nonce: str
    ciphertext: str
    aad: str
    alg: str
    wrapped_dek: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "key_id": self.key_id,
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "aad": self.aad,
            "alg": self.alg,
            "wrapped_dek": self.wrapped_dek,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> EncryptedBody:
        missing = {"schema", "key_id", "nonce", "ciphertext", "aad", "alg", "wrapped_dek"} - payload.keys()
        if missing:
            raise ValueError(f"EncryptedBody missing required fields: {sorted(missing)}")
        return cls(**{k: payload[k] for k in payload if k in cls.__dataclass_fields__})


def build_aad(*, episode_id: str, tenant_id: str, schema_label: str) -> str:
    """Construct the literal AAD string for an episode body.

    The construction is fixed by ADR-029: ``omur:gnokee:episode:<episode_id>:<tenant_id>:<schema_label>``.
    Callers must not pass an AAD directly to encrypt / decrypt helpers.
    """

    if not episode_id or not tenant_id or not schema_label:
        raise ValueError("episode_id, tenant_id, and schema_label are all required for AAD construction")
    if any(":" in part for part in (episode_id, tenant_id, schema_label)):
        raise ValueError("AAD parts must not contain ':' — would corrupt the delimiter")
    return f"{_AAD_PREFIX}{episode_id}:{tenant_id}:{schema_label}"


def _b64e(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


def encrypt_episode_body(
    plaintext: bytes,
    *,
    kms: KMSAdapter,
    tenant_id: str,
    episode_id: str,
    schema_label: str,
) -> EncryptedBody:
    """Encrypt ``plaintext`` for handoff to gnokee.

    Generates a fresh AES-256 DEK, encrypts under AES-256-GCM with a CSPRNG
    nonce, wraps the DEK via ``kms``, returns the envelope. The unwrapped DEK
    is best-effort zeroised before return; callers should treat the envelope
    as the only output.
    """

    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("plaintext must be bytes")
    aad = build_aad(episode_id=episode_id, tenant_id=tenant_id, schema_label=schema_label)
    aad_bytes = aad.encode("ascii")

    dek = bytearray(os.urandom(32))
    nonce = os.urandom(12)
    try:
        aead = AESGCM(bytes(dek))
        ciphertext = aead.encrypt(nonce, bytes(plaintext), aad_bytes)
        wrapped, version = kms.wrap_dek(
            user_id=tenant_id,
            purpose="gnokee_episode_body",
            plain_dek=bytes(dek),
            aad=aad_bytes,
        )
    finally:
        for i in range(len(dek)):
            dek[i] = 0

    key_id = f"omur:tenant:{tenant_id}:k_user:{version}"
    return EncryptedBody(
        schema=SCHEMA_V1,
        key_id=key_id,
        nonce=_b64e(nonce),
        ciphertext=_b64e(ciphertext),
        aad=aad,
        alg=ALG_AES_256_GCM,
        wrapped_dek=_b64e(wrapped),
    )


def decrypt_episode_body(
    envelope: EncryptedBody,
    *,
    kms: KMSAdapter,
    tenant_id: str,
    episode_id: str,
    schema_label: str,
) -> bytes:
    """Reverse ``encrypt_episode_body``.

    Validates schema and AAD before invoking KMS to keep failure modes clear.
    The unwrapped DEK is zeroised after use.
    """

    if envelope.schema != SCHEMA_V1:
        raise UnsupportedSchemaError(f"unsupported schema: {envelope.schema!r}")
    if envelope.alg != ALG_AES_256_GCM:
        raise UnsupportedSchemaError(f"unsupported alg: {envelope.alg!r}")

    expected_aad = build_aad(episode_id=episode_id, tenant_id=tenant_id, schema_label=schema_label)
    if envelope.aad != expected_aad:
        raise AADMismatchError(
            "envelope AAD does not match (episode_id, tenant_id, schema_label) tuple"
        )
    aad_bytes = expected_aad.encode("ascii")

    version = envelope.key_id.rsplit(":", 1)[-1]
    wrapped = _b64d(envelope.wrapped_dek)
    dek = bytearray(
        kms.unwrap_dek(
            user_id=tenant_id,
            purpose="gnokee_episode_body",
            wrapped_dek=wrapped,
            aad=aad_bytes,
            version=version,
        )
    )
    try:
        aead = AESGCM(bytes(dek))
        return aead.decrypt(_b64d(envelope.nonce), _b64d(envelope.ciphertext), aad_bytes)
    finally:
        for i in range(len(dek)):
            dek[i] = 0
