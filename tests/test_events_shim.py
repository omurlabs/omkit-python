"""tests/test_events_shim.py — omkit.events is a DeprecationWarning shim for omkit.eventbus.

exports: test_events_reexports_eventbus() | test_events_emits_deprecation_warning_on_import()
rules:   The module must maintain backward compatibility with existing eventbus reexports while ensuring all imports properly handle deprecation warnings. Any changes to the events shim must preserve the exact public API surface and import behavior. The test suite must continue to validate both the reexport functionality and deprecation warning emission on import.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import warnings


def test_events_reexports_eventbus():
    """
    Rules:   The test assumes that the events module directly re-exports the EventBus class from the eventbus module, meaning any changes to the import structure or aliasing in the events module will break this test. Future developers must understand the module's re-export behavior and maintain compatibility.
    """
    from omkit import events, eventbus

    assert events.EventBus is eventbus.EventBus


def test_events_emits_deprecation_warning_on_import():
    """
    Rules:   Future developers must know that importing omkit.events triggers a DeprecationWarning, and that the warning is specifically tested for in this function to ensure backward compatibility is maintained during the deprecation period.
    """
    import importlib
    import omkit.events as _preload  # noqa: F401

    # Reimport fresh to ensure the warning fires
    import sys

    if "omkit.events" in sys.modules:
        del sys.modules["omkit.events"]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import omkit.events  # noqa: F401

        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert dep_warnings, "expected DeprecationWarning on omkit.events import"
        assert "omkit.eventbus" in str(dep_warnings[0].message)
