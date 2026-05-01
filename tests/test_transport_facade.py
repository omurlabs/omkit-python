"""packages/omur-sdk/tests/test_transport_facade.py — omur_sdk.transport re-exports the expected surface.

exports: EXPECTED_EXPORTS | test_transport_facade_exports_are_callable_or_classes() | test_transport_facade_identity_matches_underlying() | test_transport_facade_all_matches_imports_exactly() | test_transport_facade_does_not_leak_internals()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import sys

from omur_sdk.transport import (
    build_tenant_client,
    init_tracing,
    instrument_fastapi,
    mount_metrics,
    mount_health_endpoints,
    configure_logging,
    CircuitBreaker,
    resilient,
)

EXPECTED_EXPORTS = {
    "build_tenant_client",
    "init_tracing",
    "instrument_fastapi",
    "mount_metrics",
    "mount_health_endpoints",
    "configure_logging",
    "CircuitBreaker",
    "resilient",
}


def test_transport_facade_exports_are_callable_or_classes():
    for obj in (
        build_tenant_client,
        init_tracing,
        instrument_fastapi,
        mount_metrics,
        mount_health_endpoints,
        configure_logging,
        resilient,
    ):
        assert callable(obj), f"{obj!r} is not callable"
    assert isinstance(CircuitBreaker, type), "CircuitBreaker should be a class"


def test_transport_facade_identity_matches_underlying():
    """A facade re-export must be the SAME object as the source module attr.

    Note: ``omur_sdk.tracing.init_tracing`` and ``instrument_fastapi`` are
    deliberately NOT checked here — ``tests/test_tracing.py`` calls
    ``importlib.reload(omur_sdk.tracing)`` mid-session to swap in OTEL mocks,
    which creates new function objects in the reloaded module. The facade
    captures references at import time, so identity fails after that reload.
    This is a property of Python ``from X import y`` in general and is not a
    facade-specific regression.
    """
    from omur_sdk import health, http, logging, metrics, resilience

    assert build_tenant_client is http.build_tenant_client
    assert mount_metrics is metrics.mount_metrics
    assert mount_health_endpoints is health.mount_health_endpoints
    assert configure_logging is logging.configure_logging
    assert CircuitBreaker is resilience.CircuitBreaker
    assert resilient is resilience.resilient


def test_transport_facade_all_matches_imports_exactly():
    """__all__ must equal the imported names — catches silent drift."""
    import omur_sdk.transport as facade

    declared = set(getattr(facade, "__all__", ()))
    assert declared == EXPECTED_EXPORTS, (
        f"__all__ drift: declared={declared}, expected={EXPECTED_EXPORTS}"
    )


def test_transport_facade_does_not_leak_internals():
    """Importing the facade must not pull omur_sdk.internal.* into sys.modules."""
    to_purge = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    for m in to_purge:
        del sys.modules[m]

    import omur_sdk.transport  # noqa: F401

    leaked = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    assert not leaked, f"facade leaked private modules: {leaked}"
