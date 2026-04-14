# packages/omur-sdk/omur_sdk/settings.py
"""Settings manager with in-memory cache, Valkey pub/sub subscriber, and callbacks."""

import asyncio
import json
import logging
import os
from typing import Any, Callable

import redis.asyncio as aioredis

from omur_sdk.encryption import decrypt_value

logger = logging.getLogger(__name__)


class SettingsManager:
    """Drop-in settings manager for services.
    Loads all settings from DB on start, subscribes to Valkey for live updates."""

    def __init__(
        self,
        service_name: str,
        db_session_factory,
        valkey_url: str,
        tenant_id: str,
        encryption_key: str = "",
    ):
        self._service_name = service_name
        self._db_factory = db_session_factory
        self._valkey_url = valkey_url
        self._tenant_id = tenant_id
        self._encryption_key = encryption_key
        self._cache: dict[str, Any] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._subscriber_task: asyncio.Task | None = None
        self._cache_path = os.environ.get("SETTINGS_CACHE_PATH", "/tmp/settings-cache.json")
        self._secret_keys: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        """Read from in-memory cache. No I/O."""
        return self._cache.get(key, default)

    async def get_secret(self, key: str) -> str | None:
        """Decrypt and return a secret value. Reads from DB, not cache."""
        from sqlalchemy import text

        async with self._db_factory() as session:
            result = await session.execute(
                text("SELECT value_json, is_secret FROM app_settings WHERE key = :key"),
                {"key": key},
            )
            row = result.one_or_none()
            if not row or not row.is_secret:
                return None
            try:
                return decrypt_value(str(row.value_json), self._encryption_key)
            except Exception:
                logger.warning("Failed to decrypt secret %s", key)
                return None

    def on_change(self, key: str, callback: Callable):
        """Register a callback for when a specific setting changes."""
        self._listeners.setdefault(key, []).append(callback)

    async def start(self):
        """Load all settings from DB into cache and start Valkey subscriber."""
        await self._load_from_db()
        self._subscriber_task = asyncio.create_task(self._subscribe())
        logger.info("[%s] SettingsManager started, %d settings cached", self._service_name, len(self._cache))

    async def stop(self):
        """Stop the Valkey subscriber."""
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass

    def _write_cache(self):
        """Write non-secret settings to local cache file atomically."""
        try:
            secret_keys = getattr(self, "_secret_keys", set())
            data = {k: v for k, v in self._cache.items() if k not in secret_keys}
            tmp_path = self._cache_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._cache_path)
        except Exception as e:
            logger.warning("Failed to write settings cache: %s", e)

    def _read_cache(self):
        """Read settings from local cache file (fallback when DB unavailable)."""
        try:
            with open(self._cache_path) as f:
                self._cache.update(json.load(f))
            logger.info("[%s] Loaded %d settings from cache", self._service_name, len(self._cache))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Failed to read settings cache: %s", e)

    async def _load_from_db(self):
        """Load all non-secret settings into cache."""
        from sqlalchemy import text

        try:
            async with self._db_factory() as session:
                result = await session.execute(
                    text("SELECT key, value_json, is_secret FROM app_settings"),
                )
                for row in result.all():
                    if row.is_secret:
                        self._secret_keys.add(row.key)
                    else:
                        self._cache[row.key] = row.value_json
            self._write_cache()
        except Exception as e:
            logger.warning("[%s] DB load failed, trying cache: %s", self._service_name, e)
            self._read_cache()

    async def _subscribe(self):
        """Subscribe to Valkey pub/sub channel for setting changes."""
        channel = f"omur:settings:{self._tenant_id}"
        try:
            client = aioredis.from_url(self._valkey_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            logger.info("[%s] Subscribed to %s", self._service_name, channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    await self._handle_message(message["data"])
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("[%s] Valkey subscriber error: %s", self._service_name, e)
            await asyncio.sleep(5)
            self._subscriber_task = asyncio.create_task(self._subscribe())

    async def _handle_message(self, data: str):
        """Process a pub/sub message: update cache, fire callbacks."""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return

        key = payload.get("key")
        if not key:
            return

        if "value" in payload:
            self._cache[key] = payload["value"]
        elif payload.get("changed"):
            self._cache.pop(key, None)
        self._write_cache()

        for callback in self._listeners.get(key, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(payload.get("value"))
                else:
                    callback(payload.get("value"))
            except Exception as e:
                logger.error("Settings callback error for %s: %s", key, e)
