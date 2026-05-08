"""omur_sdk.privacy.privacy_class — per-request privacy classification.

Track 4 of `docs/superpowers/plans/2026-05-03-cloud-readiness-prep.md`.

Privacy class is an explicit per-request signal (carried over the
`X-Omur-Privacy-Class` header) that lets routing decisions stay auditable
across local-only, hybrid, and cloud-only deployments. Hostname-based
routing (Ollama vs. cloud proxy) is not a contract that survives the
cloud migration; this class is.

Three values:

- ``public``    — non-sensitive content; safe for any backend.
- ``tenant``    — tenant-scoped content; default; safe for any backend
                  the tenant has authorised but not for shared/system
                  endpoints.
- ``sensitive`` — protected health information or equivalent; only
                  on-tenant or local backends; cloud routes refuse.

Default is ``tenant`` — callers that omit the header get the safe
middle ground. Callers that mean ``public`` must say so explicitly.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

HEADER_NAME: Final[str] = "X-Omur-Privacy-Class"


class PrivacyClass(str, Enum):
    """Per-request privacy classification (see module docstring)."""

    PUBLIC = "public"
    TENANT = "tenant"
    SENSITIVE = "sensitive"

    @classmethod
    def default(cls) -> "PrivacyClass":
        return cls.TENANT


def parse_privacy_class(raw: str | None) -> PrivacyClass:
    """Normalise an arbitrary header value into a :class:`PrivacyClass`.

    Accepts case-insensitive matches and surrounding whitespace.
    Falls back to :meth:`PrivacyClass.default` when the value is missing,
    blank, or unrecognised — never raises. The fall-back is the **safe**
    direction: an unparseable header should not silently downgrade
    sensitive content to ``public``.
    """

    if raw is None:
        return PrivacyClass.default()
    normalised = raw.strip().lower()
    if not normalised:
        return PrivacyClass.default()
    for member in PrivacyClass:
        if member.value == normalised:
            return member
    return PrivacyClass.default()


def allows_cloud(privacy_class: PrivacyClass) -> bool:
    """Return True when a backend that may egress beyond the tenant boundary
    is permitted for this class. ``sensitive`` is the only refusal."""

    return privacy_class is not PrivacyClass.SENSITIVE


__all__ = [
    "HEADER_NAME",
    "PrivacyClass",
    "allows_cloud",
    "parse_privacy_class",
]
