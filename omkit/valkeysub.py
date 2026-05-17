"""omkit/valkeysub.py — Redis/Valkey pub/sub subscriber with auto-reconnect.

Async port of `omkit-go/valkeysub`. Subscribes to a Redis channel and
yields message payloads, transparently reconnecting with a fixed backoff
on disconnect. Shutdown is cooperative via `asyncio.CancelledError` —
cancel the consuming task to stop.

Divergence from Go: exposes an `AsyncIterator[bytes]` (`messages()`)
instead of a callback-style `Subscribe(handler)`. Python idiom; same
semantics. Default reconnect backoff is 1.0s here vs 5.0s in Go because
the spec asks for `reconnect_backoff_s=1.0`; callers can override.

exports: class Subscriber
rules:   Must reconnect on transport errors without losing the subscription
         loop, and must propagate `asyncio.CancelledError` for cooperative
         shutdown. Yields raw `bytes` payloads — callers decode/parse.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from Go
message:
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class Subscriber:
    """Subscribe to a Redis pub/sub channel with automatic reconnect.

    Iterate `messages()` to receive raw `bytes` payloads. On connection
    error the iterator sleeps `reconnect_backoff_s` seconds, re-subscribes,
    and resumes — matching the Go `Subscribe()` reconnect loop. Cancel the
    consuming task to stop.
    """

    def __init__(
        self,
        client: "aioredis.Redis",
        channel: str,
        *,
        reconnect_backoff_s: float = 1.0,
    ) -> None:
        self._r = client
        self._channel = channel
        self._backoff = reconnect_backoff_s

    @property
    def reconnect_backoff_s(self) -> float:
        return self._backoff

    async def messages(self) -> AsyncIterator[bytes]:
        """Yield message payloads as `bytes`. Reconnects on error.

        Runs until the consuming task is cancelled. Each reconnect attempt
        is preceded by `await asyncio.sleep(reconnect_backoff_s)`.
        """
        while True:
            pubsub = self._r.pubsub()
            try:
                await pubsub.subscribe(self._channel)
                while True:
                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=None,
                    )
                    if msg is None:
                        continue
                    data = msg.get("data")
                    if data is None:
                        continue
                    if isinstance(data, str):
                        data = data.encode()
                    elif not isinstance(data, (bytes, bytearray)):
                        # Subscribe-control payloads (counts) — skip.
                        continue
                    yield bytes(data)
            except asyncio.CancelledError:
                # Cooperative shutdown — let it propagate after cleanup.
                try:
                    await pubsub.unsubscribe(self._channel)
                except Exception:
                    pass
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
                raise
            except Exception:
                # Transport / protocol error — close and retry after backoff.
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
                await asyncio.sleep(self._backoff)
                continue
