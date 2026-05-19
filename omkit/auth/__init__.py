"""omkit/auth/__init__.py — role catalog + audit-log writer for admin actions.

Identity comes from Zitadel via oauth2-proxy forward-auth headers; roles are
computed from group membership using a hardcoded map. Adding a role is a code
change — that's the right friction for a security-sensitive list. Role keys
live in Terraform (infra/zitadel/roles.tf), same source as omkit-go/auth.

This module is framework-agnostic: it does NOT depend on FastAPI, Starlette,
or asyncpg directly. Callers extract headers and pass them in.

exports: Role | ROLE_ADMIN | ROLE_SUPPORT | ROLE_USER | roles_from_groups |
         with_roles | roles_from_context | has_role | require_role |
         RoleRequiredError | AuditEntry | write_audit_entry
rules:   The role catalog is a code-time security boundary — never read from
         config or env. groupToRoles must stay in lockstep with
         omkit-go/auth/roles.go and infra/zitadel/roles.tf.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/auth
message:
"""

from __future__ import annotations

from omkit.auth.audit import AuditEntry, write_audit_entry
from omkit.auth.roles import (
    ROLE_ADMIN,
    ROLE_SUPPORT,
    ROLE_USER,
    Role,
    RoleRequiredError,
    has_role,
    require_role,
    roles_from_context,
    roles_from_groups,
    with_roles,
)

__all__ = [
    "Role",
    "ROLE_ADMIN",
    "ROLE_SUPPORT",
    "ROLE_USER",
    "roles_from_groups",
    "with_roles",
    "roles_from_context",
    "has_role",
    "require_role",
    "RoleRequiredError",
    "AuditEntry",
    "write_audit_entry",
]
