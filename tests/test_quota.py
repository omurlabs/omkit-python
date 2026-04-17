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


def test_defaults_match_stage1_spec():
    assert DEFAULT_DOCS == 100
    assert DEFAULT_STORAGE_BYTES == 500 * 1024 * 1024
    assert DEFAULT_QUERIES_PER_MONTH == 1000
