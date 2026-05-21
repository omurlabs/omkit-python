"""omkit/valkeystream.py — Redis/Valkey Streams + consumer-group helpers.

Async port of `omkit-go/valkeystream`. Wraps a `redis.asyncio.Redis` client
with stream producer + consumer helpers using XADD, XREADGROUP, XACK,
XAUTOCLAIM, XGROUP CREATE MKSTREAM. Field naming matches the Go side and
`omkit.eventbus.RedisEventBus` (canonical `payload` field) so cross-language
consumers can co-exist on the same streams.

Divergence from Go: takes an already-built `redis.asyncio.Redis` client
instead of `(addr, password)` — mirrors the SDK convention in
`omkit.valkey.new_client` and `omkit.eventbus.RedisEventBus`.

exports: class StreamMessage | class StreamProducer | class StreamConsumer
rules:   Field names on the wire must match the Go `valkeystream` package so
         Go and Python consumers can interoperate on the same streams. All
         I/O must be async; never block the event loop.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from Go
message:
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Union

if TYPE_CHECKING:
    import redis.asyncio as aioredis


FieldValue = Union[str, bytes]


@dataclass
class StreamMessage:
    """A single Redis Stream entry. Mirrors Go `valkeystream.Message`.

    `id` is the stream entry ID (e.g. "1700000000000-0"). `fields` holds the
    raw field map as returned by Redis; values are bytes when the underlying
    client is constructed without `decode_responses=True` (the SDK default).
    """

    id: str
    fields: dict[str, bytes]


def _normalize_fields(raw: Mapping) -> dict[str, bytes]:
    """Coerce a redis-py field map to `dict[str, bytes]`.

    redis-py returns `dict[bytes, bytes]` when `decode_responses=False` and
    `dict[str, str]` when `True`. Normalize to str keys + bytes values so
    downstream code does not need to branch on client configuration.
    """
    out: dict[str, bytes] = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
        if isinstance(v, (bytes, bytearray)):
            out[key] = bytes(v)
        elif isinstance(v, str):
            out[key] = v.encode()
        else:
            out[key] = str(v).encode()
    return out


def _coerce_id(value: object) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return str(value)


class StreamProducer:
    """Append entries to a Redis Stream with XADD.

    Mirrors `Stream.Add` from the Go side. Uses `*` as the entry ID so Redis
    auto-generates monotonically increasing IDs.
    """

    def __init__(self, client: "aioredis.Redis", stream: str) -> None:
        self._r = client
        self._stream = stream

    async def add(self, fields: Mapping[str, FieldValue]) -> str:
        """XADD `fields` to the stream and return the generated entry ID."""
        result = await self._r.xadd(self._stream, dict(fields))  # type: ignore[arg-type]
        return _coerce_id(result)


class StreamConsumer:
    """Consume entries from a Redis Stream via a consumer group.

    Mirrors `Stream.ReadGroup`, `Stream.Ack`, and `Stream.ClaimStale` from
    the Go side. `block_ms` controls the XREADGROUP blocking duration in
    milliseconds (0 = non-blocking). `count` caps the batch size per read.

    Call `ensure_group()` once before reading; it issues
    `XGROUP CREATE MKSTREAM` and swallows `BUSYGROUP` errors, matching the
    Go `New()` behavior.
    """

    def __init__(
        self,
        client: "aioredis.Redis",
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 100,
    ) -> None:
        self._r = client
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._block_ms = block_ms
        self._count = count

    async def ensure_group(self) -> None:
        """Create the consumer group (XGROUP CREATE MKSTREAM); ignore BUSYGROUP."""
        try:
            await self._r.xgroup_create(
                self._stream, self._group, id="0", mkstream=True
            )
        except Exception as exc:  # noqa: BLE001 — match Go's substring check
            if "BUSYGROUP" not in str(exc):
                raise

    async def read(self) -> list[StreamMessage]:
        """XREADGROUP from `>` and return new messages for this consumer.

        Returns an empty list when no messages arrive within `block_ms`.
        """
        resp = await self._r.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._count,
            block=self._block_ms,
        )
        return _flatten(resp)

    async def ack(self, msg_id: str) -> None:
        """XACK a message id in this stream/group."""
        await self._r.xack(self._stream, self._group, msg_id)

    async def claim_stale(self, idle_ms: int) -> list[StreamMessage]:
        """XAUTOCLAIM messages idle longer than `idle_ms` from any consumer.

        Reassigns ownership to this consumer and returns the claimed entries.
        """
        # redis-py xautoclaim returns (next_id, claimed_messages, deleted_ids)
        # for redis>=6.2. Some versions return (next_id, claimed_messages).
        result = await self._r.xautoclaim(
            name=self._stream,
            groupname=self._group,
            consumername=self._consumer,
            min_idle_time=idle_ms,
            start_id="0-0",
            count=self._count,
        )
        if not result:
            return []
        # result[1] is the list of (id, fields) tuples
        claimed = result[1] if len(result) >= 2 else []
        return [_message_from_pair(item) for item in claimed]


def _flatten(resp: Any) -> list[StreamMessage]:
    """Flatten the XREADGROUP response into a flat list of `StreamMessage`."""
    if not resp:
        return []
    out: list[StreamMessage] = []
    # resp is list[(stream_name, list[(id, fields)])]
    for _stream_name, entries in resp:
        for item in entries:
            out.append(_message_from_pair(item))
    return out


def _message_from_pair(item: Any) -> StreamMessage:
    msg_id, fields = item
    return StreamMessage(id=_coerce_id(msg_id), fields=_normalize_fields(fields))
