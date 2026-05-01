"""packages/omur-sdk/omur_sdk/internal/crypto.py — Re-export of encryption primitives for SDK-internal consumers.

External services should NOT import from here; this module exists so the
SDK's own SettingsManager has a named location for the helpers that isn't
the top-level public surface.

exports: none
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from omur_sdk.encryption import (  # noqa: F401
    decrypt_value,
    encrypt_value,
    generate_key,
    mask_secret,
)
