"""packages/omur-sdk/omur_sdk/valkey.py — Valkey client factory.

Single source of truth for `redis.asyncio.Redis` construction across the SDK.
Replaces the URL-construction duplication in `eventbus.new_bus()` and other
call sites. Reads BaseServiceSettings.valkey_url so password handling stays
consistent.

Note: streaq does not use this factory — streaq depends on `coredis`, a
different async Redis client. Services that use streaq construct the Worker
directly from `settings.valkey_url`.

exports: new_client(settings)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from omur_sdk.config import BaseServiceSettings


def new_client(
    settings: "BaseServiceSettings", **kwargs: Any
) -> "aioredis.Redis":
    """Build a redis.asyncio.Redis client from BaseServiceSettings.

    Reuses settings.valkey_url to keep password handling and host/port logic
    in one place. Empty password falls back to no-auth URL — fail-fast on
    empty password is enforced at compose-startup via the
    `${VALKEY_PASSWORD:?VALKEY_PASSWORD required}` interpolation, not here.

    Extra kwargs pass through to redis.asyncio.from_url (decode_responses,
    socket_timeout, etc.).
    """
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.valkey_url, **kwargs)
