"""packages/omur-sdk/omur_sdk/jobqueue/__init__.py — Job-queue primitives shared across Omur Python services.

Exposes the cross-SDK Envelope contract; streaq helpers live in the
sibling `streaq` submodule (`omur_sdk.jobqueue.streaq`) and are not
re-exported here so that services without a queue dependency don't pay
the cost of importing streaq at module load.

exports: none
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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
