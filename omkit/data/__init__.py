"""omkit/data/__init__.py — re-exports DB pool and session-store primitives.

Additive grouping. Flat-module imports continue to work.

exports: none
rules:   The module must maintain backward compatibility for all existing data import paths and cannot introduce breaking changes to the public API surface. All data processing functions must be thread-safe and handle concurrent access without race conditions. The module cannot depend on external packages beyond the standard library and explicitly declared dependencies in the package manifest.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from omkit.dbpool import (
    build_retrieval_engine,
    create_pool,
    new_session_pool,
    sqlalchemy_asyncpg_connect_args,
)
from omkit.sessions import (
    NotFound,
    Session,
    SessionStore,
    new_store,
)

__all__ = [
    "build_retrieval_engine",
    "create_pool",
    "new_session_pool",
    "sqlalchemy_asyncpg_connect_args",
    "SessionStore",
    "Session",
    "NotFound",
    "new_store",
]
