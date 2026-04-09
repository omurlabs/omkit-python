"""Fire-and-forget notifier for solid-sync Pod synchronization.

Usage:
    notifier = SyncNotifier(base_url="http://solid-sync:8000", token="...")
    await notifier.notify("medication", "med-001", {...data...})

Notifications are best-effort: failures are logged but never block the caller.
"""

import asyncio
import structlog
import httpx

log = structlog.get_logger()


class SyncNotifier:
    """Sends async sync notifications to solid-sync service."""

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def notify(self, resource_type: str, resource_id: str, data: dict) -> None:
        """Fire-and-forget sync notification. Never raises."""
        asyncio.create_task(self._send(resource_type, resource_id, data))

    async def notify_delete(self, resource_type: str, resource_id: str) -> None:
        """Fire-and-forget delete notification. Never raises."""
        asyncio.create_task(self._send_delete(resource_type, resource_id))

    async def notify_metrics(self, metric_name: str, date: str, rows: list[dict]) -> None:
        """Fire-and-forget metrics sync notification. Never raises."""
        asyncio.create_task(self._send_metrics(metric_name, date, rows))

    async def _send(self, resource_type: str, resource_id: str, data: dict) -> None:
        try:
            client = self._get_client()
            resp = await client.post(
                f"{self._base_url}/sync/{resource_type}/{resource_id}",
                json=data,
                headers={"X-Service-Token": self._token},
            )
            if resp.status_code == 202:
                log.debug("sync_notifier.queued", type=resource_type, id=resource_id)
            else:
                log.warning("sync_notifier.unexpected_status", type=resource_type,
                           id=resource_id, status=resp.status_code)
        except Exception as e:
            log.warning("sync_notifier.failed", type=resource_type,
                       id=resource_id, error=str(e))

    async def _send_delete(self, resource_type: str, resource_id: str) -> None:
        try:
            client = self._get_client()
            resp = await client.delete(
                f"{self._base_url}/sync/{resource_type}/{resource_id}",
                headers={"X-Service-Token": self._token},
            )
            if resp.status_code == 202:
                log.debug("sync_notifier.delete_queued", type=resource_type, id=resource_id)
            else:
                log.warning("sync_notifier.delete_unexpected_status", type=resource_type,
                           id=resource_id, status=resp.status_code)
        except Exception as e:
            log.warning("sync_notifier.delete_failed", type=resource_type,
                       id=resource_id, error=str(e))

    async def _send_metrics(self, metric_name: str, date: str, rows: list[dict]) -> None:
        try:
            client = self._get_client()
            resp = await client.post(
                f"{self._base_url}/sync/metrics",
                json={"metric_name": metric_name, "date": date, "rows": rows},
                headers={"X-Service-Token": self._token},
            )
            if resp.status_code == 202:
                log.debug("sync_notifier.metrics_queued", metric=metric_name, date=date)
            else:
                log.warning("sync_notifier.metrics_unexpected_status",
                           metric=metric_name, status=resp.status_code)
        except Exception as e:
            log.warning("sync_notifier.metrics_failed", metric=metric_name, error=str(e))

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
