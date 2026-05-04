"""packages/omur-sdk/omur_sdk/cortex.py — CortexClient for cortex OpenAI-compat API.

Replaces CerebellumClient at all prod call sites. Routes embed/classify/
translate/detect-language through cortex, which proxies to cloud providers
(Voyage for embed, Anthropic for text ops).

exports: CortexClient
used_by: services/marrow/core/*
rules:   Never call cerebellum. Raise on HTTP error — no silent None returns.
         All methods are coroutines; callers must await them.
"""
from __future__ import annotations

import json
import os

import httpx
import structlog

log = structlog.get_logger()

_DETECT_LANG_PROMPT = """\
Detect the language of the following text. Return ONLY a JSON object:
{{"language": "<BCP-47 code, e.g. en, ru, de, fr>"}}

TEXT:
{text}
"""

_NER_PROMPT = """\
Extract named medical entities from the following text.
Return ONLY a JSON object matching this schema:
{schema}

TEXT:
{text}
"""

_TRANSLATE_PROMPT = """\
Translate the following text to English. Return ONLY a JSON object:
{{"translated": "the full English translation"}}

Do not add explanations, notes, or commentary. Translate everything including \
headers, labels, units, and footnotes. Preserve the original structure \
(line breaks, bullet points).

TEXT:
{text}
"""

_CLASSIFY_PROMPT = """\
Classify the following text. Return ONLY a JSON object.
{schema_hint}

TEXT:
{text}
"""


class CortexClient:
    """Async HTTP client for cortex's OpenAI-compat port.

    All methods raise httpx.HTTPStatusError on non-2xx responses.
    Construct once per service startup; reuse the instance (httpx connection
    pool is kept alive).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("LLM_PROXY_URL", "http://cortex:4000")).rstrip("/")
        self._api_key = api_key or os.environ.get("LLM_PROXY_KEY", "")
        self._tenant_id = tenant_id
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _headers(self, tenant_id: str | None = None) -> dict[str, str]:
        tid = tenant_id or self._tenant_id
        if tid is None:
            try:
                from omur_sdk.tenant import current_or_none
                tid = current_or_none()
            except Exception:
                pass
        h: dict[str, str] = {}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        if tid:
            h["X-Tenant-ID"] = tid
        return h

    async def embed(self, text: str, tenant_id: str | None = None) -> list[float]:
        """Return a single embedding vector for *text*.

        Raises httpx.HTTPStatusError on failure.

        Rules:   The input text is limited to 3000 characters when passed to the LLM backend, although the function itself does not enforce this limit. Future developers should be aware that very long texts may be truncated by the backend.
        """
        client = self._get_client()
        resp = await client.post(
            f"{self._base_url}/v1/embeddings",
            json={"model": "embed", "input": [text]},
            headers=self._headers(tenant_id),
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]

    async def classify(self, text: str, schema: dict | None = None,
                       tenant_id: str | None = None) -> dict:
        """Classify *text*. Returns the parsed JSON dict from the LLM.

        *schema* is optional; when provided it is serialised and appended to
        the prompt so the model returns the expected fields.

        Rules:   The function uses a fixed prompt template (_CLASSIFY_PROMPT) and truncates input text to 3000 characters. Developers should know that large inputs may be silently truncated and that the schema hint is appended to the prompt, which could affect model behavior.
        """
        schema_hint = ""
        if schema:
            schema_hint = f"Use this JSON schema: {json.dumps(schema)}"
        prompt = _CLASSIFY_PROMPT.format(text=text[:3000], schema_hint=schema_hint)
        return await self._chat_json("classify", prompt, tenant_id)

    async def detect_language(self, text: str, tenant_id: str | None = None) -> str:
        """Return BCP-47 language code for *text* (e.g. 'en', 'ru').

        Rules:   The function truncates input text to 1000 characters. Developers should be aware that longer texts will be silently truncated, potentially affecting accuracy.
        """
        prompt = _DETECT_LANG_PROMPT.format(text=text[:1000])
        result = await self._chat_json("classify", prompt, tenant_id)
        lang = result.get("language", "")
        if not lang:
            log.warning("cortex_client.detect_language_empty", text_prefix=text[:50])
        return lang

    async def translate(self, text: str, target_lang: str = "en",
                        tenant_id: str | None = None) -> str:
        """Translate *text* to *target_lang* (default: English).

        Returns the translated string.

        Rules:   The function truncates input text to 8000 characters. Developers should know that very long texts may be truncated by the backend and that the target language must be a valid BCP-47 code.
        """
        prompt = _TRANSLATE_PROMPT.format(text=text[:8000])
        result = await self._chat_json("translate", prompt, tenant_id)
        return result.get("translated", "")

    async def ner(self, text: str, schema: dict | None = None,
                  tenant_id: str | None = None) -> dict:
        """Run NER on *text* using the classify cap with a structured prompt.

        Rules:   The function truncates input text to 3000 characters and uses a default schema if none is provided. Developers should be aware of the truncation limit and that the schema is used to constrain the output format, which may affect model performance if not properly defined.
        """
        default_schema = {
            "entities": [{"text": "string", "label": "string", "start": 0, "end": 0}]
        }
        effective_schema = schema or default_schema
        prompt = _NER_PROMPT.format(
            text=text[:3000],
            schema=json.dumps(effective_schema, ensure_ascii=False),
        )
        return await self._chat_json("classify", prompt, tenant_id)

    async def _chat_json(self, model: str, prompt: str,
                         tenant_id: str | None = None) -> dict:
        """Call POST /v1/chat/completions with *model* alias and return parsed JSON."""
        client = self._get_client()
        resp = await client.post(
            f"{self._base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            headers=self._headers(tenant_id),
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("cortex_client.json_parse_failed", model=model, raw=raw[:200])
            return {}

    async def close(self) -> None:
        """
        Rules:   Client must be properly initialized before calling close, otherwise it will raise AttributeError. The function only closes the client if it exists and is not already closed.
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
