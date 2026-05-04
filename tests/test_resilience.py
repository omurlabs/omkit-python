"""packages/omur-sdk/tests/test_resilience.py — test_resilience module.

exports: test_circuit_opens_after_fail_max() | test_open_circuit_raises_circuit_open_immediately() | test_success_resets_failure_count() | test_half_open_after_reset_timeout() | test_non_transient_errors_are_not_retried() | test_half_open_probe_success_closes_circuit()
rules:   The circuit breaker must maintain thread safety across all state transitions and timeout operations. All failure counting and reset timeout logic must be atomic to prevent race conditions during concurrent executions. The module must support configurable fail_max and reset_timeout parameters while ensuring consistent behavior across different timeout values.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import pytest
import httpx
from unittest.mock import MagicMock
from omur_sdk.resilience import CircuitBreaker, CircuitOpen, resilient


@pytest.mark.asyncio
async def test_circuit_opens_after_fail_max():
    """
    Rules:   Circuit breaker must be in 'closed' state before failures; after fail_max failures, it transitions to 'open' and stops allowing calls until reset.
    """
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
    """
    Rules:   Once a circuit is open, any call to a resilient function will immediately raise CircuitOpen without attempting the call.
    """
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
    """
    Rules:   A successful call in a circuit breaker resets the failure count and transitions the state to 'closed'.
    """
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
    """
    Rules:   If reset_timeout is 0, the circuit transitions to 'half_open' immediately after failing, allowing one probe call.
    """
    cb = CircuitBreaker(fail_max=1, reset_timeout=0, name="test")
    cb.record_failure()
    assert cb.state == "open"
    # reset_timeout=0 means immediately eligible to transition
    assert cb.state == "half_open"


@pytest.mark.asyncio
async def test_non_transient_errors_are_not_retried():
    """
    Rules:   Only HTTP errors with status codes 502, 503, or 504 are considered transient and retried; others are raised immediately without retrying.
    """
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
    """After timeout, a successful call in HALF_OPEN state closes the circuit.

    Rules:   In 'half_open' state, a successful call closes the circuit and resets failure count, transitioning back to 'closed'.
    """
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
