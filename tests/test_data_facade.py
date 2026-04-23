"""Facade smoke test — omur_sdk.data re-exports DB + session primitives."""

import sys

from omur_sdk.data import (
    create_pool,
    new_session_pool,
    sqlalchemy_asyncpg_connect_args,
    SessionStore,
    Session,
    NotFound,
    new_store,
)

EXPECTED_EXPORTS = {
    "create_pool",
    "new_session_pool",
    "sqlalchemy_asyncpg_connect_args",
    "SessionStore",
    "Session",
    "NotFound",
    "new_store",
}


def test_data_facade_identity_matches_underlying():
    from omur_sdk import dbpool, sessions

    assert create_pool is dbpool.create_pool
    assert new_session_pool is dbpool.new_session_pool
    assert sqlalchemy_asyncpg_connect_args is dbpool.sqlalchemy_asyncpg_connect_args
    assert SessionStore is sessions.SessionStore
    assert Session is sessions.Session
    assert NotFound is sessions.NotFound
    assert new_store is sessions.new_store


def test_data_facade_types():
    assert callable(create_pool)
    assert callable(new_session_pool)
    assert callable(new_store)
    assert isinstance(Session, type)
    assert issubclass(NotFound, Exception)


def test_data_facade_all_matches_imports_exactly():
    import omur_sdk.data as facade

    declared = set(getattr(facade, "__all__", ()))
    assert declared == EXPECTED_EXPORTS, (
        f"__all__ drift: declared={declared}, expected={EXPECTED_EXPORTS}"
    )


def test_data_facade_does_not_leak_internals():
    to_purge = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    for m in to_purge:
        del sys.modules[m]

    import omur_sdk.data  # noqa: F401

    leaked = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    assert not leaked, f"facade leaked private modules: {leaked}"
