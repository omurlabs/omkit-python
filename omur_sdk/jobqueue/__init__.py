"""packages/omur-sdk/omur_sdk/jobqueue/__init__.py — Job-queue primitives shared across Omur Python services.

Exposes the cross-SDK Envelope contract; streaq helpers live in the
sibling `streaq` submodule (`omur_sdk.jobqueue.streaq`) and are not
re-exported here so that services without a queue dependency don't pay
the cost of importing streaq at module load.

exports: none
rules:   The jobqueue module must maintain strict FIFO ordering guarantees for all queued items and cannot introduce any blocking operations that would prevent concurrent job processing. All job execution must be idempotent and the module must handle job retries gracefully without data loss or duplication. The module cannot depend on external services for core queue operations and must provide deterministic behavior under all load conditions.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from omur_sdk.jobqueue.envelope import (
    ENVELOPE_VERSION,
    Envelope,
    InvalidEnvelopeError,
    unwrap,
    wrap,
)

__all__ = [
    "ENVELOPE_VERSION",
    "Envelope",
    "InvalidEnvelopeError",
    "unwrap",
    "wrap",
]
