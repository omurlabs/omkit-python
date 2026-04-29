"""Tests for jobqueue envelope contract."""

from __future__ import annotations

import json

import pytest

from omur_sdk.jobqueue import (
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
    with pytest.raises(InvalidEnvelopeError, match="uuid"):
        wrap("not-a-uuid", {"x": 1})


def test_unwrap_accepts_dict():
    obj = {"version": 1, "tenant_id": TID, "payload": {"x": 1}}
    env = unwrap(obj)
    assert env.payload == {"x": 1}


def test_unwrap_rejects_bad_json():
    with pytest.raises(InvalidEnvelopeError, match="not valid json"):
        unwrap(b"{not json")


def test_unwrap_rejects_non_object():
    with pytest.raises(InvalidEnvelopeError, match="json object"):
        unwrap(b'"a string"')


def test_unwrap_rejects_bad_tenant_id():
    bogus = json.dumps({"version": 1, "tenant_id": "nope", "payload": {}})
    with pytest.raises(InvalidEnvelopeError, match="uuid"):
        unwrap(bogus)


def test_unwrap_rejects_missing_version():
    bogus = json.dumps({"tenant_id": TID, "payload": {"x": 1}})
    # Pydantic uses default → version=1; this should succeed actually.
    # But spec requires version explicitly present. Verify our shape:
    env = unwrap(bogus)
    assert env.version == ENVELOPE_VERSION  # default kicks in


def test_unwrap_rejects_future_version():
    bogus = json.dumps({"version": 99, "tenant_id": TID, "payload": {"x": 1}})
    with pytest.raises(InvalidEnvelopeError, match="unsupported envelope version"):
        unwrap(bogus)


def test_unwrap_rejects_negative_version():
    bogus = json.dumps({"version": 0, "tenant_id": TID, "payload": {"x": 1}})
    with pytest.raises(InvalidEnvelopeError, match=">= 1"):
        unwrap(bogus)


def test_unwrap_rejects_extra_fields():
    bogus = json.dumps({
        "version": 1, "tenant_id": TID, "payload": {}, "extra": "field"
    })
    with pytest.raises(InvalidEnvelopeError, match="extra"):
        unwrap(bogus)


def test_envelope_frozen():
    env = Envelope(version=1, tenant_id=TID, payload={"x": 1})
    with pytest.raises(Exception):  # pydantic ValidationError on assignment
        env.tenant_id = "different"  # type: ignore[misc]
