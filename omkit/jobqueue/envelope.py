"""omkit/jobqueue/envelope.py — Cross-SDK envelope contract for job-queue payloads.

Every task enqueued via streaq (Python) or Asynq (Go) is wrapped in this
envelope. Workers unwrap on receive, validate, and run the handler under the
tenant's RLS scope.

exports: ENVELOPE_VERSION | class InvalidEnvelopeError | class Envelope | wrap(tenant_id, payload) | unwrap(data)
rules:   The Envelope class must maintain strict tenant isolation and never allow cross-tenant data leakage. All envelope validation must be immutable and deterministic to ensure consistent task processing across distributed workers. The wrap/unwrap functions must handle all serialization edge cases including nested data structures and preserve original payload integrity during transformation.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
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
    Cross-SDK contract: matches Go's packages/omur-go-sdk/jobqueue/Envelope
    field-for-field. Empty payloads and missing version keys are rejected by
    both sides — wrap()/Wrap() produce envelopes that round-trip cleanly
    between Python and Go workers.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    # `version` is required — no default. Go's Unwrap rejects envelopes
    # with version==0 (missing field zero-value), so the Python side must
    # reject the missing-key case symmetrically.
    version: int
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

    @field_validator("payload")
    @classmethod
    def _validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError(
                "payload must not be empty — Go workers dead-letter empty payloads"
            )
        return v


def wrap(tenant_id: str, payload: dict[str, Any]) -> bytes:
    """Build an envelope and serialize to JSON bytes for streaq enqueue.

    Raises InvalidEnvelopeError if tenant_id is not a UUID.

    Rules:   tenant_id must be a valid UUID string, otherwise InvalidEnvelopeError is raised
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

    Rules:   Input must be valid JSON bytes/str or a pre-parsed dict. If pre-parsed dict is provided, it must already be validated and contain the expected envelope structure. The function raises InvalidEnvelopeError for any validation failure, which should be handled by dead-lettering rather than retrying.
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
