"""tests/test_cross_runtime_settings.py — Cross-SDK settings ciphertext.

Pins decryption of realistic tenant_settings shapes (anthropic / openai /
openrouter API keys) against fixed `v1` tokens. A Python-side change that
silently breaks the wire format (AAD drift, prefix change, base64 alphabet
swap) fails CI immediately — the regression cannot reach production-encrypted
rows.

Reads two fixture files:

* `tests/golden/settings_v1.json` — Py-produced tokens (regenerated via
  `scripts/regen_golden.py`).
* `omkit-go/internal/testdata/golden/settings.json` — Go-produced tokens
  read from the sibling repo when present. Skip cleanly if the omkit-go
  checkout is missing (CI runs paired; local dev may not).

exports: PY_GOLDEN_PATH | GO_GOLDEN_PATH | test_*
rules:   Never delete a passing pinned case. The AAD constant
         `b"omkit.encryption.v1"` is part of the pinned contract.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | issue #5
message:
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omkit.encryption import decrypt_value

PY_GOLDEN_PATH = Path(__file__).parent / "golden" / "settings_v1.json"
GO_GOLDEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "omkit-go"
    / "internal"
    / "testdata"
    / "golden"
    / "settings.json"
)


def _py_cases() -> list[dict]:
    return json.loads(PY_GOLDEN_PATH.read_text())


def _go_cases() -> list[dict]:
    return json.loads(GO_GOLDEN_PATH.read_text())


def test_py_golden_fixture_present():
    assert PY_GOLDEN_PATH.exists(), f"missing fixture: {PY_GOLDEN_PATH}"
    cases = _py_cases()
    assert len(cases) >= 3, f"expected >=3 cases, got {len(cases)}"


@pytest.mark.parametrize(
    "case",
    _py_cases() if PY_GOLDEN_PATH.exists() else [],
    ids=lambda c: c["name"],
)
def test_decrypt_py_produced_settings_token(case: dict):
    got = decrypt_value(case["token"], case["key_b64"])
    assert got == case["plaintext"], f"{case['name']}: plaintext drift"


@pytest.mark.skipif(
    not GO_GOLDEN_PATH.exists(),
    reason=f"omkit-go fixture not found at {GO_GOLDEN_PATH}",
)
@pytest.mark.parametrize(
    "case",
    _go_cases() if GO_GOLDEN_PATH.exists() else [],
    ids=lambda c: c["name"],
)
def test_decrypt_go_produced_settings_token(case: dict):
    """Decrypt a token produced by omkit-go's Encrypt — true cross-runtime pin."""
    got = decrypt_value(case["token"], case["key_b64"])
    assert got == case["plaintext"], f"{case['name']}: plaintext drift from Go-produced token"
