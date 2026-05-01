"""packages/omur-sdk/tests/test_metrics.py — test_metrics module.

exports: test_mount_metrics_exposes_endpoint() | test_mount_metrics_idempotent()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omur_sdk.metrics import mount_metrics


def test_mount_metrics_exposes_endpoint():
    app = FastAPI()
    mount_metrics(app, "test-svc")

    @app.get("/foo")
    def foo():
        return {"ok": True}

    client = TestClient(app)
    client.get("/foo")
    r = client.get("/metrics")
    assert r.status_code == 200
    # Either standard HTTP metric name is acceptable — Instrumentator
    # emits "http_requests_total" or "starlette_requests_total" depending
    # on version; both indicate wiring succeeded.
    assert "http_requests_total" in r.text or "starlette_requests_total" in r.text


def test_mount_metrics_idempotent():
    app = FastAPI()
    mount_metrics(app, "svc")
    mount_metrics(app, "svc")  # second call must not raise
