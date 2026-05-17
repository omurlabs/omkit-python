"""omkit/events.py — DEPRECATED: use ``omkit.eventbus`` instead.

Deprecated shim; will be removed in a future release once downstream
consumers migrate to ``omkit.eventbus``. Imports from this module emit a
DeprecationWarning at import time.

exports: none
rules:   The events module must maintain backward compatibility for all existing event handlers and cannot introduce breaking changes to the event dispatching mechanism. All event classes must inherit from a single base Event class and implement a standardized serialization interface. The module cannot depend on external libraries beyond the standard Python library and must not introduce circular dependencies with other modules in the omkit package.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import warnings

from omkit.eventbus import EventBus  # noqa: F401

warnings.warn(
    "omkit.events is deprecated; import from omkit.eventbus instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["EventBus"]
