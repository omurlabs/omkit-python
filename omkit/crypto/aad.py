"""omkit/crypto/aad.py — AAD purpose-string constants shared with omkit-go/crypto.

AAD strings bind each per-domain DEK to the data it protects. Changing any
value invalidates every existing ciphertext encrypted with that AAD, so
rotations are versioned (e.g. `-v2`) and migrated separately. The values must
match `omkit-go/crypto/aad.go` byte-for-byte.

The Go names (`AADMeta`, `AADMetrics`, ...) are exported verbatim; Python-
idiomatic UPPER_SNAKE aliases (`AAD_META`, ...) are provided for readability.

exports: AADMeta | AADMetrics | AADContent | AADEmbeddingsChunks | AAD_META | AAD_METRICS | AAD_CONTENT | AAD_EMBEDDINGS_CHUNKS
rules:   AAD constants must remain identical to omkit-go/crypto/aad.go. Adding a new domain requires a corresponding Go change in the same release. Rotations bump the trailing -vN suffix.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/crypto
message:
"""

from __future__ import annotations

from typing import Final

# Go-symbol names (PascalCase to match the Go package's exported identifiers).
AADMeta: Final[str] = "omur-col-meta-v1"
AADMetrics: Final[str] = "omur-col-metrics-v1"
AADContent: Final[str] = "omur-col-content-v1"
AADEmbeddingsChunks: Final[str] = "omur-col-embeddings-v1"

# Python-idiomatic aliases.
AAD_META: Final[str] = AADMeta
AAD_METRICS: Final[str] = AADMetrics
AAD_CONTENT: Final[str] = AADContent
AAD_EMBEDDINGS_CHUNKS: Final[str] = AADEmbeddingsChunks

__all__ = [
    "AADMeta",
    "AADMetrics",
    "AADContent",
    "AADEmbeddingsChunks",
    "AAD_META",
    "AAD_METRICS",
    "AAD_CONTENT",
    "AAD_EMBEDDINGS_CHUNKS",
]
