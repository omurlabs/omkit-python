"""packages/omur-sdk/tests/test_events_shim.py — omur_sdk.events is a DeprecationWarning shim for omur_sdk.eventbus.

exports: test_events_reexports_eventbus() | test_events_emits_deprecation_warning_on_import()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

import warnings


def test_events_reexports_eventbus():
    from omur_sdk import events, eventbus

    assert events.EventBus is eventbus.EventBus


def test_events_emits_deprecation_warning_on_import():
    import importlib
    import omur_sdk.events as _preload  # noqa: F401

    # Reimport fresh to ensure the warning fires
    import sys

    if "omur_sdk.events" in sys.modules:
        del sys.modules["omur_sdk.events"]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import omur_sdk.events  # noqa: F401

        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert dep_warnings, "expected DeprecationWarning on omur_sdk.events import"
        assert "omur_sdk.eventbus" in str(dep_warnings[0].message)
