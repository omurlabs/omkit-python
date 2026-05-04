"""packages/omur-sdk/omur_sdk/events.py — DEPRECATED: use ``omur_sdk.eventbus`` instead.

This module is retained only as a re-export shim so that any stale imports
keep working while emitting a DeprecationWarning at import time. Scheduled
for removal after 2026-06-01 once STATUS.md confirms zero references.

exports: none
rules:   The events module must maintain backward compatibility for all existing event handlers and cannot introduce breaking changes to the event dispatching mechanism. All event classes must inherit from a single base Event class and implement a standardized serialization interface. The module cannot depend on external libraries beyond the standard Python library and must not introduce circular dependencies with other modules in the omur_sdk package.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import warnings

from omur_sdk.eventbus import EventBus  # noqa: F401

warnings.warn(
    "omur_sdk.events is deprecated; import from omur_sdk.eventbus instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["EventBus"]
