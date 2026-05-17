"""Tests for omkit.cost — Track 3 of cloud-readiness-prep."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from omkit.cost import COST_UNITS_TOTAL, record_cost


def _value(service: str, provider: str, op: str, tenant_bucket: str) -> float:
    return REGISTRY.get_sample_value(
        "cost_units_total",
        {"service": service, "provider": provider, "op": op, "tenant_bucket": tenant_bucket},
    ) or 0.0


def test_record_cost_increments_counter():
    before = _value("marrow", "voyage", "embed", "paid")
    record_cost(service="marrow", provider="voyage", op="embed", units=12, tenant_bucket="paid")
    assert _value("marrow", "voyage", "embed", "paid") == before + 12


def test_record_cost_normalises_unknown_bucket_to_trial():
    record_cost(service="marrow", provider="voyage", op="embed", units=1, tenant_bucket="enterprise")
    assert _value("marrow", "voyage", "embed", "trial") >= 1


def test_record_cost_skips_zero_and_negative_units():
    before = _value("auris", "deepgram", "stt_seconds", "system")
    record_cost(service="auris", provider="deepgram", op="stt_seconds", units=0, tenant_bucket="system")
    record_cost(service="auris", provider="deepgram", op="stt_seconds", units=-5, tenant_bucket="system")
    assert _value("auris", "deepgram", "stt_seconds", "system") == before


def test_record_cost_swallows_emission_errors(monkeypatch):
    class Boom:
        def labels(self, **_kw):
            class L:
                def inc(self, _n):
                    raise RuntimeError("registry blew up")
            return L()

    monkeypatch.setattr("omkit.cost.COST_UNITS_TOTAL", Boom())
    # Must not raise — best-effort emission.
    record_cost(service="x", provider="y", op="z", units=1, tenant_bucket="paid")


def test_counter_label_names_are_low_cardinality():
    # tenant_bucket is the cardinality firewall; raw tenant_id must NOT appear.
    assert "tenant_bucket" in COST_UNITS_TOTAL._labelnames
    assert "tenant_id" not in COST_UNITS_TOTAL._labelnames


@pytest.mark.parametrize("bucket", ["system", "trial", "paid"])
def test_each_documented_bucket_records(bucket: str):
    record_cost(service="cerebellum", provider="cohere", op="rerank", units=3, tenant_bucket=bucket)
    assert _value("cerebellum", "cohere", "rerank", bucket) >= 3
