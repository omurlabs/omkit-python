"""HTTP client for Cerebellum biomedical NLP service.

Features: circuit breaker, batch splitting, header forwarding, graceful fallback.
"""

from __future__ import annotations

import time
import structlog
from typing import Any

import httpx

log = structlog.get_logger()

_MAX_BATCH_SIZE = 32


class CerebellumClient:
    """Async HTTP client for the Cerebellum service with circuit breaker."""

    def __init__(
        self,
        base_url: str = "http://cerebellum:8006",
        timeout: float = 5.0,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        enabled: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled

        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        """Returns False when disabled or circuit is open."""
        if not self.enabled:
            return False
        if self._consecutive_failures < self.failure_threshold:
            return True
        # Circuit is open — check if cooldown has passed (half-open)
        if self._circuit_opened_at is not None:
            elapsed = time.monotonic() - self._circuit_opened_at
            if elapsed >= self.cooldown_seconds:
                return True  # half-open: allow a probe
        return False

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            if self._circuit_opened_at is None:
                self._circuit_opened_at = time.monotonic()
                log.warning("cerebellum.circuit_opened",
                            failures=self._consecutive_failures)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @staticmethod
    def _split_batch(items: list, max_size: int = _MAX_BATCH_SIZE) -> list[list]:
        return [items[i:i + max_size] for i in range(0, len(items), max_size)]

    async def _post(
        self,
        endpoint: str,
        payload: dict,
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> dict | None:
        """POST to Cerebellum. Returns None on failure (caller should fallback)."""
        if not self.available:
            return None

        headers = {}
        if request_id:
            headers["X-Request-ID"] = request_id
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        try:
            client = self._get_client()
            resp = await client.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 503:
                self._record_failure()
                return None
            resp.raise_for_status()
            self._record_success()
            return resp.json()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            self._record_failure()
            log.warning("cerebellum.request_failed", endpoint=endpoint, error=str(e))
            return None

    # --- Public API ---

    async def embed(
        self,
        texts: list[str],
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[list[float]] | None:
        """Get embeddings. Returns None on failure."""
        if not self.available:
            return None

        all_embeddings = []
        for batch in self._split_batch(texts):
            result = await self._post("/embed", {"texts": batch}, request_id, tenant_id)
            if result is None:
                return None
            all_embeddings.extend(result.get("embeddings", []))
        return all_embeddings

    async def ner(
        self,
        texts: list[str],
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict] | None:
        """Run NER. Returns None on failure."""
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/ner", {"texts": batch}, request_id, tenant_id)
            if result is None:
                return None
            all_results.extend(result.get("results", []))
        return all_results

    async def classify(
        self,
        texts: list[str],
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict] | None:
        """Classify texts. Returns None on failure."""
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/classify", {"texts": batch}, request_id, tenant_id)
            if result is None:
                return None
            all_results.extend(result.get("results", []))
        return all_results

    async def translate(
        self,
        texts: list[str],
        source_lang: str | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict] | None:
        """Translate texts to English. Returns None on failure."""
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            payload = {"texts": batch}
            if source_lang:
                payload["source_lang"] = source_lang
            result = await self._post("/translate", payload, request_id, tenant_id)
            if result is None:
                return None
            all_results.extend(result.get("translations", []))
        return all_results

    async def detect_language(
        self,
        texts: list[str],
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict] | None:
        """Detect language. Returns None on failure."""
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/detect-language", {"texts": batch}, request_id, tenant_id)
            if result is None:
                return None
            all_results.extend(result.get("results", []))
        return all_results

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
