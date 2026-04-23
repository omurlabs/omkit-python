"""Data facade — re-exports DB pool and session-store primitives.

Additive grouping. Flat-module imports continue to work.
"""

from omur_sdk.dbpool import (
    create_pool,
    new_session_pool,
    sqlalchemy_asyncpg_connect_args,
)
from omur_sdk.sessions import (
    NotFound,
    Session,
    SessionStore,
    new_store,
)

__all__ = [
    "create_pool",
    "new_session_pool",
    "sqlalchemy_asyncpg_connect_args",
    "SessionStore",
    "Session",
    "NotFound",
    "new_store",
]
