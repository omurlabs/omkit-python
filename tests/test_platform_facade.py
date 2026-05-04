"""packages/omur-sdk/tests/test_platform_facade.py — omur_sdk.platform re-exports platform primitives.

exports: EXPECTED_EXPORTS | test_platform_facade_identity_matches_underlying() | test_platform_facade_types() | test_platform_facade_all_matches_imports_exactly() | test_platform_facade_does_not_leak_internals()
used_by: none
rules:   The platform facade must maintain exact identity and type compatibility with the underlying platform implementation to ensure transparent substitution. All public interfaces must be fully exported through the facade without internal module leakage. The facade cannot alter or obscure the fundamental behavior of the underlying platform components.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import sys

from omur_sdk.platform import (
    BaseServiceSettings,
    SettingsManager,
    ModelLifecycle,
    ModelRegistry,
    CerebellumClient,
    CortexClient,
    SyncNotifier,
)

EXPECTED_EXPORTS = {
    "BaseServiceSettings",
    "SettingsManager",
    "ModelLifecycle",
    "ModelRegistry",
    "CerebellumClient",
    "CortexClient",
    "SyncNotifier",
}


def test_platform_facade_identity_matches_underlying():
    """
    Rules:   Future developers must know that this test verifies identity assertions between facade classes and their underlying implementations, ensuring no accidental reassignment or import mismatches occur in the platform facade.
    """
    from omur_sdk import (
        cerebellum_client,
        config,
        cortex,
        model_lifecycle,
        settings,
        sync_notifier,
    )

    assert BaseServiceSettings is config.BaseServiceSettings
    assert SettingsManager is settings.SettingsManager
    assert ModelLifecycle is model_lifecycle.ModelLifecycle
    assert ModelRegistry is model_lifecycle.ModelRegistry
    assert CerebellumClient is cerebellum_client.CerebellumClient
    assert CortexClient is cortex.CortexClient
    assert SyncNotifier is sync_notifier.SyncNotifier


def test_platform_facade_types():
    """
    Rules:   Future developers must know that this test ensures all facade classes are actual Python classes (not instances or other types) to maintain proper type safety and expected behavior in the platform facade.
    """
    for cls in (
        BaseServiceSettings,
        SettingsManager,
        ModelLifecycle,
        ModelRegistry,
        CerebellumClient,
        CortexClient,
        SyncNotifier,
    ):
        assert isinstance(cls, type), f"{cls!r} should be a class"


def test_platform_facade_all_matches_imports_exactly():
    """
    Rules:   The test assumes a constant EXPECTED_EXPORTS is defined globally, which future developers must know to maintain consistency.
    """
    import omur_sdk.platform as facade

    declared = set(getattr(facade, "__all__", ()))
    assert declared == EXPECTED_EXPORTS, (
        f"__all__ drift: declared={declared}, expected={EXPECTED_EXPORTS}"
    )


def test_platform_facade_does_not_leak_internals():
    """
    Rules:   The test manipulates sys.modules directly, a non-obvious operation that requires understanding of Python's module system and potential side effects.
    """
    to_purge = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    for m in to_purge:
        del sys.modules[m]

    import omur_sdk.platform  # noqa: F401

    leaked = [m for m in sys.modules if m.startswith("omur_sdk.internal")]
    assert not leaked, f"facade leaked private modules: {leaked}"
