import asyncio
import os

import asyncpg
import pytest

from omur_sdk.providers.base import ProviderBase
from omur_sdk.providers.registry import ProviderRegistry


class NoopProvider(ProviderBase):
    """Collects tenant+config in a class var so tests can observe start."""

    kind = "polling-test"
    name = "noop"
    instances: list = []

    def __init__(self, tenant_id: str, config: dict) -> None:
        super().__init__(tenant_id=tenant_id, config=config)
        NoopProvider.instances.append((tenant_id, config))

    async def run(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise


@pytest.fixture
async def pool():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN not set")
    p = await asyncpg.create_pool(dsn)
    yield p
    await p.close()


@pytest.mark.asyncio
async def test_registry_polling_picks_up_providers(pool, monkeypatch):
    monkeypatch.setenv("OMUR_PROVIDERS_BACKEND", "postgres")
    NoopProvider.instances.clear()

    tenant_id = "00000000-0000-0000-0000-0000000000cc"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tenants (id, name) VALUES ($1, 'polling-test') "
            "ON CONFLICT (id) DO NOTHING",
            tenant_id,
        )
        await conn.execute(
            "DELETE FROM providers WHERE tenant_id = $1 AND kind = 'polling-test'",
            tenant_id,
        )

    dsn = os.getenv("TEST_POSTGRES_DSN")
    registry = ProviderRegistry(
        kind="polling-test",
        provider_classes={"noop": NoopProvider},
        postgres_dsn=dsn,
        valkey_url="",
        poll_interval=0.1,
    )
    await registry.start()

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO providers (tenant_id, kind, name, enabled, config) "
                "VALUES ($1, 'polling-test', 'noop', true, '{}'::jsonb)",
                tenant_id,
            )
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline:
            if NoopProvider.instances:
                return
            await asyncio.sleep(0.05)
        assert NoopProvider.instances, "polling did not pick up provider"
    finally:
        await registry.stop()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM providers WHERE tenant_id = $1 AND kind = 'polling-test'",
                tenant_id,
            )
            await conn.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
