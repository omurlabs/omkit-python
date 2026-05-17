# omur-sdk changelog

## Unreleased

### Changed

- `omur_sdk.eventbus.PostgresEventBus.publish()` now stamps the nil-UUID
  sentinel (`NIL_TENANT_ID = "00000000-0000-0000-0000-000000000000"`) on
  system-level events instead of writing NULL `tenant_id`. Aligns the SDK
  with the RLS policy introduced in migration
  `0005_rls_with_check_and_events_sentinel` so admin-role readers can see
  system events without re-opening the cross-tenant leak the migration
  closed. Backfill of legacy NULL rows ships in migration
  `0006_events_backfill_nil_tenant`. (#549)

### Added

- `omur_sdk.eventbus.NIL_TENANT_ID` constant. Mirrored by `NilTenantID`
  in `packages/omur-go-sdk/eventbus/postgres.go`.

## [0.2.0] - 2026-04-17

Added pluggable backends so services can keep Valkey/Redis as an opt-in and
default to Postgres for everything cross-cutting (sessions, events,
settings-sync, provider sync).

### Added

- `omur_sdk.sessions` — `Session` dataclass, `SessionStore` Protocol,
  `PostgresSessionStore`, `RedisSessionStore`, `backend_from_env()`, `new_store()`.
  Backend selection via `OMUR_SESSION_BACKEND` (default `postgres`).
- `omur_sdk.eventbus` — `Event` dataclass, `EventBus` Protocol,
  `PostgresEventBus` (polling), `RedisEventBus` (Streams), `new_bus()`.
  Backend selection via `OMUR_EVENTBUS_BACKEND` (default `postgres`).
- `omur_sdk.dbpool.create_pool()` — wraps `asyncpg.create_pool` with an
  init-coroutine that runs `SET ROLE <role>` on every new connection
  (defence in depth for tenants after PgBouncer removal).

### Changed

- `omur_sdk.settings.SettingsManager` now accepts `pool=` and
  `poll_interval=` kwargs and selects between polling (default, via
  `OMUR_SETTINGS_BACKEND=postgres`) and Valkey subscriber
  (`OMUR_SETTINGS_BACKEND=redis`). Legacy
  `(service_name, db_session_factory, valkey_url, tenant_id, …)` signature
  still works unchanged.
- `omur_sdk.providers.registry.ProviderRegistry` now accepts
  `poll_interval=` and `backend=` kwargs; default polling backend
  re-runs `_reconcile_all()` every `poll_interval` seconds in place of the
  Valkey pub/sub subscriber. Backend also selectable via
  `OMUR_PROVIDERS_BACKEND`.

### Notes

No service changes shipped in this release. Services consume the new
abstractions in Plan 2.
