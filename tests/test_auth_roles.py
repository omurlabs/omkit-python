"""tests/test_auth_roles.py — Tests for omkit.auth.roles.

exports: test_*
rules:   Role catalog values are part of the cross-SDK contract —
         changing them requires a coordinated omkit-go change.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/auth
message:
"""

from __future__ import annotations

import pytest

from omkit.auth import (
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


def test_role_values_pinned():
    """Cross-SDK contract: must equal Go's omkit-go/auth/roles.go literals."""
    assert Role.ADMIN.value == "admin"
    assert Role.SUPPORT.value == "support"
    assert Role.USER.value == "user"


def test_role_aliases():
    assert ROLE_ADMIN is Role.ADMIN
    assert ROLE_SUPPORT is Role.SUPPORT
    assert ROLE_USER is Role.USER


def test_roles_from_groups_empty():
    assert roles_from_groups([]) == []
    assert roles_from_groups(None) == []


def test_roles_from_groups_known_keys():
    out = roles_from_groups(["omur-admin", "omur-user"])
    assert set(out) == {Role.ADMIN, Role.USER}


def test_roles_from_groups_unknown_keys_ignored():
    out = roles_from_groups(["omur-admin", "unknown-group"])
    assert out == [Role.ADMIN]


def test_roles_from_groups_dedup():
    out = roles_from_groups(["omur-admin", "omur-admin"])
    assert out == [Role.ADMIN]


def test_context_empty_by_default():
    assert roles_from_context() == ()
    assert not has_role(Role.ADMIN)


def test_with_roles_attaches_and_unsets():
    assert not has_role(Role.ADMIN)
    with with_roles([Role.ADMIN]):
        assert has_role(Role.ADMIN)
        assert Role.ADMIN in roles_from_context()
    assert not has_role(Role.ADMIN)


def test_with_roles_multiple():
    with with_roles([Role.ADMIN, Role.SUPPORT]):
        assert has_role(Role.ADMIN)
        assert has_role(Role.SUPPORT)
        assert not has_role(Role.USER)


def test_require_role_passes_when_present():
    with with_roles([Role.ADMIN]):
        require_role(Role.ADMIN)  # no raise


def test_require_role_raises_when_missing():
    with pytest.raises(RoleRequiredError) as exc:
        require_role(Role.ADMIN)
    assert exc.value.want == Role.ADMIN
    assert "admin" in str(exc.value)


def test_require_role_raises_when_other_role_present():
    with with_roles([Role.USER]):
        with pytest.raises(RoleRequiredError):
            require_role(Role.ADMIN)
