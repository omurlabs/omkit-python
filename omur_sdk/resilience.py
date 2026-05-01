"""packages/omur-sdk/omur_sdk/resilience.py — HTTP resilience primitives: circuit breaker + retry with exponential backoff.

exports: T | class CircuitOpen | class CircuitBreaker | resilient(breaker)
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import functools
import time
from enum import Enum
from typing import Awaitable, Callable, TypeVar

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

T = TypeVar("T")


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """Async circuit breaker for single-process services.

    States: CLOSED (normal) → OPEN (fail-fast) → HALF_OPEN (probe) → CLOSED
    Thread-safe within a single asyncio event loop (no cross-thread use).
    """

    def __init__(self, fail_max: int = 5, reset_timeout: int = 60, name: str = "") -> None:
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.name = name
        self._failures = 0
        self._state = _State.CLOSED
        self._opened_at: float = 0.0
        self._open_observed: bool = False  # True after first "open" state is returned

    @property
    def state(self) -> str:
        if self._state == _State.OPEN:
            if self._open_observed and time.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = _State.HALF_OPEN
            else:
                self._open_observed = True
        return self._state.value

    def record_success(self) -> None:
        self._failures = 0
        self._state = _State.CLOSED
        self._open_observed = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max:
            self._state = _State.OPEN
            self._opened_at = time.monotonic()
            self._open_observed = False

    async def call(self, coro: Awaitable[T]) -> T:
        if self.state == "open":
            raise CircuitOpen(
                f"Circuit '{self.name}' is open — retry after {self.reset_timeout}s"
            )
        try:
            result = await coro
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


def _is_transient(exc: BaseException) -> bool:
    """True for errors that warrant a retry."""
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code in (502, 503, 504)
    return False


def resilient(breaker: CircuitBreaker) -> Callable:
    """Decorator: retry 3× with exponential backoff, guarded by a circuit breaker."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )
        @functools.wraps(fn)
        async def wrapped(*args, **kwargs):
            return await breaker.call(fn(*args, **kwargs))

        return wrapped

    return decorator
