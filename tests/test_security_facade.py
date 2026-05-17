"""packages/omur-sdk/tests/test_security_facade.py — omkit.security re-exports sanitation helpers.

exports: EXPECTED_EXPORTS | test_security_facade_identity_matches_sanitize() | test_security_facade_sanitize_callables() | test_security_facade_all_matches_imports_exactly() | test_security_facade_does_not_leak_internals()
rules:   The security facade must maintain exact import parity with all public functions from `omkit.security` and must not expose any internal module references or leak implementation details through its public interface.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import sys

from omkit.security import (
    sanitize_llm_output,
    sanitize_html,
    sanitize_llm_response,
    extract_json,
    log_security_event,
)

EXPECTED_EXPORTS = {
    "sanitize_llm_output",
    "sanitize_html",
    "sanitize_llm_response",
    "extract_json",
    "log_security_event",
}


def test_security_facade_identity_matches_sanitize():
    from omkit import sanitize

    assert sanitize_llm_output is sanitize.sanitize_llm_output
    assert sanitize_html is sanitize.sanitize_html
    assert sanitize_llm_response is sanitize.sanitize_llm_response
    assert extract_json is sanitize.extract_json


def test_security_facade_sanitize_callables():
    for fn in (sanitize_llm_output, sanitize_html, sanitize_llm_response, extract_json, log_security_event):
        assert callable(fn)


def test_security_facade_all_matches_imports_exactly():
    import omkit.security as facade

    declared = set(getattr(facade, "__all__", ()))
    assert declared == EXPECTED_EXPORTS, (
        f"__all__ drift: declared={declared}, expected={EXPECTED_EXPORTS}"
    )


def test_security_facade_does_not_leak_internals():
    to_purge = [m for m in sys.modules if m.startswith("omkit.internal")]
    for m in to_purge:
        del sys.modules[m]

    import omkit.security  # noqa: F401

    leaked = [m for m in sys.modules if m.startswith("omkit.internal")]
    assert not leaked, f"facade leaked private modules: {leaked}"
