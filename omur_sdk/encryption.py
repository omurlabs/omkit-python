"""packages/omur-sdk/omur_sdk/encryption.py — Fernet-based encryption utilities for Omur settings secrets.

exports: generate_key() | encrypt_value(plaintext, key) | decrypt_value(ciphertext, key) | mask_secret(value)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    """Generate a new Fernet-compatible key (URL-safe base64)."""
    return Fernet.generate_key().decode()


def encrypt_value(plaintext: str, key: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, key: str) -> str:
    """Decrypt a base64-encoded ciphertext string.

    Raises cryptography.fernet.InvalidToken if the key is wrong or the
    token is malformed/tampered.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()


def mask_secret(value: str | None) -> str | None:
    """Mask a secret for API display.

    - Values >= 10 chars: first 4 + '****' + last 4  (e.g. 'sk-a****Xk2f')
    - Values 4-9 chars:   first 2 + '****' + last 2  (e.g. 'ab****ef')
    - Values < 4 chars:   '****'
    - None or empty:      returns None
    """
    if not value:
        return None
    n = len(value)
    if n >= 10:
        return value[:4] + "****" + value[-4:]
    if n >= 4:
        return value[:2] + "****" + value[-2:]
    return "****"
