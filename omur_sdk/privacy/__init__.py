"""omur_sdk.privacy — privacy-layer primitives shared across Omur services.

Currently exposes the encrypted-episode-body envelope used on the Omur ↔ gnokee
boundary. See ADR-029 "Encrypted Episode Body for gnokee Ingest".
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

__all__ = [
    "AADMismatchError",
    "EncryptedBody",
    "KMSAdapter",
    "UnsupportedSchemaError",
    "build_aad",
    "decrypt_episode_body",
    "encrypt_episode_body",
]
