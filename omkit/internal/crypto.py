"""packages/omur-sdk/omkit/internal/crypto.py — Re-export of encryption primitives for SDK-internal consumers.

External services should NOT import from here; this module exists so the
SDK's own SettingsManager has a named location for the helpers that isn't
the top-level public surface.

exports: none
rules:   The cryptographic module must maintain deterministic behavior across all environments to ensure consistent encryption/decryption results. All cryptographic operations must be thread-safe and not introduce any side effects that could compromise security. The module cannot depend on external services or network calls during cryptographic operations.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from omkit.encryption import (  # noqa: F401
    decrypt_value,
    encrypt_value,
    generate_key,
    mask_secret,
)
