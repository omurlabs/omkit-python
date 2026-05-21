"""Verify that base `import omkit` does not pull I/O extras.

Acceptance for issue #7: stateless consumers (e.g. cerebellum) install
plain `omkit` without dragging asyncpg, sqlalchemy, redis, or cryptography.
This test fences regressions: any new top-level import of those packages
under `omkit/` will fail here.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


_HEAVY = ("asyncpg", "sqlalchemy", "redis", "cryptography")


def _run_in_subprocess(code: str) -> tuple[int, str, str]:
    """Run `code` in a fresh interpreter so module-cache state is clean."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_base_import_omkit_no_heavy_deps() -> None:
    """`import omkit` must not load asyncpg/sqlalchemy/redis/cryptography."""
    code = textwrap.dedent(
        """
        import sys
        import omkit  # noqa: F401
        heavy = [m for m in sys.modules if m.split('.')[0] in (
            'asyncpg', 'sqlalchemy', 'redis', 'cryptography'
        )]
        print('\\n'.join(sorted(heavy)))
        """
    )
    rc, out, err = _run_in_subprocess(code)
    assert rc == 0, f"subprocess failed: {err}"
    loaded = [line for line in out.strip().splitlines() if line]
    assert loaded == [], (
        "base `import omkit` pulled I/O extras into sys.modules: " + ", ".join(loaded)
    )


def test_dbpool_actionable_error_without_asyncpg() -> None:
    """`omkit.dbpool.create_pool` raises actionable ImportError if asyncpg absent."""
    code = textwrap.dedent(
        """
        import asyncio
        import sys
        # Block asyncpg before import: cache the sentinel so any later
        # `import asyncpg` re-raises ImportError.
        sys.modules['asyncpg'] = None
        from omkit.dbpool import create_pool
        try:
            asyncio.run(create_pool('postgres://x'))
        except ImportError as e:
            msg = str(e)
            assert 'omkit[db]' in msg, msg
            print('OK')
        else:
            raise AssertionError('expected ImportError')
        """
    )
    rc, out, err = _run_in_subprocess(code)
    assert rc == 0, f"subprocess failed: {err}"
    assert "OK" in out


def test_aes_gcm_actionable_error_without_cryptography() -> None:
    """`omkit.crypto.aes_gcm.wrap_with_key` raises actionable error w/o cryptography."""
    code = textwrap.dedent(
        """
        import sys
        for name in list(sys.modules):
            if name == 'cryptography' or name.startswith('cryptography.'):
                del sys.modules[name]
        sys.modules['cryptography'] = None
        from omkit.crypto.aes_gcm import wrap_with_key
        try:
            wrap_with_key(b'\\x00' * 32, b'x', b'aad')
        except ImportError as e:
            msg = str(e)
            assert 'omkit[crypto]' in msg, msg
            print('OK')
        else:
            raise AssertionError('expected ImportError')
        """
    )
    rc, out, err = _run_in_subprocess(code)
    assert rc == 0, f"subprocess failed: {err}"
    assert "OK" in out
