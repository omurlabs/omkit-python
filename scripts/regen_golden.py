"""scripts/regen_golden.py — regenerate cross-runtime golden fixtures.

Usage: python scripts/regen_golden.py

Writes:
  - tests/golden/envelope_v1.json
  - tests/golden/encryption_v1.json
  - tests/golden/settings_v1.json

Envelope cases are deterministic (Python wrap() emits canonical compact JSON
with insertion-ordered keys; payloads in this script are kept single-key or
alphabetically ordered so they match Go's sorted-map output byte-for-byte).
Encryption / settings tokens carry random nonces, so each run rotates them.
Both SDKs read the committed values; regen + commit is the source of truth.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from omkit.encryption import encrypt_value
from omkit.jobqueue.envelope import wrap

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"


def build_envelope_cases() -> list[dict]:
    cases = [
        {
            "name": "v1_no_request_id",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "request_id": "",
            "payload": {"doc_id": "abc"},
        },
        {
            "name": "v1_with_request_id",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "request_id": "req-abc-123",
            "payload": {"task": "summarize"},
        },
    ]
    out: list[dict] = []
    for c in cases:
        raw = wrap(c["tenant_id"], c["payload"], request_id=c["request_id"])
        out.append(
            {
                **c,
                "expected_json": raw.decode("utf-8"),
            }
        )
    return out


def build_encryption_cases() -> list[dict]:
    keys = [
        base64.urlsafe_b64encode(b"B" * 32).decode("ascii"),
        base64.urlsafe_b64encode(b"B" * 32).decode("ascii"),
    ]
    plaintexts = ["sk-prod-secret-token-v1", ""]
    names = ["v1_short_plaintext", "v1_empty_plaintext"]
    out: list[dict] = []
    for name, key, plain in zip(names, keys, plaintexts, strict=True):
        out.append(
            {
                "name": name,
                "key_b64": key,
                "plaintext": plain,
                "token": encrypt_value(plain, key),
            }
        )
    return out


def build_settings_cases() -> list[dict]:
    """Realistic tenant_settings / account_keys shapes.

    Mirrors omkit-go/internal/testdata/golden/settings.json so a Python
    settings ciphertext refactor is caught before it reaches production.
    """
    entries = [
        ("anthropic_api_key", "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"),
        ("openai_api_key", "sk-proj-YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY"),
        ("openrouter_api_key", "sk-or-v1-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"),
    ]
    out: list[dict] = []
    for i, (name, plain) in enumerate(entries):
        key = base64.urlsafe_b64encode(bytes([0x20 + i]) * 32).decode("ascii")
        out.append(
            {
                "name": name,
                "key_b64": key,
                "plaintext": plain,
                "token": encrypt_value(plain, key),
                "produced_by": "py",
            }
        )
    return out


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    write_json(GOLDEN_DIR / "envelope_v1.json", build_envelope_cases())
    write_json(GOLDEN_DIR / "encryption_v1.json", build_encryption_cases())
    write_json(GOLDEN_DIR / "settings_v1.json", build_settings_cases())
    print(f"wrote fixtures to {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
