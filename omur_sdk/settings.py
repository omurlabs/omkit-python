"""packages/omur-sdk/omur_sdk/settings.py — Settings manager with in-memory cache, Valkey pub/sub subscriber, and callbacks.

exports: class SettingsManager
used_by: none
rules:   The SettingsManager must maintain thread-safe cache access and ensure all database and Redis operations are properly synchronized to prevent race conditions during concurrent updates.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
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


def _backend_from_env() -> str:
    v = os.getenv("OMUR_SETTINGS_BACKEND", "postgres")
    if v not in {"postgres", "redis"}:
        raise ValueError(f"unknown OMUR_SETTINGS_BACKEND: {v}")
    return v


class SettingsManager:
    """Drop-in settings manager for services.

    Loads all settings from DB on start and then keeps the in-memory cache
    fresh via either a Postgres polling task (default) or a Valkey pub/sub
    subscriber (opt-in via ``OMUR_SETTINGS_BACKEND=redis``).

    Backward-compatible construction keeps accepting the legacy
    ``(service_name, db_session_factory, valkey_url, tenant_id, ...)`` signature.
    New callers can pass an asyncpg ``pool`` with ``poll_interval`` to use the
    polling backend without a SQLAlchemy session factory.
    """

    def __init__(
        self,
        service_name: str = "omur",
        db_session_factory=None,
        valkey_url: str = "",
        tenant_id: str = "",
        encryption_key: str = "",
        *,
        pool=None,
        poll_interval: float = 5.0,
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
        self._pool = pool
        self._poll_interval = poll_interval
        self._poll_last_seen = None
        self._poll_task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None

    @classmethod
    def create(
        cls,
        service_name: str,
        db_session_factory,
        settings,
    ) -> "SettingsManager":
        """Factory that reads valkey_url, tenant_id, encryption_key from a BaseServiceSettings instance.

        Rules:   The `service_name` must be a valid string that uniquely identifies the service; `db_session_factory` must be a callable that returns a valid database session; `settings` must have a `valkey_url` attribute, and optionally an `omur_settings_key` for encryption.
        """
        return cls(
            service_name=service_name,
            db_session_factory=db_session_factory,
            valkey_url=settings.valkey_url,
            tenant_id="",
            encryption_key=getattr(settings, "omur_settings_key", ""),
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Read from in-memory cache. No I/O.

        Rules:   The function only retrieves values from an in-memory cache; it does not handle missing keys gracefully if the default is not provided, and assumes the cache has already been populated.
        """
        return self._cache.get(key, default)

    async def get_secret(self, key: str) -> str | None:
        """Decrypt and return a secret value. Reads from DB, not cache.

        Rules:   The function assumes that the database table `app_settings` exists with columns `value_json`, `is_secret`, and `key`; the `decrypt_value` function must be defined and properly handle decryption of the stored values.
        """
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
        """Register a callback for when a specific setting changes.

        Rules:   Callbacks registered via `on_change` are expected to be synchronous and should not block or raise exceptions, as they are invoked directly during setting updates.
        """
        self._listeners.setdefault(key, []).append(callback)

    async def start(self):
        """Load all settings from DB into cache, validate, and start the

        Rules:   The `start` method requires that either `_pool` is set (for asyncpg) or `_valkey_url` is provided (for Redis); if neither is present, it defaults to a PostgreSQL-based polling mechanism.
        configured live-update worker."""
        if self._stop is None:
            self._stop = asyncio.Event()
        if self._pool is not None:
            # Asyncpg pool path — use polling by default.
            await self._load_from_pool()
        else:
            await self._load_from_db()
        self._validate()

        backend = _backend_from_env() if self._pool is not None else ("redis" if self._valkey_url else "postgres")
        if backend == "redis" and self._valkey_url:
            self._subscriber_task = asyncio.create_task(self._subscribe())
        elif self._pool is not None:
            self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "[%s] SettingsManager started, backend=%s, %d settings cached",
            self._service_name, backend, len(self._cache),
        )

    def _validate(self):
        """Log warnings for settings with invalid or empty values that may cause runtime errors."""
        for key, value in self._cache.items():
            if value is None:
                logger.warning("[%s] Setting '%s' is null", self._service_name, key)
            elif isinstance(value, str) and value.strip() == "" and "api_key" not in key and "token" not in key:
                logger.warning("[%s] Setting '%s' is empty", self._service_name, key)
            elif isinstance(value, str):
                # Check for common misconfigurations: JSON strings that should be parsed
                stripped = value.strip()
                if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
                    try:
                        json.loads(stripped)
                    except json.JSONDecodeError:
                        logger.warning("[%s] Setting '%s' looks like invalid JSON", self._service_name, key)

    async def stop(self):
        """Stop any background live-update workers.

        Rules:   Calling `stop` without a prior call to `start` will result in no-op behavior, but it's important to ensure that `start` was called and that background tasks were initialized before attempting to stop them.
        """
        if self._stop is None:
            # start() was never called; nothing to stop.
            return
        self._stop.set()
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _load_from_pool(self):
        """Load all non-secret settings via the asyncpg pool."""
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT key, value_json, is_secret, updated_at FROM app_settings"
                )
                latest = self._poll_last_seen
                for r in rows:
                    if latest is None or r["updated_at"] > latest:
                        latest = r["updated_at"]
                    if r["is_secret"]:
                        self._secret_keys.add(r["key"])
                        continue
                    value = r["value_json"]
                    if isinstance(value, (bytes, bytearray)):
                        value = value.decode()
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                    self._cache[r["key"]] = value
                if latest is not None:
                    self._poll_last_seen = latest
        except Exception as e:
            logger.warning("[%s] pool load failed: %s", self._service_name, e)

    async def _poll_loop(self):
        """Background task: re-fetch rows with updated_at > last_seen."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                return
            await self._poll_once()

    async def _poll_once(self):
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT key, value_json, is_secret, updated_at FROM app_settings "
                    "WHERE updated_at > $1 ORDER BY updated_at ASC",
                    self._poll_last_seen,
                )
            latest = self._poll_last_seen
            for r in rows:
                if latest is None or r["updated_at"] > latest:
                    latest = r["updated_at"]
                if r["is_secret"]:
                    continue
                value = r["value_json"]
                if isinstance(value, (bytes, bytearray)):
                    value = value.decode()
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                self._cache[r["key"]] = value
                for callback in self._listeners.get(r["key"], []):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(value)
                        else:
                            callback(value)
                    except Exception as e:
                        logger.error("Settings callback error for %s: %s", r["key"], e)
            if latest is not None:
                self._poll_last_seen = latest
        except Exception as e:
            logger.warning("[%s] poll failed: %s", self._service_name, e)

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
