"""omkit/crypto/__init__.py — AES-256-GCM envelope primitives shared with omkit-go/crypto.

Cross-SDK contract: byte-for-byte compatible with `github.com/omurlabs/omkit-go/crypto`.
Envelope layout: `nonce(12) || ciphertext || tag(16)` — no magic, no version
header, no key id; the calling KMS layer owns key identity.

For the short string/value encryption used by `omkit.encryption` (settings
secrets), use that module instead — it is a thin AES-256-GCM wrapper sharing
this primitive but ships a versioned URL-safe base64 token format.

exports: wrap | unwrap | AADMeta | AADMetrics | AADContent | AADEmbeddingsChunks | AAD_META | AAD_METRICS | AAD_CONTENT | AAD_EMBEDDINGS_CHUNKS | KUser | KUSER_SIZE | InvalidEnvelopeError | InvalidKeyError
rules:   AES-256-GCM envelope must remain byte-for-byte compatible with omkit-go/crypto. Never change AAD constants without a versioned rotation (e.g. -v2). Pure-CPU sync API — KMS adapters add async on top.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/crypto
message:
"""

from __future__ import annotations

from omkit.crypto.aad import (
    AAD_CONTENT,
    AAD_EMBEDDINGS_CHUNKS,
    AAD_META,
    AAD_METRICS,
    AADContent,
    AADEmbeddingsChunks,
    AADMeta,
    AADMetrics,
)
from omkit.crypto.aes_gcm import (
    InvalidEnvelopeError,
    InvalidKeyError,
    unwrap,
    wrap,
)
from omkit.crypto.kuser import KUSER_SIZE, KUser

__all__ = [
    "wrap",
    "unwrap",
    "InvalidEnvelopeError",
    "InvalidKeyError",
    "AADMeta",
    "AADMetrics",
    "AADContent",
    "AADEmbeddingsChunks",
    "AAD_META",
    "AAD_METRICS",
    "AAD_CONTENT",
    "AAD_EMBEDDINGS_CHUNKS",
    "KUser",
    "KUSER_SIZE",
]
