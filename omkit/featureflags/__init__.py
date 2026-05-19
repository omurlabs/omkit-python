"""omkit/featureflags/__init__.py — role-scoped feature flag primitive.

A flag is {enabled: bool, roles: [Role]}; a caller is allowed iff the flag
is enabled AND the caller's roles intersect the allowlist. Unknown flag
denies; empty roles list denies everyone (deny-by-default).

Storage is pluggable via the Store protocol; built-in implementations are
StaticStore (in-memory, tests) and PostgresStore (TTL-cached, reads
`app_settings` where key LIKE 'flag.%').

exports: Flag | Store | StaticStore | PostgresStore | allowed |
         validate_roles | parse_from_json | load_for_service
rules:   Wire shape `{"enabled": bool, "roles": ["admin",...]}` and the
         `app_settings.key LIKE 'flag.%'` query are part of the cross-SDK
         contract — coordinate with omkit-go before changing.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

from omkit.featureflags.allowed import allowed
from omkit.featureflags.flag import Flag, parse_from_json, validate_roles
from omkit.featureflags.postgres import PostgresStore, load_for_service
from omkit.featureflags.store import StaticStore, Store

__all__ = [
    "Flag",
    "Store",
    "StaticStore",
    "PostgresStore",
    "allowed",
    "validate_roles",
    "parse_from_json",
    "load_for_service",
]
