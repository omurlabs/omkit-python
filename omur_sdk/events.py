"""EventBus SDK primitive backed by Valkey (Redis) Streams."""

import json
import time

import structlog

log = structlog.get_logger()

STREAM_KEY_PREFIX = "omur:events"


class EventBus:
    """Lightweight event bus backed by Valkey (Redis) Streams."""

    def __init__(self, redis_client, service_name: str) -> None:
        self._redis = redis_client
        self._service_name = service_name

    def _stream_key(self, event_type: str) -> str:
        return f"{STREAM_KEY_PREFIX}:{event_type}"

    async def publish(self, event_type: str, data: dict) -> str:
        """Publish an event to the stream. Returns the message ID."""
        payload = {**data, "source": self._service_name, "timestamp": time.time()}
        stream_key = self._stream_key(event_type)
        msg_id = await self._redis.xadd(stream_key, {"payload": json.dumps(payload)})
        log.debug("eventbus.publish", event_type=event_type, stream=stream_key, msg_id=msg_id)
        return msg_id

    async def consume(
        self,
        event_type: str,
        last_id: str = "0-0",
        count: int = 10,
        block_ms: int | None = None,
    ) -> list[dict]:
        """Read events from the stream. Returns list of {msg_id, data} dicts."""
        stream_key = self._stream_key(event_type)
        results = await self._redis.xread({stream_key: last_id}, count=count, block=block_ms)
        if not results:
            return []

        items = []
        for _stream_name, messages in results:
            for msg_id, fields in messages:
                payload = fields.get("payload") or fields.get(b"payload")
                if payload is None:
                    continue
                if isinstance(payload, bytes):
                    payload = payload.decode()
                items.append({"msg_id": msg_id, "data": json.loads(payload)})

        return items

    async def ack(self, event_type: str, group: str, msg_id: str) -> None:
        """Acknowledge a message in a consumer group."""
        stream_key = self._stream_key(event_type)
        await self._redis.xack(stream_key, group, msg_id)
        log.debug("eventbus.ack", event_type=event_type, group=group, msg_id=msg_id)
