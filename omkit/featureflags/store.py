"""omkit/featureflags/store.py — Store Protocol + StaticStore impl.

exports: Store | StaticStore
rules:   Store.get is sync (cache read); Store.refresh is async (DB roundtrip).
         StaticStore.refresh is a no-op; the in-memory map is immutable after
         construction.
agent:   claude-opus-4-7 | anthropic | 2026-05-19 | claude-code | parity with omkit-go/featureflags
message:
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from omkit.featureflags.flag import Flag


@runtime_checkable
class Store(Protocol):
    """Read-side contract for a flag backend."""

    def get(self, key: str) -> Flag | None:
        """Return the flag, or None if unknown."""
        ...

    async def refresh(self) -> None:
        """Synchronously reload the backing snapshot. Errors propagate."""
        ...

    def all_flags(self) -> Mapping[str, Flag]:
        """Snapshot of the current cached flag map. Callers must not mutate."""
        ...


class StaticStore:
    """In-memory Store for tests and as a compile-time Protocol sanity check."""

    def __init__(self, flags: Mapping[str, Flag] | None = None):
        self._flags = dict(flags or {})

    def get(self, key: str) -> Flag | None:
        return self._flags.get(key)

    async def refresh(self) -> None:
        return None

    def all_flags(self) -> Mapping[str, Flag]:
        return dict(self._flags)
