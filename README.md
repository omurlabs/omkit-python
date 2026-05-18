# omkit

[![ci](https://github.com/omurlabs/omkit-python/actions/workflows/ci.yml/badge.svg)](https://github.com/omurlabs/omkit-python/actions/workflows/ci.yml)
[![security](https://github.com/omurlabs/omkit-python/actions/workflows/security.yml/badge.svg)](https://github.com/omurlabs/omkit-python/actions/workflows/security.yml)
[![PyPI](https://img.shields.io/pypi/v/omkit.svg)](https://pypi.org/project/omkit/)
[![Python versions](https://img.shields.io/pypi/pyversions/omkit.svg)](https://pypi.org/project/omkit/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Multi-tenant SaaS scaffolding for Python services.

`omkit` is the Python side of Omur Labs' shared service toolkit. It bundles the
boring-but-load-bearing pieces every tenant-isolated service needs: a Postgres
pool that enforces Row-Level Security per connection, a pluggable event bus
(Postgres `LISTEN/NOTIFY` or Valkey), session and settings stores, an LLM
provider registry, BYOK encryption helpers, FastAPI observability middleware,
and a cross-runtime job-queue envelope that interoperates with the Go sibling.

- **Status:** `v0.2.0` — internal API stable.
- **Python:** `>=3.12`
- **License:** Apache-2.0
- **Sibling:** [`omkit-go`](https://github.com/omurlabs/omkit-go) — same primitives, same envelope contract, same RLS conventions.

## Install

```bash
pip install git+https://github.com/omurlabs/omkit-python@v0.2.0
```

Optional extras:

| Extra      | Adds                                                              | When you need it                       |
|------------|-------------------------------------------------------------------|----------------------------------------|
| `tracing`  | `opentelemetry-{api,sdk}`, OTLP/HTTP exporter, FastAPI + httpx instrumentation | Distributed tracing |
| `metrics`  | `prometheus-fastapi-instrumentator`                               | FastAPI request metrics                |
| `dev`      | `fastapi`, `pytest`, `pytest-asyncio`, `respx`                    | Local development and tests            |

```bash
pip install "omkit[tracing,metrics] @ git+https://github.com/omurlabs/omkit-python@v0.2.0"
```

## Quickstart

A minimal tenant-aware FastAPI service wired up with the pieces omkit gives you:

```python
from fastapi import FastAPI
from omkit.dbpool import create_pool
from omkit.tenant import TenantMiddleware
from omkit.transport import (
    configure_logging,
    init_tracing,
    instrument_fastapi,
    mount_metrics,
    mount_health_endpoints,
)

configure_logging()
init_tracing(service_name="my-service")

app = FastAPI()
app.add_middleware(TenantMiddleware)
instrument_fastapi(app)
mount_metrics(app)
mount_health_endpoints(app)

pool = await create_pool("postgresql://...")  # role-scoped, RLS-aware
```

Tenant context is set by `TenantMiddleware` and read by everything downstream
(pool, event bus, logger, HTTP client, job envelope) via `omkit.tenant`.

## Module index

### Data & storage

| Module                        | What it does                                                                 |
|-------------------------------|------------------------------------------------------------------------------|
| `omkit.dbpool`                | Asyncpg pool that sets a Postgres role per connection so RLS policies apply. |
| `omkit.sessions`              | `SessionStore` protocol with Postgres and Redis backends.                    |
| `omkit.encryption`            | AES-256-GCM settings encryption — `generate_key`, `encrypt_value`, `decrypt_value`, `mask_secret`. Wire-compatible with `omkit-go/encryption`. |
| `omkit.data` *(facade)*       | Re-exports pool + session primitives in one place.                           |

### Events & async

| Module           | What it does                                                                    |
|------------------|---------------------------------------------------------------------------------|
| `omkit.eventbus` | `EventBus` protocol (`PostgresEventBus`, `RedisEventBus`) with env-driven factory. |
| `omkit.valkey`   | Async Redis/Valkey client factory.                                              |
| `omkit.events`   | Deprecated shim — imports from here warn; use `omkit.eventbus`.                 |

### Job queue

| Module                    | What it does                                                                  |
|---------------------------|-------------------------------------------------------------------------------|
| `omkit.jobqueue`          | `Envelope` contract — `wrap`/`unwrap` for tenant-scoped tasks. Same wire format as `omkit-go/jobqueue`. |
| `omkit.jobqueue.streaq`   | streaq worker helpers (`make_worker`, `enqueue`, `mount_streaq_ui`, Prometheus collector). Import explicitly. |
| `omkit.model_lifecycle`   | `ModelRegistry` + `ModelLifecycle` ABC — lazy model loading with polling.     |
| `omkit.syncnotifier`      | `SyncNotifier` — enqueue outbound HTTP callbacks.                             |

### Observability & resilience

| Module                | What it does                                                              |
|-----------------------|---------------------------------------------------------------------------|
| `omkit.logging`       | `configure_logging()` — structlog + JSON formatter.                       |
| `omkit.metrics`       | `mount_metrics()` — Prometheus endpoint on a FastAPI app.                 |
| `omkit.tracing`       | `init_tracing()`, `instrument_fastapi()` — OpenTelemetry over OTLP/HTTP.  |
| `omkit.health`        | `mount_health_endpoints()` — `/health` + `/ready` routes.                 |
| `omkit.resilience`    | `CircuitBreaker`, `@resilient` decorator, `CircuitOpen` exception.        |
| `omkit.quota`         | `Resource`, `Limits`, `Usage`, `Decision`, `check_upload`, `check_query`. |
| `omkit.transport` *(facade)* | Re-exports the wire + observability set.                           |

### Multi-tenant & config

| Module               | What it does                                                              |
|----------------------|---------------------------------------------------------------------------|
| `omkit.tenant`       | Tenant context (`require`, `current_or_none`, `request_id`, `bind`) and ASGI/FastAPI middleware. |
| `omkit.config`       | `BaseServiceSettings` — pydantic-settings base class for env-driven config. |
| `omkit.settings`     | `SettingsManager` — async tenant-settings loader with polling.            |
| `omkit.platform` *(facade)* | Re-exports config + lifecycle + sync notifier.                     |

### LLM & security

| Module               | What it does                                                              |
|----------------------|---------------------------------------------------------------------------|
| `omkit.provider`     | `ProviderBase` ABC + `ProviderRegistry` for pluggable LLM providers.      |
| `omkit.sanitize`     | `sanitize_llm_output`, `sanitize_llm_response`, `sanitize_html`, `extract_json`. |
| `omkit.security` *(facade)* | Sanitation re-exports plus `log_security_event`.                   |
| `omkit.cost`         | `record_cost`, `COST_UNITS_TOTAL` Prometheus counter, `TenantBucket` enum. |
| `omkit.httpclient`   | `build_tenant_client()` — httpx `AsyncClient` that injects tenant headers. |
| `omkit.cleanup`      | `Loop` context manager — ensure event-loop cleanup on shutdown.           |

### Internal

`omkit.internal` holds private helpers (currently `crypto.py`). Not part of the
stable surface — do not import.

## Subpackage facades

Five subpackages re-export grouped primitives. Prefer importing from a facade
when you only need the "shape" of a concern; reach into a flat module when you
need a less common symbol.

| Facade            | Re-exports                                                                       |
|-------------------|----------------------------------------------------------------------------------|
| `omkit.data`      | Pool + session primitives                                                        |
| `omkit.platform`  | `BaseServiceSettings`, `SettingsManager`, `ModelLifecycle`, `ModelRegistry`, `SyncNotifier` |
| `omkit.security`  | Sanitation + `log_security_event` *(does **not** re-export `omkit.encryption`)*  |
| `omkit.transport` | `build_tenant_client`, `init_tracing`, `instrument_fastapi`, `mount_metrics`, `mount_health_endpoints`, `configure_logging`, `CircuitBreaker`, `resilient` |
| `omkit.jobqueue`  | `Envelope`, `wrap`, `unwrap`, `ENVELOPE_VERSION`, `InvalidEnvelopeError` *(streaq helpers via `omkit.jobqueue.streaq`)* |

## Cross-SDK job envelope

`omkit.jobqueue.Envelope` is the same wire contract used by
`omkit-go/jobqueue`. A Python streaq worker and a Go Asynq worker can publish
and consume each other's jobs as long as they agree on `ENVELOPE_VERSION` and
share the tenant routing rules. Pair it with a shared Valkey instance and
either runtime can pick up either runtime's work.

## Development

```bash
git clone git@github.com:omurlabs/omkit-python.git
cd omkit-python
pip install -e ".[dev,tracing,metrics]"

# Unit tests (no external services)
pytest

# Integration tests against a real Postgres
./scripts/test-with-postgres.sh
```

Test layout mirrors the module layout; every public module and facade has a
matching `tests/test_*.py`.
