"""packages/omur-sdk/omur_sdk/valkey.py — Valkey client factory.

Single source of truth for `redis.asyncio.Redis` construction across the SDK.
Replaces the URL-construction duplication in `eventbus.new_bus()` and other
call sites. Reads BaseServiceSettings.valkey_url so password handling stays
consistent.

Note: streaq does not use this factory — streaq depends on `coredis`, a
different async Redis client. Services that use streaq construct the Worker
directly from `settings.valkey_url`.

exports: new_client(settings)
rules:   The module must maintain backward compatibility with existing Redis connection patterns while ensuring all async operations are properly awaited. The client initialization must respect the settings structure defined in the SDK's configuration schema. All Redis operations must be wrapped with appropriate timeout and retry logic to prevent service disruptions.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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

    Rules:   The function relies on settings.valkey_url being properly configured with a valid Redis connection string. It assumes that password handling and host/port logic are correctly implemented in the BaseServiceSettings, and that the VALKEY_PASSWORD environment variable is enforced at startup to prevent empty passwords.
    """
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.valkey_url, **kwargs)
