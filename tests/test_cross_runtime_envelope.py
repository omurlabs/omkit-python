"""tests/test_cross_runtime_envelope.py — Cross-SDK envelope wire-compat tests.

Pins `omkit.jobqueue.envelope.wrap` / `unwrap` against a fixed set of canonical
JSON byte-strings checked into `tests/golden/envelope_v1.json`. The paired
omkit-go suite reads the same fixture, so any drift on either side fails CI
before the bytes hit Valkey.

A regression here is a wire-compat break — Go workers cannot read Python
envelopes (or vice versa). Fix the producer, never relax the assertion.

exports: GOLDEN_PATH | test_*
rules:   Never bump ENVELOPE_VERSION without a coordinated fixture update in
         omkit-go/jobqueue/testdata/envelope_v{N}.json. The version-pin test
         catches the bump-only mistake.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | issue #5
message:
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omkit.jobqueue.envelope import (
    ENVELOPE_VERSION,
    Envelope,
    unwrap,
    wrap,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "envelope_v1.json"
GO_GOLDEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "omkit-go"
    / "internal"
    / "testdata"
    / "golden"
    / "envelope.json"
)


def _cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text())


def _go_cases() -> list[dict]:
    return json.loads(GO_GOLDEN_PATH.read_text())


def test_envelope_version_pinned():
    """Hard-pin ENVELOPE_VERSION so a stealth bump fails CI.

    Bumping to v2 requires (1) a new tests/golden/envelope_v2.json fixture,
    (2) a paired omkit-go change, and (3) updating this assertion in the
    same PR. Forgetting any of those breaks production.
    """
    assert ENVELOPE_VERSION == 1


def test_golden_fixture_present():
    assert GOLDEN_PATH.exists(), f"missing golden fixture: {GOLDEN_PATH}"
    cases = _cases()
    assert len(cases) >= 2, f"expected >=2 cases, got {len(cases)}"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_wrap_produces_canonical_bytes(case: dict):
    """wrap() output must equal the canonical byte-string in the fixture.

    Equality at the string level == equality at the byte level (ASCII JSON).
    """
    got = wrap(
        case["tenant_id"],
        case["payload"],
        request_id=case.get("request_id", ""),
    ).decode("utf-8")
    assert got == case["expected_json"], f"{case['name']}: wrap byte drift"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_unwrap_round_trips_canonical_bytes(case: dict):
    """unwrap() of the canonical bytes must produce the expected fields.

    Proves Python can read whatever the canonical (Go-compatible) producer wrote.
    """
    env = unwrap(case["expected_json"].encode("utf-8"))
    assert isinstance(env, Envelope)
    assert env.version == ENVELOPE_VERSION
    assert env.tenant_id == case["tenant_id"]
    assert env.payload == case["payload"]
    assert env.request_id == case.get("request_id", "")


def test_unwrap_tolerates_missing_request_id():
    """Old Go envelopes (pre-RequestID) omit the key — Python must accept."""
    raw = (
        b'{"version":1,"tenant_id":"33333333-3333-3333-3333-333333333333",'
        b'"payload":{"x":1}}'
    )
    env = unwrap(raw)
    assert env.request_id == ""


@pytest.mark.skipif(
    not GO_GOLDEN_PATH.exists(),
    reason=f"omkit-go fixture not found at {GO_GOLDEN_PATH}",
)
@pytest.mark.parametrize(
    "case",
    _go_cases() if GO_GOLDEN_PATH.exists() else [],
    ids=lambda c: c["name"],
)
def test_unwrap_go_produced_envelope(case: dict):
    """Unwrap an envelope produced by omkit-go — true cross-runtime pin.

    The Go fixture stores the canonical bytes as base64; decode and feed to
    Python's unwrap(). Fields must match what the Go side recorded.
    """
    import base64

    raw = base64.b64decode(case["envelope_bytes_b64"])
    env = unwrap(raw)
    assert env.version == ENVELOPE_VERSION
    assert env.tenant_id == case["tenant_id"]
    assert env.payload == case["payload"]
    assert env.request_id == case.get("request_id", "")


@pytest.mark.skipif(
    not GO_GOLDEN_PATH.exists(),
    reason=f"omkit-go fixture not found at {GO_GOLDEN_PATH}",
)
@pytest.mark.parametrize(
    "case",
    _go_cases() if GO_GOLDEN_PATH.exists() else [],
    ids=lambda c: c["name"],
)
def test_wrap_matches_go_produced_bytes(case: dict):
    """wrap() output equals Go's bytes for sorted-key payloads.

    Both SDKs emit canonical compact JSON; payloads in fixtures are kept
    single-key or alphabetically ordered so Go's sorted-map output and
    Python's insertion-ordered output agree byte-for-byte.
    """
    import base64

    want = base64.b64decode(case["envelope_bytes_b64"])
    got = wrap(
        case["tenant_id"],
        case["payload"],
        request_id=case.get("request_id", ""),
    )
    assert got == want, f"{case['name']}: byte drift vs Go-produced envelope"
