"""Tests for shared health/ready endpoint helpers."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omur_sdk.health import mount_health_endpoints


def test_health_returns_ok():
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "test-svc"
    assert data["version"] == "1.0.0"


def test_ready_returns_ready_when_check_passes():
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
    async def check():
        return {"db": "connection refused"}

    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0", ready_check=check)
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_ready_returns_ready_without_check():
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
