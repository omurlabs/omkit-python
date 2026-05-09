"""packages/omur-sdk/tests/test_data_facade.py — omur_sdk.data re-exports DB + session primitives.

exports: EXPECTED_EXPORTS | test_data_facade_identity_matches_underlying() | test_data_facade_types() | test_data_facade_all_matches_imports_exactly() | test_data_facade_does_not_leak_internals()
rules:   The data facade must maintain exact import equivalence with direct module imports, cannot expose internal implementation details through sys.modules, and must preserve identity consistency between facade and underlying components.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import sys

from omur_sdk.data import (
    build_retrieval_engine,
    create_pool,
    new_session_pool,
    sqlalchemy_asyncpg_connect_args,
    SessionStore,
    Session,
    NotFound,
    new_store,
)

EXPECTED_EXPORTS = {
    "build_retrieval_engine",
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

    assert build_retrieval_engine is dbpool.build_retrieval_engine
    assert create_pool is dbpool.create_pool
    assert new_session_pool is dbpool.new_session_pool
    assert sqlalchemy_asyncpg_connect_args is dbpool.sqlalchemy_asyncpg_connect_args
    assert SessionStore is sessions.SessionStore
    assert Session is sessions.Session
    assert NotFound is sessions.NotFound
    assert new_store is sessions.new_store


def test_data_facade_types():
    assert callable(build_retrieval_engine)
    assert callable(create_pool)
    assert callable(new_session_pool)
    assert callable(new_store)
    assert isinstance(Session, type)
    assert issubclass(NotFound, Exception)


def test_data_facade_all_matches_imports_exactly():
    """
    Rules:   The test validates that the __all__ tuple in the data facade module exactly matches the EXPECTED_EXPORTS set, ensuring all public API exports are properly declared and no unexpected items are exposed.
    """
    import omur_sdk.data as facade

    declared = set(getattr(facade, "__all__", ()))
    assert declared == EXPECTED_EXPORTS, (
        f"__all__ drift: declared={declared}, expected={EXPECTED_EXPORTS}"
    )


def test_data_facade_does_not_leak_internals():
    """
    Rules:   Future developers must ensure that internal modules are properly purged from sys.modules to prevent leakage, as this test verifies the facade doesn't expose private implementation details.
    """
    to_purge = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    for m in to_purge:
        del sys.modules[m]

    import omur_sdk.data  # noqa: F401

    leaked = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    assert not leaked, f"facade leaked private modules: {leaked}"
