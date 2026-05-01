"""packages/omur-sdk/tests/test_metrics.py — test_metrics module.

exports: test_mount_metrics_exposes_endpoint() | test_mount_metrics_idempotent()
used_by: none
rules:   The module must maintain backward compatibility with existing FastAPI application integrations and cannot introduce breaking changes to the metrics endpoint exposure pattern. The test suite must remain fully self-contained without external dependencies and should not modify global application state during test execution. All metrics endpoint tests must validate against the standard FastAPI testing client interface and cannot rely on custom middleware or external service mocks.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omur_sdk.metrics import mount_metrics


def test_mount_metrics_exposes_endpoint():
    """
    Rules:   The test verifies that metrics are exposed via the /metrics endpoint, but does not validate the specific metric name format or version-specific behavior of the Instrumentator library, which future developers must understand to maintain compatibility.
    """
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
    """
    Rules:   Calling mount_metrics multiple times with the same service name must not raise an exception, indicating the function should handle duplicate calls gracefully.
    """
    app = FastAPI()
    mount_metrics(app, "svc")
    mount_metrics(app, "svc")  # second call must not raise
