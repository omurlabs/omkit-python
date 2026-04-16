# omur-sdk (Python)

Shared infrastructure for Omur Python services — settings, logging, tracing,
Prometheus instrumentation, tenant middleware.

## Init order

Every Python service `main.py` must call SDK helpers in this order, **inside-
out** (each step depends on the prior):

```python
from omur_sdk.logging import configure_logging
from omur_sdk.tracing import init_tracing, instrument_fastapi
from omur_sdk.metrics import mount_metrics
from omur_sdk.tenant import TenantMiddleware
from fastapi import FastAPI

# 1. Logging — so subsequent steps log structured
configure_logging("my-service")

# 2. Tracing — sets the global tracer provider
init_tracing("my-service", version=settings.version)

# 3. Build the FastAPI app
app = FastAPI(title="my-service")

# 4. Instrument FastAPI for OTel — after app exists, before routes
instrument_fastapi(app)

# 5. Mount /metrics — uses Instrumentator with default exclusions
mount_metrics(app, "my-service")

# 6. TenantMiddleware LAST so it wraps outermost — tenant contextvars get
#    bound BEFORE the OTel span opens (FastAPI middleware runs in reverse
#    add order, so the last add becomes the outermost wrapper)
app.add_middleware(TenantMiddleware)
```

**Why TenantMiddleware last:** FastAPI middleware is LIFO — the last
`add_middleware` runs first on inbound requests. We want tenant contextvars
populated before any other middleware (especially before tracing) so that
spans and logs carry tenant labels.

## What `mount_metrics` excludes

`mount_metrics(app, "my-service")` mounts `/metrics` and configures
`Instrumentator` to skip `/metrics`, `/health`, `/healthz`, `/ready` so scrape
and probe traffic doesn't pollute `http_requests_total`. Matches the Go SDK's
`metrics.DefaultMetricsExclusions`.

If your service currently calls `Instrumentator().instrument(app).expose(app)`
directly, swap to `mount_metrics(app, "my-service")`.

## Settings

Use `BaseServiceSettings` (Pydantic v2) for env-var loading. Subclass it for
service-specific fields:

```python
from omur_sdk.config import BaseServiceSettings

class Settings(BaseServiceSettings):
    my_port: int = 8000
    my_queue: str = "valkey"

settings = Settings()
```

## Packages

| Module | Purpose |
|--------|---------|
| `omur_sdk.logging` | `configure_logging(service_name)` — structured logging setup |
| `omur_sdk.tracing` | `init_tracing(name, version)` — OTel SDK + OTLP exporter; `instrument_fastapi(app)` |
| `omur_sdk.metrics` | `mount_metrics(app, name)` — Prometheus `/metrics` with default exclusions |
| `omur_sdk.tenant` | `TenantMiddleware` + contextvar accessors |
| `omur_sdk.config` | `BaseServiceSettings` Pydantic base class |
