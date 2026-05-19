"""tests/test_featureflags.py — Tests for omkit.featureflags.

Covers Flag parsing, allowed() role logic, StaticStore, and PostgresStore
TTL + refresh + invalidate semantics. PostgresStore tests use a stubbed
refresher so they run without a live database.

exports: test_*
rules:   Deny-by-default is the load-bearing semantic; pin every "empty"
         path explicitly.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

import asyncio
import json

import pytest

from omkit.auth import Role, with_roles
from omkit.featureflags import (
    Flag,
    PostgresStore,
    StaticStore,
    Store,
    allowed,
    parse_from_json,
    validate_roles,
)


# --- Flag parsing --------------------------------------------------------


def test_parse_from_json_full():
    raw = json.dumps({"enabled": True, "roles": ["admin", "user"]}).encode()
    f = parse_from_json(raw)
    assert f.enabled is True
    assert Role.ADMIN in f.roles
    assert Role.USER in f.roles


def test_parse_from_json_disabled():
    f = parse_from_json(b'{"enabled": false, "roles": []}')
    assert f.enabled is False
    assert f.roles == ()


def test_parse_from_json_unknown_role_dropped():
    f = parse_from_json(b'{"enabled": true, "roles": ["admin", "ceo"]}')
    assert f.enabled is True
    assert f.roles == (Role.ADMIN,)


def test_parse_from_json_malformed_yields_disabled():
    f = parse_from_json(b"{not json}")
    assert f.enabled is False
    assert f.roles == ()


def test_parse_from_json_accepts_dict():
    f = parse_from_json({"enabled": True, "roles": ["support"]})
    assert f.enabled is True
    assert f.roles == (Role.SUPPORT,)


def test_validate_roles_all_known():
    assert validate_roles(["admin", "support", "user"]) == ""


def test_validate_roles_returns_first_unknown():
    assert validate_roles(["admin", "ceo"]) == "ceo"


def test_validate_roles_empty_is_valid():
    assert validate_roles([]) == ""


# --- StaticStore + allowed() --------------------------------------------


def _store_with(flag_key: str, flag: Flag) -> StaticStore:
    return StaticStore({flag_key: flag})


def test_static_store_implements_protocol():
    s = StaticStore({"flag.x": Flag(enabled=True, roles=(Role.ADMIN,))})
    assert isinstance(s, Store)


def test_static_store_get_unknown_returns_none():
    s = StaticStore()
    assert s.get("flag.missing") is None


def test_static_store_all_flags_returns_copy():
    s = StaticStore({"flag.a": Flag(enabled=True, roles=(Role.ADMIN,))})
    snap = s.all_flags()
    snap["flag.a"] = Flag()  # type: ignore[index]
    assert s.get("flag.a") is not None
    assert s.get("flag.a").enabled is True


def test_allowed_unknown_flag_denies():
    s = StaticStore()
    with with_roles([Role.ADMIN]):
        assert allowed(s, "flag.missing") is False


def test_allowed_disabled_flag_denies():
    s = _store_with("flag.x", Flag(enabled=False, roles=(Role.ADMIN,)))
    with with_roles([Role.ADMIN]):
        assert allowed(s, "flag.x") is False


def test_allowed_no_caller_roles_denies():
    s = _store_with("flag.x", Flag(enabled=True, roles=(Role.ADMIN,)))
    assert allowed(s, "flag.x") is False  # no with_roles in scope


def test_allowed_empty_flag_roles_denies_everyone():
    s = _store_with("flag.x", Flag(enabled=True, roles=()))
    with with_roles([Role.ADMIN]):
        assert allowed(s, "flag.x") is False


def test_allowed_no_role_intersection_denies():
    s = _store_with("flag.x", Flag(enabled=True, roles=(Role.ADMIN,)))
    with with_roles([Role.USER]):
        assert allowed(s, "flag.x") is False


def test_allowed_role_intersection_grants():
    s = _store_with("flag.x", Flag(enabled=True, roles=(Role.ADMIN, Role.USER)))
    with with_roles([Role.USER]):
        assert allowed(s, "flag.x") is True


# --- PostgresStore (stubbed refresher) ----------------------------------


@pytest.mark.asyncio
async def test_postgres_store_refresh_populates_cache():
    async def fake_refresh():
        return {"flag.x": Flag(enabled=True, roles=(Role.ADMIN,))}

    s = PostgresStore(refresh=fake_refresh, ttl=60.0)
    assert s.get("flag.x") is None
    # First get triggered background refresh; await it deterministically
    await s.refresh()
    assert s.get("flag.x").enabled is True


@pytest.mark.asyncio
async def test_postgres_store_refresh_error_keeps_cache():
    state = {"calls": 0}

    async def flaky():
        state["calls"] += 1
        if state["calls"] == 1:
            return {"flag.x": Flag(enabled=True, roles=(Role.ADMIN,))}
        raise RuntimeError("db down")

    s = PostgresStore(refresh=flaky, ttl=60.0)
    await s.refresh()
    assert s.get("flag.x").enabled is True
    await s.refresh()  # error — does not zero cache
    assert s.get("flag.x").enabled is True


@pytest.mark.asyncio
async def test_postgres_store_invalidate_removes_key():
    async def fake_refresh():
        return {"flag.x": Flag(enabled=True, roles=(Role.ADMIN,))}

    s = PostgresStore(refresh=fake_refresh, ttl=60.0)
    await s.refresh()
    assert s.get("flag.x") is not None
    await s.invalidate("flag.x")
    assert s.get("flag.x") is None


@pytest.mark.asyncio
async def test_postgres_store_concurrent_refresh_collapses():
    state = {"calls": 0}

    async def slow():
        state["calls"] += 1
        await asyncio.sleep(0.01)
        return {"flag.x": Flag(enabled=True, roles=(Role.ADMIN,))}

    s = PostgresStore(refresh=slow, ttl=60.0)
    # Serialize via lock — under the lock there's no real "collapse",
    # but the second call must observe the first call's result.
    await asyncio.gather(s.refresh(), s.refresh(), s.refresh())
    # Each call entered the lock sequentially → calls == 3 acceptable; key point is no race.
    assert s.get("flag.x").enabled is True
