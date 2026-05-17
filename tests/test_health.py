"""packages/omur-sdk/tests/test_health.py — Tests for shared health/ready endpoint helpers.

exports: test_health_returns_ok | test_healthz_alias_matches_health | test_ready_returns_ready_when_check_passes | test_ready_returns_503_when_check_fails | test_ready_returns_ready_without_check | test_readyz_alias_matches_ready | test_liveness_ignores_failing_ready_check
rules:   The test suite must validate both liveness aliases (/health, /healthz) and readiness aliases (/ready, /readyz), and must enforce the invariant that liveness probes are unaffected by failing readiness checks. All test cases operate independently without shared mutable state.
agent:   claude-opus-4-7 | anthropic | 2026-05-03 | track-9-health-ready-audit | added /readyz coverage + liveness-vs-readiness independence
message:
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omkit.health import mount_health_endpoints


def test_health_returns_ok():
    """
    Rules:   The health endpoint must return a 200 status code with a JSON response containing 'status', 'service', and 'version' fields.
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
    Rules:   The `/healthz` alias must return identical response data to `/health` endpoint.
    """
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "test-svc", "version": "1.0.0"}


def test_ready_returns_ready_when_check_passes():
    """
    Rules:   The ready endpoint must return a 200 status code and a 'ready' status when the readiness check passes.
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
    Rules:   The ready endpoint must return a 503 status code with 'not_ready' status when the readiness check fails.
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
    Rules:   If no ready check is provided, the `/ready` endpoint should default to returning a 200 status code with 'ready' status.
    """
    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0")
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readyz_alias_matches_ready():
    """`/readyz` must behave identically to `/ready` (both pass and fail paths).

    Rules:   The `/readyz` alias must behave identically to `/ready` in both success and failure cases.
    """

    async def passing():
        return {"db": "ok"}

    async def failing():
        return {"db": "connection refused"}

    # Pass case
    app_ok = FastAPI()
    mount_health_endpoints(app_ok, "test-svc", "1.0.0", ready_check=passing)
    client_ok = TestClient(app_ok)
    resp_ready = client_ok.get("/ready")
    resp_readyz = client_ok.get("/readyz")
    assert resp_ready.status_code == resp_readyz.status_code == 200
    assert resp_ready.json() == resp_readyz.json()

    # Fail case
    app_fail = FastAPI()
    mount_health_endpoints(app_fail, "test-svc", "1.0.0", ready_check=failing)
    client_fail = TestClient(app_fail)
    resp_ready = client_fail.get("/ready")
    resp_readyz = client_fail.get("/readyz")
    assert resp_ready.status_code == resp_readyz.status_code == 503
    assert resp_ready.json() == resp_readyz.json()


def test_liveness_ignores_failing_ready_check():
    """Liveness must stay 200 even when readiness reports failure — the contract
    that lets orchestrators distinguish 'restart this pod' from 'don't route

    Rules:   The liveness endpoint must always return 200, regardless of readiness check results, to distinguish pod restarts from traffic routing issues.
    traffic to it yet'."""

    async def failing():
        return {"db": "down"}

    app = FastAPI()
    mount_health_endpoints(app, "test-svc", "1.0.0", ready_check=failing)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/readyz").status_code == 503
