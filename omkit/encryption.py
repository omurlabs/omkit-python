"""omkit/encryption.py — Fernet-based encryption utilities for Omur settings secrets.

exports: generate_key() | encrypt_value(plaintext, key) | decrypt_value(ciphertext, key) | mask_secret(value)
rules:   The encryption module must maintain backward compatibility with all existing encrypted data formats and key structures. All cryptographic operations must be deterministic and reproducible across different runtime environments. The module cannot introduce any external dependencies beyond the standard library and the fernet package.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    """Generate a new Fernet-compatible key (URL-safe base64).

    Rules:   Key must be stored securely and never logged or exposed in plaintext. The generated key is URL-safe base64 encoded and should be persisted in a secure key management system.
    """
    return Fernet.generate_key().decode()


def encrypt_value(plaintext: str, key: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext.

    Rules:   The key must be a valid Fernet-compatible key (URL-safe base64 encoded string) or the function will raise a ValueError.
    """
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, key: str) -> str:
    """Decrypt a base64-encoded ciphertext string.

    Raises cryptography.fernet.InvalidToken if the key is wrong or the
    token is malformed/tampered.

    Rules:   The key must match the one used for encryption, and the ciphertext must be a valid Fernet token; otherwise, cryptography.fernet.InvalidToken will be raised.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()


def mask_secret(value: str | None) -> str | None:
    """Mask a secret for API display.

    - Values >= 10 chars: first 4 + '****' + last 4  (e.g. 'sk-a****Xk2f')
    - Values 4-9 chars:   first 2 + '****' + last 2  (e.g. 'ab****ef')
    - Values < 4 chars:   '****'
    - None or empty:      returns None

    Rules:   The function assumes ASCII-compatible strings; non-ASCII characters may produce unexpected masking behavior due to byte-level string slicing.
    """
    if not value:
        return None
    n = len(value)
    if n >= 10:
        return value[:4] + "****" + value[-4:]
    if n >= 4:
        return value[:2] + "****" + value[-2:]
    return "****"
