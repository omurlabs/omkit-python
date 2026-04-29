"""Job-queue primitives shared across Omur Python services.

Exposes the cross-SDK Envelope contract; streaq helpers live in the
sibling `streaq` submodule (`omur_sdk.jobqueue.streaq`) and are not
re-exported here so that services without a queue dependency don't pay
the cost of importing streaq at module load.
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
