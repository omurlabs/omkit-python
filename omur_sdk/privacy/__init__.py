"""omur_sdk.privacy — privacy-layer primitives shared across Omur services.

Exposes:

- The encrypted-episode-body envelope used on the Omur ↔ gnokee boundary
  (ADR-029).
- The per-request :class:`PrivacyClass` used to keep routing decisions
  auditable across local / hybrid / cloud deployments (Track 4 of
  `2026-05-03-cloud-readiness-prep.md`).
"""

from __future__ import annotations

from .episode_body import (
    AADMismatchError,
    EncryptedBody,
    KMSAdapter,
    UnsupportedSchemaError,
    build_aad,
    decrypt_episode_body,
    encrypt_episode_body,
)
from .privacy_class import (
    HEADER_NAME,
    PrivacyClass,
    allows_cloud,
    parse_privacy_class,
)

__all__ = [
    "AADMismatchError",
    "EncryptedBody",
    "HEADER_NAME",
    "KMSAdapter",
    "PrivacyClass",
    "UnsupportedSchemaError",
    "allows_cloud",
    "build_aad",
    "decrypt_episode_body",
    "encrypt_episode_body",
    "parse_privacy_class",
]
