"""packages/omur-sdk/omur_sdk/cerebellum_client.py — HTTP client for Cerebellum biomedical NLP service.

Features: circuit breaker, batch splitting, header forwarding, graceful fallback.

exports: _MAX_BATCH_SIZE | class CerebellumClient
used_by: none
rules:   The `CerebellumClient` must maintain thread safety across all asynchronous operations and ensure the circuit breaker logic is consistently applied to all external HTTP calls to prevent cascading failures.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
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
        timeout: float = 60.0,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        enabled: bool = True,
        service_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled
        self._service_token = service_token

        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        """Returns False when disabled or circuit is open.

        Rules:   The circuit breaker logic allows a probe request after cooldown seconds have passed, but only if failure threshold has been reached. Future developers must understand this half-open state behavior.
        """
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

        # Resolve tenant_id: explicit arg wins, else pick up from the SDK
        # tenant contextvar (populated by TenantMiddleware or tenant.bind).
        # Cerebellum's own TenantMiddleware returns 401 without X-Tenant-ID.
        if tenant_id is None:
            try:
                from omur_sdk.tenant import current_or_none
                tenant_id = current_or_none()
            except Exception:
                tenant_id = None

        headers: dict[str, str] = {}
        if request_id:
            headers["X-Request-ID"] = request_id
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if self._service_token:
            headers["X-Service-Token"] = self._service_token

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
            log.warning("cerebellum.request_failed", endpoint=endpoint, error=repr(e))
            return None

    # --- Public API ---

    async def embed(
        self,
        texts: list[str],
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[list[float]] | None:
        """Get embeddings. Returns None on failure.

        Rules:   Function returns None on failure and relies on batch splitting; developers should know that individual batch failures lead to complete failure return.
        """
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
        """Run NER. Returns None on failure.

        Rules:   Function returns None on failure and uses batch processing; developers must understand that any single batch failure results in a complete None return.
        """
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/ner", {"texts": batch}, request_id, tenant_id)
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
        split_strategy: str | None = None,
        skip_strategy: str | None = None,
        batch_size: int = 1,
    ) -> list[dict] | None:
        """Translate texts to English. Returns None on failure.

        Rules:   Function returns None on failure and supports batch splitting; developers must understand that translation failures at any batch level result in a full None return.
        """
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            payload = {"texts": batch}
            if source_lang:
                payload["source_lang"] = source_lang
            if split_strategy:
                payload["split_strategy"] = split_strategy
            if skip_strategy:
                payload["skip_strategy"] = skip_strategy
            if batch_size > 1:
                payload["batch_size"] = batch_size
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
        """Detect language. Returns None on failure.

        Rules:   Function returns None on failure and uses batch processing; developers must understand that any single batch failure results in a complete None return.
        """
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/detect-language", {"texts": batch}, request_id, tenant_id)
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
        """Classify documents. Returns None on failure.

        Rules:   Function returns None on failure and uses batch processing; developers must understand that any single batch failure results in a complete None return.
        """
        if not self.available:
            return None

        all_results = []
        for batch in self._split_batch(texts):
            result = await self._post("/classify", {"texts": batch}, request_id, tenant_id)
            if result is None:
                return None
            all_results.extend(result.get("results", []))
        return all_results

    async def rerank(
        self,
        query: str,
        passages: list[str],
        top_k: int = 5,
        request_id: str | None = None,
        tenant_id: str | None = None,
    ) -> dict | None:
        """Re-rank passages for a query using cerebellum's cross-encoder.

        Returns the full response dict ``{"results": [...], "model": "..."}``
        or ``None`` on failure (timeout, 5xx, circuit open). Frontal's
        fallback path relies on ``None`` to mean "use pre-rerank order";
        raising on failure would break that contract and force the RAG
        request to fail on reranker outage.

        Unlike embed/ner/etc. this endpoint is NOT split into batches —
        the cross-encoder scores each (query, passage) pair jointly and
        splitting the batch would change the score order (ties break
        within a batch but can shuffle across batches).

        Rules:   Function returns None on failure and must maintain backward compatibility with frontal's fallback logic that relies on None to mean 'use pre-rerank order'; raising exceptions would break this contract.
        """
        if not self.available:
            return None
        if not passages:
            return {"results": [], "model": ""}

        payload = {"query": query, "passages": passages, "top_k": top_k}
        return await self._post("/rerank", payload, request_id, tenant_id)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
