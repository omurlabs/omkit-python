"""omkit/kms/openbao.py — OpenBao / Vault Transit KMS adapter (port of omkit-go/kms/openbao.go).

Wire-compatible with the Go adapter. Uses `httpx.AsyncClient` for HTTP and
follows the same:

  * AppRole login at `/v1/auth/approle/login` with `{role_id, secret_id}` →
    `data.auth.client_token`. Token cached in memory and refreshed when
    expiry is within 30 s.
  * Encrypt / decrypt at `/v1/transit/{encrypt,decrypt}/<keyName>` with
    `{plaintext|ciphertext, context}` (both base64 except `ciphertext` which
    is the Transit `vault:vN:...` string).
  * Static-key flow uses caller's `aad` as the Transit context.
  * Derived-key flow encodes the context as
    `base64(user_id + ":" + purpose + ":" + base64(aad))`. Matches Go's
    `derivedContext`.
  * `current_version` reads `data.latest_version` from
    `/v1/transit/keys/<keyName>`.
  * `delete_user_keys` writes a tombstone to
    `/v1/secret/data/omur/shredded/<user_id>` (kv-v2). Transit derived-mode
    cannot revoke per-context keys; this is the best-effort signal Go uses.

Status codes:
  * >= 500 / network error → `KMSUnavailableError`.
  * >= 400               → `KMSAuthError`.
  * On 403 from an authenticated call, the token is dropped and the request
    is retried once after a fresh login.

Env vars (read by `OpenBaoKMS.from_env`):
  * `OMUR_KMS_OPENBAO_ADDR`       (required)
  * `OMUR_KMS_OPENBAO_ROLE_ID`    (required)
  * `OMUR_KMS_OPENBAO_SECRET_ID`  (required)
  * `OMUR_KMS_OPENBAO_KEY_NAME`   (default: `omur-user-content`)

exports: OpenBaoKMS
rules:   HTTP path layout, request/response shape, and derivedContext encoding must remain identical to omkit-go/kms/openbao.go. The X-Vault-Token header must be set on every authenticated call. Never log the token or AppRole secret_id.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial port from omkit-go/kms
message:
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, Final

import httpx

from omkit.kms.base import KMSAuthError, KMSUnavailableError

_DEFAULT_KEY_NAME: Final[str] = "omur-user-content"
_DEFAULT_TIMEOUT_S: Final[float] = 10.0
_TOKEN_REFRESH_WINDOW_S: Final[float] = 30.0
_MAX_RESP_BYTES: Final[int] = 64 * 1024


def _truncate(b: bytes | str, n: int = 200) -> str:
    s = b.decode("utf-8", errors="replace") if isinstance(b, (bytes, bytearray)) else b
    return s if len(s) <= n else s[:n]


def _derived_context(user_id: str, purpose: str, aad: bytes) -> str:
    """Build the Transit context. Matches Go `derivedContext`.

    `base64(user_id + ":" + purpose + ":" + base64(aad))`.
    """
    inner = f"{user_id}:{purpose}:{base64.b64encode(aad).decode('ascii')}".encode()
    return base64.b64encode(inner).decode("ascii")


class OpenBaoKMS:
    """OpenBao / Vault Transit adapter. Async I/O via `httpx.AsyncClient`."""

    __slots__ = (
        "_addr",
        "_role_id",
        "_secret_id",
        "_key_name",
        "_client",
        "_owns_client",
        "_token",
        "_token_expiry",
        "_token_lock",
    )

    def __init__(
        self,
        addr: str,
        role_id: str,
        secret_id: str,
        *,
        key_name: str = _DEFAULT_KEY_NAME,
        client: httpx.AsyncClient | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        if not addr:
            raise ValueError("OpenBaoKMS: addr is required")
        if not role_id:
            raise ValueError("OpenBaoKMS: role_id is required")
        if not secret_id:
            raise ValueError("OpenBaoKMS: secret_id is required")
        self._addr = addr.rstrip("/")
        self._role_id = role_id
        self._secret_id = secret_id
        self._key_name = key_name or _DEFAULT_KEY_NAME
        if client is None:
            self._client = httpx.AsyncClient(timeout=timeout)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._token_lock = asyncio.Lock()

    @classmethod
    def from_env(cls, *, client: httpx.AsyncClient | None = None) -> "OpenBaoKMS":
        """Construct from `OMUR_KMS_OPENBAO_*` env vars (matches Go `NewOpenBaoKMS`)."""
        addr = os.environ.get("OMUR_KMS_OPENBAO_ADDR")
        if not addr:
            raise RuntimeError("openbao kms: OMUR_KMS_OPENBAO_ADDR must be set")
        role_id = os.environ.get("OMUR_KMS_OPENBAO_ROLE_ID")
        if not role_id:
            raise RuntimeError("openbao kms: OMUR_KMS_OPENBAO_ROLE_ID must be set")
        secret_id = os.environ.get("OMUR_KMS_OPENBAO_SECRET_ID")
        if not secret_id:
            raise RuntimeError("openbao kms: OMUR_KMS_OPENBAO_SECRET_ID must be set")
        key_name = os.environ.get("OMUR_KMS_OPENBAO_KEY_NAME") or _DEFAULT_KEY_NAME
        return cls(addr, role_id, secret_id, key_name=key_name, client=client)

    async def aclose(self) -> None:
        """Close the underlying HTTP client (only if we own it)."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "OpenBaoKMS":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    # --- token management ---------------------------------------------------

    async def _get_token(self) -> str:
        async with self._token_lock:
            if self._token and (self._token_expiry - time.monotonic()) > _TOKEN_REFRESH_WINDOW_S:
                return self._token
            return await self._login_locked()

    async def _login_locked(self) -> str:
        body = {"role_id": self._role_id, "secret_id": self._secret_id}
        resp = await self._do_raw("POST", "/v1/auth/approle/login", token=None, json_body=body)
        try:
            auth = resp.get("auth") or {}
            client_token = auth.get("client_token") or ""
            lease = int(auth.get("lease_duration") or 0)
        except (AttributeError, TypeError) as exc:
            raise KMSUnavailableError(
                f"unexpected login response: {_truncate(str(resp))}", status=0
            ) from exc
        if not client_token:
            raise KMSUnavailableError(
                f"unexpected login response: {_truncate(str(resp))}", status=0
            )
        if lease <= 0:
            lease = 3600
        self._token = client_token
        self._token_expiry = time.monotonic() + lease
        return self._token

    # --- HTTP helpers -------------------------------------------------------

    async def _do_raw(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Single HTTP round-trip. Returns parsed JSON. Maps status codes to KMS errors."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Vault-Token"] = token
        url = self._addr + path
        try:
            resp = await self._client.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise KMSUnavailableError(str(exc), status=0) from exc

        # Cap response size in line with Go's `io.LimitReader(64KiB)`.
        body = resp.content[:_MAX_RESP_BYTES]
        if resp.status_code >= 500:
            raise KMSUnavailableError(_truncate(body), status=resp.status_code)
        if resp.status_code >= 400:
            raise KMSAuthError(_truncate(body), status=resp.status_code)
        if not body:
            return {}
        try:
            import json

            return json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise KMSUnavailableError(
                f"invalid JSON response: {_truncate(body)}", status=resp.status_code
            ) from exc

    async def _do(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Authenticated round-trip. Refreshes the token on 403."""
        tok = await self._get_token()
        try:
            return await self._do_raw(method, path, token=tok, json_body=json_body)
        except KMSAuthError as exc:
            if exc.status == 403:
                async with self._token_lock:
                    self._token = None
                tok2 = await self._get_token()
                return await self._do_raw(method, path, token=tok2, json_body=json_body)
            raise

    # --- KMS protocol -------------------------------------------------------

    async def wrap(self, key_id: str, plaintext: bytes, aad: bytes) -> bytes:
        body = {
            "plaintext": base64.b64encode(plaintext).decode("ascii"),
            "context": base64.b64encode(aad).decode("ascii"),
        }
        resp = await self._do("POST", f"/v1/transit/encrypt/{key_id}", json_body=body)
        ct = ((resp.get("data") or {}).get("ciphertext")) or ""
        if not ct:
            raise KMSUnavailableError("unexpected encrypt response", status=0)
        return ct.encode("ascii")

    async def unwrap(self, key_id: str, blob: bytes, aad: bytes) -> bytes:
        body = {
            "ciphertext": blob.decode("ascii") if isinstance(blob, (bytes, bytearray)) else blob,
            "context": base64.b64encode(aad).decode("ascii"),
        }
        resp = await self._do("POST", f"/v1/transit/decrypt/{key_id}", json_body=body)
        pt_b64 = ((resp.get("data") or {}).get("plaintext")) or ""
        if not pt_b64:
            raise KMSUnavailableError("unexpected decrypt response", status=0)
        try:
            return base64.b64decode(pt_b64)
        except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
            raise KMSUnavailableError(f"base64 decode plaintext: {exc}", status=0) from exc

    async def current_version(self, key_id: str) -> str:
        resp = await self._do("GET", f"/v1/transit/keys/{key_id}")
        latest = ((resp.get("data") or {}).get("latest_version"))
        if not isinstance(latest, int):
            raise KMSUnavailableError("unexpected keys response", status=0)
        return f"v{latest}"

    async def wrap_dek(
        self,
        user_id: str,
        purpose: str,
        plain_dek: bytes,
        aad: bytes,
    ) -> tuple[bytes, str]:
        ctx64 = _derived_context(user_id, purpose, aad)
        body = {
            "plaintext": base64.b64encode(plain_dek).decode("ascii"),
            "context": ctx64,
        }
        resp = await self._do("POST", f"/v1/transit/encrypt/{self._key_name}", json_body=body)
        data = resp.get("data") or {}
        ct = data.get("ciphertext") or ""
        kv = data.get("key_version")
        if not ct or not isinstance(kv, int):
            raise KMSUnavailableError("unexpected wrap dek response", status=0)
        return ct.encode("ascii"), f"v{kv}"

    async def unwrap_dek(
        self,
        user_id: str,
        purpose: str,
        wrapped: bytes,
        aad: bytes,
    ) -> bytes:
        ctx64 = _derived_context(user_id, purpose, aad)
        body = {
            "ciphertext": wrapped.decode("ascii") if isinstance(wrapped, (bytes, bytearray)) else wrapped,
            "context": ctx64,
        }
        resp = await self._do("POST", f"/v1/transit/decrypt/{self._key_name}", json_body=body)
        pt_b64 = ((resp.get("data") or {}).get("plaintext")) or ""
        if not pt_b64:
            raise KMSUnavailableError("unexpected unwrap dek response", status=0)
        try:
            return base64.b64decode(pt_b64)
        except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
            raise KMSUnavailableError(f"base64 decode dek: {exc}", status=0) from exc

    async def delete_user_keys(self, user_id: str) -> None:
        """Best-effort crypto-shred tombstone. See module docstring for limits."""
        from datetime import datetime, timezone

        body = {
            "data": {
                "shredded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reason": "user_erasure_request",
            }
        }
        await self._do("POST", f"/v1/secret/data/omur/shredded/{user_id}", json_body=body)


__all__ = ["OpenBaoKMS"]
