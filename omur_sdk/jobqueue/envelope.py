"""Cross-SDK envelope contract for job-queue payloads.

Every task enqueued via streaq (Python) or Asynq (Go) is wrapped in this
envelope. Workers unwrap on receive, validate, and run the handler under the
tenant's RLS scope.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

ENVELOPE_VERSION = 1


class InvalidEnvelopeError(ValueError):
    """Envelope failed validation. Workers should dead-letter (no retry)."""


class Envelope(BaseModel):
    """Tenant-scoped task envelope.

    `payload` is opaque — handlers parse it into their own pydantic model.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    version: int = Field(default=ENVELOPE_VERSION)
    tenant_id: str
    payload: dict[str, Any]

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"tenant_id not a valid uuid: {v!r}") from exc
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"envelope version must be >= 1, got {v}")
        if v > ENVELOPE_VERSION:
            raise ValueError(
                f"unsupported envelope version {v} (max {ENVELOPE_VERSION})"
            )
        return v


def wrap(tenant_id: str, payload: dict[str, Any]) -> bytes:
    """Build an envelope and serialize to JSON bytes for streaq enqueue.

    Raises InvalidEnvelopeError if tenant_id is not a UUID.
    """
    try:
        env = Envelope(
            version=ENVELOPE_VERSION,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValidationError as exc:
        raise InvalidEnvelopeError(str(exc)) from exc
    return env.model_dump_json().encode("utf-8")


def unwrap(data: bytes | str | dict[str, Any]) -> Envelope:
    """Parse and validate inbound envelope.

    Accepts raw JSON bytes/str or a pre-parsed dict (streaq sometimes hands
    handlers the decoded payload directly). Raises InvalidEnvelopeError on
    any validation failure — callers must dead-letter, not retry.
    """
    if isinstance(data, (bytes, str)):
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise InvalidEnvelopeError(f"envelope not valid json: {exc}") from exc
    else:
        obj = data
    if not isinstance(obj, dict):
        raise InvalidEnvelopeError(f"envelope must be a json object, got {type(obj).__name__}")
    try:
        return Envelope.model_validate(obj)
    except ValidationError as exc:
        raise InvalidEnvelopeError(str(exc)) from exc
