"""Job-queue primitives shared across Omur Python services.

Currently exposes the cross-SDK Envelope contract. Worker / task / UI helpers
for streaq land in subsequent commits.
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
