"""packages/omur-sdk/tests/test_base.py — test_base module.

exports: test_provider_document_required_fields() | test_provider_document_rejects_missing_content() | test_provider_document_optional_fields_default() | test_provider_metric_required_fields() | test_provider_metric_coerces_value_to_float() | test_provider_metric_rejects_non_numeric_value() | test_provider_base_cannot_be_instantiated_directly() | test_provider_base_concrete_subclass_must_implement_run() | test_provider_base_subclass_stores_tenant_and_config()
rules:   none
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
import pytest
from omur_sdk.providers.base import ProviderBase, ProviderDocument, ProviderMetric


# ── ProviderDocument ──────────────────────────────────────────────

def test_provider_document_required_fields():
    """
    Rules:   ProviderDocument requires 'content' field; other fields like 'source', 'source_id', and 'title' are also required for valid instantiation.
    """
    doc = ProviderDocument(source="gdrive", source_id="abc123", title="Lab result", content="glucose 5.4")
    assert doc.source == "gdrive"
    assert doc.source_id == "abc123"
    assert doc.meta == {}


def test_provider_document_rejects_missing_content():
    """
    Rules:   ProviderDocument cannot be instantiated without a 'content' field, as it's required for the document to be valid.
    """
    with pytest.raises(Exception):
        ProviderDocument(source="gdrive", source_id="abc123", title="Lab result")


def test_provider_document_optional_fields_default():
    """
    Rules:   Optional fields 'doc_type' and 'doc_date' default to None if not provided.
    """
    doc = ProviderDocument(source="local", source_id="f1", title="T", content="x")
    assert doc.doc_type is None
    assert doc.doc_date is None


# ── ProviderMetric ────────────────────────────────────────────────

def test_provider_metric_required_fields():
    """
    Rules:   ProviderMetric requires 'value' to be a numeric type; non-numeric values will cause instantiation to fail.
    """
    m = ProviderMetric(source="fitbit", metric="steps", value=8432.0, unit="steps", ts=1_700_000_000_000_000_000, tenant_id="t1")
    assert m.value == 8432.0
    assert m.meta == {}


def test_provider_metric_coerces_value_to_float():
    """
    Rules:   ProviderMetric automatically coerces string numeric values into float type during instantiation.
    """
    m = ProviderMetric(source="fitbit", metric="steps", value="8432", unit="steps", ts=1, tenant_id="t1")
    assert m.value == 8432.0


def test_provider_metric_rejects_non_numeric_value():
    """
    Rules:   ProviderMetric raises an exception if 'value' is not convertible to a numeric type.
    """
    with pytest.raises(Exception):
        ProviderMetric(source="fitbit", metric="steps", value="lots", unit="steps", ts=1, tenant_id="t1")


# ── ProviderBase ──────────────────────────────────────────────────

def test_provider_base_cannot_be_instantiated_directly():
    """
    Rules:   ProviderBase is an abstract base class and cannot be instantiated directly; it must be subclassed.
    """
    with pytest.raises(TypeError):
        ProviderBase(tenant_id="t1", config={})


def test_provider_base_concrete_subclass_must_implement_run():
    """
    Rules:   Concrete subclasses of ProviderBase must implement the 'run' method or instantiation will raise TypeError.
    """
    class BadProvider(ProviderBase):
        kind = "collector"
        name = "bad"
        # missing run()

    with pytest.raises(TypeError):
        BadProvider(tenant_id="t1", config={})


def test_provider_base_subclass_stores_tenant_and_config():
    """
    Rules:   ProviderBase subclasses store and preserve the provided 'tenant_id' and 'config' during instantiation.
    """
    class GoodProvider(ProviderBase):
        kind = "collector"
        name = "good"
        async def run(self): pass

    p = GoodProvider(tenant_id="alice", config={"api_key": "secret"})
    assert p.tenant_id == "alice"
    assert p.config["api_key"] == "secret"
