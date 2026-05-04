"""packages/omur-sdk/tests/test_dbpool_role.py — Pure-function tests for the role plumbing in.

``sqlalchemy_asyncpg_connect_args`` — no DB required.

The SET ROLE switch was previously a SQLAlchemy sync "connect" event
listener that called ``dbapi_conn.cursor()``; under concurrent first-use
SQLAlchemy's greenlet adapter would occasionally see a half-initialized
connection and raise ``'NoneType' object has no attribute 'cursor'``.
The fix moves the role switch into asyncpg's ``server_settings`` so it
runs inside the connection handshake. These tests pin the contract of
the helper so the fix can't silently regress.

exports: test_connect_args_default_includes_omur_app_role() | test_connect_args_custom_role() | test_connect_args_role_none_omits_server_settings()
rules:   The module must maintain backward compatibility with existing database connection patterns and cannot alter the default role behavior without explicit version bumping. All connection arguments must be validated at import time to prevent runtime failures. The module's public API cannot introduce breaking changes to the `sqlalchemy_asyncpg_connect_args` function signature or its returned argument structure.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from omur_sdk.dbpool import sqlalchemy_asyncpg_connect_args


def test_connect_args_default_includes_omur_app_role():
    """
    Rules:   The function requires that pgbouncer-compatibility knobs (statement_cache_size and prepared_statement_cache_size) must remain set to 0 even when server_settings is present, to maintain compatibility with pgbouncer.
    """
    args = sqlalchemy_asyncpg_connect_args()
    assert args["server_settings"] == {"role": "omur_app"}
    # The pgbouncer-compatibility knobs must still be present.
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0


def test_connect_args_custom_role():
    """
    Rules:   The role parameter in sqlalchemy_asyncpg_connect_args must be a valid PostgreSQL role that exists on the database server, otherwise the connection will fail with an authentication error.
    """
    args = sqlalchemy_asyncpg_connect_args(role="readonly_app")
    assert args["server_settings"] == {"role": "readonly_app"}


def test_connect_args_role_none_omits_server_settings():
    """
    Rules:   When role is explicitly set to None, the server_settings key must be completely omitted from the returned args dictionary, but pgbouncer-compatibility knobs must still be present.
    """
    args = sqlalchemy_asyncpg_connect_args(role=None)
    assert "server_settings" not in args
    # pgbouncer-compat knobs still present on the opt-out path.
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0
