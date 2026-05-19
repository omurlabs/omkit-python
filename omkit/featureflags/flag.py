"""omkit/featureflags/flag.py — Flag dataclass + JSON parser + role validator.

exports: Flag | parse_from_json | validate_roles
rules:   Wire shape `{"enabled": bool, "roles": ["admin",...]}` matches
         omkit-go/featureflags/flag.go. Malformed JSON yields a disabled
         (deny-all) Flag — never raise here; the caller already trusts the
         backing store and a parse error must fail safe.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

from omkit.auth.roles import Role


@dataclass(frozen=True)
class Flag:
    """Normalized shape of one feature flag."""

    enabled: bool = False
    roles: tuple[Role, ...] = field(default_factory=tuple)


_KNOWN_ROLE_VALUES = {r.value for r in Role}


def validate_roles(roles: Iterable[str]) -> str:
    """Return the first role string not in the known catalog, or "" if all OK.

    Empty input is valid (deny-all is a legitimate state).
    """
    for r in roles:
        if r not in _KNOWN_ROLE_VALUES:
            return r
    return ""


def parse_from_json(raw: bytes | str | dict) -> Flag:
    """Parse a flag row's value_json into a Flag.

    Accepted shape: `{"enabled": bool, "roles": ["admin", ...]}`. Malformed
    JSON, missing fields, or unknown role strings collapse to a disabled
    Flag (deny-all) — fail safe.
    """
    try:
        if isinstance(raw, dict):
            obj = raw
        else:
            obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return Flag()
    if not isinstance(obj, dict):
        return Flag()

    enabled = bool(obj.get("enabled", False))
    role_strs = obj.get("roles") or []
    if not isinstance(role_strs, list):
        return Flag()

    parsed: list[Role] = []
    for s in role_strs:
        if not isinstance(s, str) or s not in _KNOWN_ROLE_VALUES:
            # Skip unknown roles silently — they cannot grant access anyway.
            continue
        parsed.append(Role(s))
    return Flag(enabled=enabled, roles=tuple(parsed))
