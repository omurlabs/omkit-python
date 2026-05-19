"""omkit/auth/roles.py — Role enum + context binding + check helpers.

Mirrors omkit-go/auth/roles.go field-for-field. Uses contextvars.ContextVar
for ambient role propagation (async-safe, equivalent to Go's context.Value).

exports: Role | ROLE_ADMIN | ROLE_SUPPORT | ROLE_USER | roles_from_groups |
         with_roles | roles_from_context | has_role | require_role |
         RoleRequiredError
rules:   groupToRoles is the source of truth; adding a role requires a code
         change. Unknown group keys are silently ignored.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/auth
message:
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Iterable, Iterator


class Role(str, Enum):
    """One of a fixed set of authorization roles."""

    ADMIN = "admin"
    SUPPORT = "support"
    # USER covers two distinct actors that land in the same audit column:
    # (a) omur-user role members, for role-gated admin/settings features;
    # (b) self-service auth-path events (signup, login, logout, credential
    # add/delete) where the account owner IS the actor — no IdP role is
    # required for that flow because auth handlers emit the entry directly.
    # admin_audit_log's CHECK constraint on `role` must include 'user'.
    USER = "user"


ROLE_ADMIN = Role.ADMIN
ROLE_SUPPORT = Role.SUPPORT
ROLE_USER = Role.USER


# groupToRoles is the source of truth for Zitadel-role-key → Role mapping.
# Keys MUST match the `role_key` field of the corresponding
# zitadel_project_role resource in infra/zitadel/roles.tf (singular).
_GROUP_TO_ROLES: dict[str, tuple[Role, ...]] = {
    "omur-admin": (Role.ADMIN,),
    "omur-support": (Role.SUPPORT,),
    "omur-user": (Role.USER,),
}


def roles_from_groups(groups: Iterable[str] | None) -> list[Role]:
    """Return the deduplicated union of roles granted by the given group keys.

    Unknown keys are silently ignored. Order of the returned list is not
    specified.
    """
    if not groups:
        return []
    seen: set[Role] = set()
    out: list[Role] = []
    for g in groups:
        for r in _GROUP_TO_ROLES.get(g, ()):
            if r in seen:
                continue
            seen.add(r)
            out.append(r)
    return out


_ROLES_CTX: ContextVar[tuple[Role, ...]] = ContextVar("omkit.auth.roles", default=())


@contextmanager
def with_roles(roles: Iterable[Role]) -> Iterator[None]:
    """Attach the given roles to the current async context.

    Use as a context manager — roles are unset on exit. Equivalent to Go's
    `auth.WithRoles(ctx, roles)`.

        with with_roles([Role.ADMIN]):
            assert has_role(Role.ADMIN)
    """
    token = _ROLES_CTX.set(tuple(roles))
    try:
        yield
    finally:
        _ROLES_CTX.reset(token)


def roles_from_context() -> tuple[Role, ...]:
    """Return the roles attached by `with_roles`, or empty tuple."""
    return _ROLES_CTX.get()


def has_role(want: Role) -> bool:
    """Report whether the current context carries the given role."""
    return want in _ROLES_CTX.get()


class RoleRequiredError(PermissionError):
    """Raised by require_role when the current context lacks the role."""

    def __init__(self, want: Role):
        super().__init__(f"forbidden: missing required role {want.value!r}")
        self.want = want


def require_role(want: Role) -> None:
    """Raise RoleRequiredError when the current context lacks the given role.

    Framework-agnostic: callers map RoleRequiredError onto whatever 403
    response shape their HTTP layer uses. For FastAPI, catch in an exception
    handler and emit `{"error": str(exc)}` with status 403.
    """
    if not has_role(want):
        raise RoleRequiredError(want)
