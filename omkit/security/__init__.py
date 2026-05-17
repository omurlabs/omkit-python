"""omkit/security/__init__.py — re-exports sanitation helpers and event logger.

The ``omkit.encryption`` module has a mixed public surface and is
intentionally NOT re-exported here; continue to import from
``omkit.encryption`` directly. Private crypto primitives live in
``omkit.internal.crypto`` and are never re-exported.

exports: none
rules:   The security module must maintain a strict separation between authentication and authorization logic, with no direct dependencies on external SDKs or third-party libraries that could introduce security vulnerabilities. All security-related operations must be deterministic and not rely on external state or environment variables. The module's public API must remain stable and backward-compatible across all minor version updates.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from omkit.sanitize import (
    extract_json,
    sanitize_html,
    sanitize_llm_output,
    sanitize_llm_response,
)
from omkit.security.events import log_security_event

__all__ = [
    "sanitize_llm_output",
    "sanitize_html",
    "sanitize_llm_response",
    "extract_json",
    "log_security_event",
]
