"""packages/omur-sdk/tests/test_resilience.py — test_resilience module.

exports: test_circuit_opens_after_fail_max() | test_open_circuit_raises_circuit_open_immediately() | test_success_resets_failure_count() | test_half_open_after_reset_timeout() | test_non_transient_errors_are_not_retried() | test_half_open_probe_success_closes_circuit()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import pytest
import httpx
from unittest.mock import MagicMock
from omur_sdk.resilience import CircuitBreaker, CircuitOpen, resilient


@pytest.mark.asyncio
async def test_circuit_opens_after_fail_max():
    cb = CircuitBreaker(fail_max=3, reset_timeout=60, name="test")
    calls = 0

    @resilient(cb)
    async def failing():
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused")

    for _ in range(3):
        try:
            await failing()
        except (httpx.ConnectError, CircuitOpen):
            pass

    assert cb.state == "open"


@pytest.mark.asyncio
async def test_open_circuit_raises_circuit_open_immediately():
    cb = CircuitBreaker(fail_max=1, reset_timeout=60, name="test")
    cb.record_failure()
    assert cb.state == "open"

    @resilient(cb)
    async def ok():
        return "should not be called"

    with pytest.raises(CircuitOpen):
        await ok()


@pytest.mark.asyncio
async def test_success_resets_failure_count():
    cb = CircuitBreaker(fail_max=5, name="test")
    cb._failures = 3

    @resilient(cb)
    async def ok():
        return 42

    result = await ok()
    assert result == 42
    assert cb._failures == 0
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_half_open_after_reset_timeout():
    cb = CircuitBreaker(fail_max=1, reset_timeout=0, name="test")
    cb.record_failure()
    assert cb.state == "open"
    # reset_timeout=0 means immediately eligible to transition
    assert cb.state == "half_open"


@pytest.mark.asyncio
async def test_non_transient_errors_are_not_retried():
    cb = CircuitBreaker(fail_max=10, name="test")
    calls = 0

    @resilient(cb)
    async def bad_request():
        nonlocal calls
        calls += 1
        mock_response = MagicMock()
        mock_response.status_code = 400
        raise httpx.HTTPStatusError("bad", request=MagicMock(), response=mock_response)

    # httpx.HTTPStatusError without response.status_code in {502,503,504} is non-transient
    with pytest.raises(httpx.HTTPStatusError):
        await bad_request()

    assert calls == 1  # no retry


@pytest.mark.asyncio
async def test_half_open_probe_success_closes_circuit():
    """After timeout, a successful call in HALF_OPEN state closes the circuit."""
    cb = CircuitBreaker(fail_max=1, reset_timeout=0, name="test")
    cb.record_failure()
    # Force to half_open by reading state twice (reset_timeout=0)
    _ = cb.state  # first read: open, sets _open_observed
    assert cb.state == "half_open"

    @resilient(cb)
    async def ok():
        return "success"

    result = await ok()
    assert result == "success"
    assert cb.state == "closed"
    assert cb._failures == 0
