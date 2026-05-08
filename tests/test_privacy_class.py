"""Tests for omur_sdk.privacy.privacy_class — Track 4 of cloud-readiness-prep."""

from __future__ import annotations

import pytest

from omur_sdk.privacy import (
    HEADER_NAME,
    PrivacyClass,
    allows_cloud,
    parse_privacy_class,
)


def test_header_name_is_canonical_case():
    assert HEADER_NAME == "X-Omur-Privacy-Class"


def test_default_is_tenant():
    assert PrivacyClass.default() is PrivacyClass.TENANT


def test_enum_values():
    assert PrivacyClass.PUBLIC.value == "public"
    assert PrivacyClass.TENANT.value == "tenant"
    assert PrivacyClass.SENSITIVE.value == "sensitive"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("public", PrivacyClass.PUBLIC),
        ("tenant", PrivacyClass.TENANT),
        ("sensitive", PrivacyClass.SENSITIVE),
        ("PUBLIC", PrivacyClass.PUBLIC),
        ("Sensitive", PrivacyClass.SENSITIVE),
        ("  tenant  ", PrivacyClass.TENANT),
    ],
)
def test_parse_recognises_known_values(raw, expected):
    assert parse_privacy_class(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "   ", "internal", "bogus", "p-u-b-l-i-c"])
def test_parse_falls_back_to_default(raw):
    assert parse_privacy_class(raw) is PrivacyClass.TENANT


def test_allows_cloud_only_blocks_sensitive():
    assert allows_cloud(PrivacyClass.PUBLIC) is True
    assert allows_cloud(PrivacyClass.TENANT) is True
    assert allows_cloud(PrivacyClass.SENSITIVE) is False


def test_string_inheritance_keeps_value_round_trip():
    # PrivacyClass(str, Enum) means JSON / log emission gets the literal value.
    assert PrivacyClass.SENSITIVE == "sensitive"
    assert str(PrivacyClass.PUBLIC.value) == "public"
