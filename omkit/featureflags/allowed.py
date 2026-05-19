"""omkit/featureflags/allowed.py — role-scoped flag check.

exports: allowed
rules:   Deny-by-default semantics: unknown flag, disabled flag, empty
         caller roles, empty allowlist roles, or no role intersection all
         return False. A typo in a flag key must fail safe.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

from omkit.auth.roles import roles_from_context
from omkit.featureflags.store import Store


def allowed(store: Store, key: str) -> bool:
    """Report whether the caller in the current async context is permitted
    to see the feature guarded by key.

    Semantics:
      * Unknown flag → False (deny-by-default; a typo fails safe).
      * flag.enabled == False → False.
      * caller_roles ∩ flag.roles == ∅ → False (empty flag.roles denies everyone).
      * Otherwise True.
    """
    flag = store.get(key)
    if flag is None or not flag.enabled:
        return False
    caller_roles = roles_from_context()
    if not caller_roles or not flag.roles:
        return False
    return any(cr in flag.roles for cr in caller_roles)
