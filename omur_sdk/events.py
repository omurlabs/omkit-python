"""DEPRECATED: use ``omur_sdk.eventbus`` instead.

This module is retained only as a re-export shim so that any stale imports
keep working while emitting a DeprecationWarning at import time. Scheduled
for removal after 2026-06-01 once STATUS.md confirms zero references.
"""

import warnings

from omur_sdk.eventbus import EventBus  # noqa: F401

warnings.warn(
    "omur_sdk.events is deprecated; import from omur_sdk.eventbus instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["EventBus"]
