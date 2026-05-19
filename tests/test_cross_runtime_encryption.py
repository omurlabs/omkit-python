"""tests/test_cross_runtime_encryption.py — Cross-SDK encryption wire-compat.

Pins `omkit.encryption.decrypt_value` (used by `omkit.settings.get_secret`)
against fixed `v1`-prefixed tokens checked into `tests/golden/encryption_v1.json`.

Round-trip with random nonces happens in `test_encryption.py`. This file's job
is the opposite: hold a frozen token across releases so a Python-side change
that breaks the wire format fails CI immediately.

When the omkit-go side ships its paired fixture, replace the Python-generated
tokens here with Go-generated ones (or add a third Go-produced case). The
decrypt path is symmetric, so Python-generated tokens are valid pinning
artifacts today — they only become "cross-runtime golden" once Go writes them.

exports: GOLDEN_PATH | test_*
rules:   Never delete a passing pinned case to "make the suite pass" — find
         the regression. AAD constant `b"omkit.encryption.v1"` is part of the
         pinned contract; changing it requires bumping the v1 prefix.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | issue #5
message:
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from omkit.encryption import InvalidToken, decrypt_value, encrypt_value

GOLDEN_PATH = Path(__file__).parent / "golden" / "encryption_v1.json"


def _cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text())


def test_golden_fixture_present():
    assert GOLDEN_PATH.exists(), f"missing golden fixture: {GOLDEN_PATH}"
    cases = _cases()
    assert len(cases) >= 2, f"expected >=2 cases, got {len(cases)}"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_decrypt_pinned_token(case: dict):
    """Decrypt a frozen `v1` token — proves wire format is stable."""
    got = decrypt_value(case["token"], case["key_b64"])
    assert got == case["plaintext"], f"{case['name']}: plaintext drift"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_token_has_v1_prefix(case: dict):
    """Token decodes to base64 and begins with `b"v1"`."""
    raw = base64.urlsafe_b64decode(case["token"].encode("ascii"))
    assert raw[:2] == b"v1", f"{case['name']}: missing v1 prefix"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_round_trip_with_pinned_key(case: dict):
    """Encrypt-then-decrypt under the pinned key returns input.

    Catches a Python-only regression where encrypt_value produces a token that
    decrypt_value cannot read (e.g. AAD or nonce-size drift).
    """
    fresh = encrypt_value(case["plaintext"], case["key_b64"])
    assert decrypt_value(fresh, case["key_b64"]) == case["plaintext"]


def test_decrypt_wrong_key_fails():
    case = _cases()[0]
    other = base64.urlsafe_b64encode(b"\x99" * 32).decode("ascii")
    with pytest.raises(InvalidToken):
        decrypt_value(case["token"], other)


def test_decrypt_tampered_token_fails():
    case = _cases()[0]
    raw = bytearray(base64.urlsafe_b64decode(case["token"].encode("ascii")))
    raw[-1] ^= 0xFF  # flip a bit in the tag
    bad = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(InvalidToken):
        decrypt_value(bad, case["key_b64"])
