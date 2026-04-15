"""Tests for tenant context module."""

import pytest
from uuid import uuid4

from omur_sdk import tenant


def test_require_raises_when_unset():
    """require() must raise RuntimeError outside tenant context."""
    with pytest.raises(RuntimeError, match="No tenant"):
        tenant.require()


def test_current_or_none_returns_none_when_unset():
    assert tenant.current_or_none() is None


def test_request_id_returns_none_when_unset():
    assert tenant.request_id() is None


def test_bind_sets_and_resets_tenant():
    tid = str(uuid4())
    assert tenant.current_or_none() is None
    with tenant.bind(tid):
        assert tenant.require() == tid
    assert tenant.current_or_none() is None


def test_bind_sets_and_resets_request_id():
    tid = str(uuid4())
    rid = str(uuid4())
    with tenant.bind(tid, request_id=rid):
        assert tenant.request_id() == rid
    assert tenant.request_id() is None


def test_bind_resets_on_exception():
    tid = str(uuid4())
    with pytest.raises(ValueError):
        with tenant.bind(tid):
            assert tenant.require() == tid
            raise ValueError("boom")
    assert tenant.current_or_none() is None
