# omur-sdk changelog

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
