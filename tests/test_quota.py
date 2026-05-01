"""packages/omur-sdk/tests/test_quota.py — test_quota module.

exports: test_check_upload_rejects_over_docs() | test_check_upload_rejects_over_bytes() | test_check_upload_allows_when_under() | test_check_query_rejects_at_limit() | test_check_query_allows_when_under() | test_cap_at_32_days() | test_defaults_match_stage1_spec()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

from omur_sdk.quota import (
    DEFAULT_DOCS,
    DEFAULT_QUERIES_PER_MONTH,
    DEFAULT_STORAGE_BYTES,
    Decision,
    Limits,
    Resource,
    Usage,
    check_query,
    check_upload,
)


def test_check_upload_rejects_over_docs():
    lim = Limits(docs=10, storage_bytes=1 << 30, queries_per_month=1000)
    usage = Usage(docs=10, storage_bytes=0, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=1)
    assert not d.allowed
    assert d.resource is Resource.DOCS


def test_check_upload_rejects_over_bytes():
    lim = Limits(docs=100, storage_bytes=1000, queries_per_month=1000)
    usage = Usage(docs=0, storage_bytes=500, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=600)
    assert not d.allowed
    assert d.resource is Resource.STORAGE_BYTES


def test_check_upload_allows_when_under():
    lim = Limits(docs=100, storage_bytes=1000, queries_per_month=1000)
    usage = Usage(docs=0, storage_bytes=500, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=499)
    assert d.allowed


def test_check_query_rejects_at_limit():
    lim = Limits(docs=100, storage_bytes=1 << 30, queries_per_month=5)
    usage = Usage(docs=0, storage_bytes=0, queries_this_month=5)
    d = check_query(lim, usage)
    assert not d.allowed
    assert d.resource is Resource.QUERIES_PER_MONTH
    assert d.retry_after > 0


def test_check_query_allows_when_under():
    lim = Limits(docs=100, storage_bytes=1 << 30, queries_per_month=5)
    usage = Usage(docs=0, storage_bytes=0, queries_this_month=4)
    d = check_query(lim, usage)
    assert d.allowed


from omur_sdk.quota import _cap_at_32_days  # type: ignore[attr-defined]


def test_cap_at_32_days():
    cases = [
        (-5, 60),
        (0, 0),
        (1000, 1000),
        (32 * 24 * 3600, 32 * 24 * 3600),
        (99 * 24 * 3600, 32 * 24 * 3600),
    ]
    for given, want in cases:
        assert _cap_at_32_days(given) == want, f"cap({given}) = {_cap_at_32_days(given)}, want {want}"


def test_defaults_match_stage1_spec():
    assert DEFAULT_DOCS == 100
    assert DEFAULT_STORAGE_BYTES == 500 * 1024 * 1024
    assert DEFAULT_QUERIES_PER_MONTH == 1000
