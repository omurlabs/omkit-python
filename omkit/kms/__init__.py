"""omkit/kms/__init__.py — Key Management Service interface and built-in adapters.

Mirrors `omkit-go/kms`. Two adapters ship:

  * `LocalDevKMS` — in-process HMAC-derived keys for dev/integration tests.
    Wraps and unwraps blobs that are byte-for-byte compatible with the Go
    adapter when constructed with the same master secret.
  * `OpenBaoKMS` — HashiCorp OpenBao / Vault Transit secrets engine, AppRole
    auth, derived per-(userID, purpose, aad) keys. Wire-compatible with
    `omkit-go/kms/openbao.go`.

All methods are `async def` to match the Python SDK convention even though the
LocalDev adapter never blocks on I/O — keeps the call sites uniform across
adapters.

exports: KMS | LocalDevKMS | OpenBaoKMS | KMSError | KMSAuthError | KMSUnavailableError
rules:   The KMS interface must remain symmetrical with omkit-go/kms — adding a method here without adding it to Go (and vice versa) is a contract break. Adapter constructors must validate required config at construction time, not at first call.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/kms
message:
"""

from __future__ import annotations

from omkit.kms.base import KMS, KMSAuthError, KMSError, KMSUnavailableError
from omkit.kms.localdev import LocalDevKMS
from omkit.kms.openbao import OpenBaoKMS

__all__ = [
    "KMS",
    "LocalDevKMS",
    "OpenBaoKMS",
    "KMSError",
    "KMSAuthError",
    "KMSUnavailableError",
]
