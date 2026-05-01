"""packages/omur-sdk/tests/test_health.py — Tests for shared health/ready endpoint helpers.

exports: test_health_returns_ok() | test_healthz_alias_matches_health() | test_ready_returns_ready_when_check_passes() | test_ready_returns_503_when_check_fails() | test_ready_returns_ready_without_check()
used_by: none
rules:   The module must maintain backward compatibility with existing health and ready endpoints while ensuring all async check functions are properly awaited. The test suite must validate both success and failure states for readiness checks. All test cases should operate independently without shared mutable state between tests.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omur_sdk.health import mount_health_endpoints


def test_health_returns_ok():
    """
    Rules:   The health endpoint must return a 200 status code and JSON response with specific keys: 'status', 'service', and 'version'. Future developers must know that the service name and version are passed to the mount_health_endpoints function and must match the expected response structure.
    """
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "test-svc"
    assert data["version"] == "1.0.0"


def test_healthz_alias_matches_health():
    """
    Rules:   The /healthz endpoint is an alias for /health and must return identical JSON structure and status code. Developers must understand that both endpoints should behave identically for health checking purposes.
    """
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "test-svc", "version": "1.0.0"}


def test_ready_returns_ready_when_check_passes():
    """
    Rules:   The ready endpoint returns 200 status when the provided async check function returns a dictionary of successful checks. Developers must know that the check function must be async and return a dictionary format for the checks to be properly parsed.
    """
    async def check():
        return {"db": "ok"}

    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0", ready_check=check)
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["db"] == "ok"


def test_ready_returns_503_when_check_fails():
    """
    Rules:   The ready endpoint returns 503 status when the check function fails or returns an error. Developers must understand that the check function's return value determines readiness status, and non-successful responses will result in 503 status code.
    """
    async def check():
        return {"db": "connection refused"}

    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0", ready_check=check)
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_ready_returns_ready_without_check():
    """
    Rules:   When no ready_check is provided, the ready endpoint defaults to returning 200 status with 'ready' status. Developers must know that this behavior is automatic when no custom check is passed to mount_health_endpoints.
    """
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
