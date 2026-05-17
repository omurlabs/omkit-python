"""tests/test_jobqueue_envelope.py — Tests for jobqueue envelope contract.

exports: TID | test_wrap_round_trip() | test_wrap_rejects_bad_tenant() | test_unwrap_accepts_dict() | test_unwrap_rejects_bad_json() | test_unwrap_rejects_non_object() | test_unwrap_rejects_bad_tenant_id() | test_unwrap_rejects_missing_version() | test_unwrap_rejects_empty_payload() | test_wrap_rejects_empty_payload() | test_unwrap_rejects_future_version() | test_unwrap_rejects_negative_version() | test_unwrap_rejects_extra_fields() | test_envelope_frozen()
rules:   The envelope format must always include a valid UUID tenant_id, a positive integer version, and a non-empty payload. Any deviation from this structure must raise an InvalidEnvelopeError. The module does not support backward compatibility for version changes or extra fields in the envelope.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

import json

import pytest

from omkit.jobqueue import (
    ENVELOPE_VERSION,
    Envelope,
    InvalidEnvelopeError,
    unwrap,
    wrap,
)

TID = "11111111-1111-1111-1111-111111111111"


def test_wrap_round_trip():
    raw = wrap(TID, {"doc_id": "abc"})
    env = unwrap(raw)
    assert env.tenant_id == TID
    assert env.version == ENVELOPE_VERSION
    assert env.payload == {"doc_id": "abc"}


def test_wrap_rejects_bad_tenant():
    """
    Rules:   Tenant ID must be a valid UUID string, or the function will raise InvalidEnvelopeError.
    """
    with pytest.raises(InvalidEnvelopeError, match="uuid"):
        wrap("not-a-uuid", {"x": 1})


def test_unwrap_accepts_dict():
    obj = {"version": 1, "tenant_id": TID, "payload": {"x": 1}}
    env = unwrap(obj)
    assert env.payload == {"x": 1}


def test_unwrap_rejects_bad_json():
    """
    Rules:   Input must be valid JSON; invalid JSON will raise InvalidEnvelopeError.
    """
    with pytest.raises(InvalidEnvelopeError, match="not valid json"):
        unwrap(b"{not json")


def test_unwrap_rejects_non_object():
    """
    Rules:   Input must be a JSON object; strings or other types will raise InvalidEnvelopeError.
    """
    with pytest.raises(InvalidEnvelopeError, match="json object"):
        unwrap(b'"a string"')


def test_unwrap_rejects_bad_tenant_id():
    """
    Rules:   Tenant ID must be a valid UUID string, or the function will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({"version": 1, "tenant_id": "nope", "payload": {}})
    with pytest.raises(InvalidEnvelopeError, match="uuid"):
        unwrap(bogus)


def test_unwrap_rejects_missing_version():
    """Cross-SDK contract: Go rejects envelopes with version==0 (missing
    field zero-value). Python must reject the missing-key case symmetrically
    or a Go-produced "no version" message would be silently upgraded by
    Python while Go dead-letters it.

    Rules:   The 'version' field is required and must not be zero (missing field default), or the function will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({"tenant_id": TID, "payload": {"x": 1}})
    with pytest.raises(InvalidEnvelopeError, match="version"):
        unwrap(bogus)


def test_unwrap_rejects_empty_payload():
    """Cross-SDK contract: Go rejects len(payload) == 0; Python rejects
    empty dict to match.

    Rules:   Payload cannot be an empty dictionary; it must contain data, or the function will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({"version": 1, "tenant_id": TID, "payload": {}})
    with pytest.raises(InvalidEnvelopeError, match="empty"):
        unwrap(bogus)


def test_wrap_rejects_empty_payload():
    """
    Rules:   Payload cannot be an empty dictionary when wrapping; it must contain data, or the function will raise InvalidEnvelopeError.
    """
    with pytest.raises(InvalidEnvelopeError, match="empty"):
        wrap(TID, {})


def test_unwrap_rejects_future_version():
    """
    Rules:   Envelope version must not exceed the supported version; higher versions will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({"version": 99, "tenant_id": TID, "payload": {"x": 1}})
    with pytest.raises(InvalidEnvelopeError, match="unsupported envelope version"):
        unwrap(bogus)


def test_unwrap_rejects_negative_version():
    """
    Rules:   Envelope version must be >= 1; version 0 or negative values will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({"version": 0, "tenant_id": TID, "payload": {"x": 1}})
    with pytest.raises(InvalidEnvelopeError, match=">= 1"):
        unwrap(bogus)


def test_unwrap_rejects_extra_fields():
    """
    Rules:   Envelope must not contain unexpected fields; extra fields will raise InvalidEnvelopeError.
    """
    bogus = json.dumps({
        "version": 1, "tenant_id": TID, "payload": {}, "extra": "field"
    })
    with pytest.raises(InvalidEnvelopeError, match="extra"):
        unwrap(bogus)


def test_envelope_frozen():
    """
    Rules:   Envelope fields are immutable after creation to ensure data integrity and prevent accidental modification of critical metadata like tenant_id.
    """
    env = Envelope(version=1, tenant_id=TID, payload={"x": 1})
    with pytest.raises(Exception):  # pydantic ValidationError on assignment
        env.tenant_id = "different"  # type: ignore[misc]
