"""packages/omur-sdk/tests/test_quota.py — test_quota module.

exports: test_check_upload_rejects_over_docs() | test_check_upload_rejects_over_bytes() | test_check_upload_allows_when_under() | test_check_query_rejects_at_limit() | test_check_query_allows_when_under() | test_cap_at_32_days() | test_defaults_match_stage1_spec()
used_by: none
rules:   The module must maintain strict compliance with defined limits for docs, storage_bytes, and queries_per_month as specified in the Limits class, and all test cases must validate behavior against these exact constraints without deviation.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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
    """
    Rules:   Upload is rejected if the incoming document count would exceed the limit, even if storage and query limits are not exceeded.
    """
    lim = Limits(docs=10, storage_bytes=1 << 30, queries_per_month=1000)
    usage = Usage(docs=10, storage_bytes=0, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=1)
    assert not d.allowed
    assert d.resource is Resource.DOCS


def test_check_upload_rejects_over_bytes():
    """
    Rules:   Upload is rejected if the total storage bytes would exceed the limit after adding the incoming bytes.
    """
    lim = Limits(docs=100, storage_bytes=1000, queries_per_month=1000)
    usage = Usage(docs=0, storage_bytes=500, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=600)
    assert not d.allowed
    assert d.resource is Resource.STORAGE_BYTES


def test_check_upload_allows_when_under():
    """
    Rules:   Upload is allowed if the total storage bytes remain under the limit after adding the incoming bytes.
    """
    lim = Limits(docs=100, storage_bytes=1000, queries_per_month=1000)
    usage = Usage(docs=0, storage_bytes=500, queries_this_month=0)
    d = check_upload(lim, usage, incoming_bytes=499)
    assert d.allowed


def test_check_query_rejects_at_limit():
    """
    Rules:   Query is rejected if the monthly query count equals the limit, and retry_after is set to a positive value.
    """
    lim = Limits(docs=100, storage_bytes=1 << 30, queries_per_month=5)
    usage = Usage(docs=0, storage_bytes=0, queries_this_month=5)
    d = check_query(lim, usage)
    assert not d.allowed
    assert d.resource is Resource.QUERIES_PER_MONTH
    assert d.retry_after > 0


def test_check_query_allows_when_under():
    """
    Rules:   Query is allowed if the monthly query count is below the limit.
    """
    lim = Limits(docs=100, storage_bytes=1 << 30, queries_per_month=5)
    usage = Usage(docs=0, storage_bytes=0, queries_this_month=4)
    d = check_query(lim, usage)
    assert d.allowed


from omur_sdk.quota import _cap_at_32_days  # type: ignore[attr-defined]


def test_cap_at_32_days():
    """
    Rules:   The retry_after duration is capped at 32 days, regardless of input value.
    """
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
    """
    Rules:   DEFAULT_DOCS must equal 100, DEFAULT_STORAGE_BYTES must equal 500MB, and DEFAULT_QUERIES_PER_MONTH must equal 1000 to match the Stage 1 specification requirements.
    """
    assert DEFAULT_DOCS == 100
    assert DEFAULT_STORAGE_BYTES == 500 * 1024 * 1024
    assert DEFAULT_QUERIES_PER_MONTH == 1000
