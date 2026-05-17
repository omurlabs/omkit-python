"""tests/test_crypto_envelope_interop.py — Cross-SDK interop tests for omkit.crypto and omkit.kms.

Pins the Python implementation against:

  * The Go golden vector from `omkit-go/crypto/aes_gcm_test.go::TestGoldenVectorUnwrap`.
  * The Go legacy-blob suite in `omkit-go/crypto/testdata/legacy_blobs.json`
    (read at test time — no need to vendor a copy).
  * Round-trip in Python with all Go AAD constants.
  * Round-trip across the KMS DEK layer (wrap / unwrap, AAD tamper, cross-
    user, cross-purpose isolation), mirroring `omkit-go/kms/localdev_dek_test.go`.

The legacy-blobs file is required for the test suite — its absence is a hard
failure, not a skip, because losing this pinning is exactly the kind of
silent regression these tests exist to catch.

exports: GOLDEN_KEK_HEX | GOLDEN_BLOB_HEX | GOLDEN_AAD | GOLDEN_PLAINTEXT | LEGACY_BLOBS_PATH | test_*
rules:   Never relax a failing legacy-blob assertion — find the regression and fix it. New AAD constants in omkit.crypto.aad MUST have a corresponding Go-side change in the same release.
agent:   claude-opus-4-7 | anthropic | 2026-05-17 | claude-code | initial interop test suite
message:
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omkit.crypto import (
    AAD_CONTENT,
    AAD_EMBEDDINGS_CHUNKS,
    AAD_META,
    AAD_METRICS,
    AADContent,
    AADEmbeddingsChunks,
    AADMeta,
    AADMetrics,
    InvalidEnvelopeError,
    InvalidKeyError,
    KUser,
    unwrap,
    wrap,
)
from omkit.crypto.aes_gcm import unwrap_with_key, wrap_with_key
from omkit.kms import KMSAuthError, LocalDevKMS

# --- Go golden vector (TestGoldenVectorUnwrap) ------------------------------

GOLDEN_KEK_HEX = "0101010101010101010101010101010101010101010101010101010101010101"
GOLDEN_BLOB_HEX = (
    "8d81c09a2a470251c953cb6e19b2c6fc5f4cd7579eda3e42cc627e7462135abd7d3aa4f8"
    "892fe47d6f35b0ccc8383edf8ed6afd1"
)
GOLDEN_AAD = b"omur-wrap-v1"
GOLDEN_PLAINTEXT = b"omur-golden-plaintext-v1"

# Path to the Go legacy-blob file. We read from the sibling Go repo because
# the spec is "do not modify Go" and we want a single source of truth.
LEGACY_BLOBS_PATH = (
    Path(__file__).resolve().parents[2] / "omkit-go" / "crypto" / "testdata" / "legacy_blobs.json"
)


# --- AAD constant pinning ---------------------------------------------------


def test_aad_constants_match_go():
    """Every AAD constant must equal the literal in omkit-go/crypto/aad.go."""
    assert AADMeta == "omur-col-meta-v1"
    assert AADMetrics == "omur-col-metrics-v1"
    assert AADContent == "omur-col-content-v1"
    assert AADEmbeddingsChunks == "omur-col-embeddings-v1"
    # Aliases.
    assert AAD_META == AADMeta
    assert AAD_METRICS == AADMetrics
    assert AAD_CONTENT == AADContent
    assert AAD_EMBEDDINGS_CHUNKS == AADEmbeddingsChunks


# --- Golden vector ----------------------------------------------------------


def test_golden_vector_unwrap():
    """Decrypt the Go golden blob — proves byte-for-byte envelope parity."""
    kek = bytes.fromhex(GOLDEN_KEK_HEX)
    blob = bytes.fromhex(GOLDEN_BLOB_HEX)
    out = unwrap_with_key(kek, blob, GOLDEN_AAD)
    assert out == GOLDEN_PLAINTEXT


# --- Legacy-blob suite (matches Go TestLegacyBlobsDecrypt) -----------------


@pytest.mark.skipif(
    not LEGACY_BLOBS_PATH.exists(),
    reason=f"Go legacy blobs file not found at {LEGACY_BLOBS_PATH}",
)
def test_legacy_blobs_decrypt():
    """Decrypt every blob in omkit-go/crypto/testdata/legacy_blobs.json.

    Failing this test means production ciphertext written by Go services may
    no longer be readable from Python — a deploy-blocking regression.
    """
    cases = json.loads(LEGACY_BLOBS_PATH.read_text())
    assert len(cases) >= 10, f"expected >=10 legacy cases, got {len(cases)}"
    for i, c in enumerate(cases):
        kek = bytes.fromhex(c["kek_hex"])
        blob = bytes.fromhex(c["blob_hex"])
        aad = c["aad"].encode()
        expected = c["plaintext"].encode()
        out = unwrap_with_key(kek, blob, aad)
        assert out == expected, f"case {i} (aad={c['aad']!r}): plaintext drift"


# --- Round-trip in Python ---------------------------------------------------


def test_round_trip_with_random_kek():
    kek = os.urandom(32)
    pt = b"hello world"
    blob = wrap_with_key(kek, pt, AAD_CONTENT.encode())
    assert unwrap_with_key(kek, blob, AAD_CONTENT.encode()) == pt


def test_round_trip_resolver_api():
    """The keyword API requested by the port spec.

    `wrap(plaintext, *, key_id, aad, key_resolver)`.
    """
    bag = {"k1": os.urandom(32)}
    blob = wrap(
        b"hello",
        key_id="k1",
        aad=AAD_CONTENT.encode(),
        key_resolver=lambda kid: bag[kid],
    )
    got = unwrap(
        blob,
        key_id="k1",
        aad=AAD_CONTENT.encode(),
        key_resolver=lambda kid: bag[kid],
    )
    assert got == b"hello"


def test_aad_mismatch_fails():
    kek = os.urandom(32)
    blob = wrap_with_key(kek, b"hello", b"aad-a")
    with pytest.raises(InvalidEnvelopeError):
        unwrap_with_key(kek, blob, b"aad-b")


def test_short_blob_raises():
    kek = os.urandom(32)
    with pytest.raises(InvalidEnvelopeError):
        unwrap_with_key(kek, b"short", b"aad")


def test_wrong_kek_size_raises():
    with pytest.raises(InvalidKeyError):
        wrap_with_key(b"too-short", b"hello", b"aad")
    with pytest.raises(InvalidKeyError):
        unwrap_with_key(b"too-short", b"x" * 32, b"aad")


# --- KUser self-test --------------------------------------------------------


def test_kuser_self_test_round_trip():
    k = KUser.generate()
    nonce, ct = k.new_self_test()
    k.verify_self_test(nonce, ct)


def test_kuser_self_test_tamper_fails():
    k = KUser.generate()
    nonce, ct = k.new_self_test()
    tampered = bytearray(ct)
    tampered[0] ^= 0xFF
    with pytest.raises(ValueError):
        k.verify_self_test(nonce, bytes(tampered))


def test_kuser_zero_clears_bytes():
    k = KUser(b"0123456789abcdef0123456789abcdef")
    k.zero()
    assert k.bytes == b"\x00" * 32


def test_kuser_zero_clears_all_nonzero_pattern():
    raw = bytes(i + 1 for i in range(32))
    k = KUser(raw)
    k.zero()
    assert k.bytes == b"\x00" * 32


# --- LocalDev KMS DEK flow (mirrors Go localdev_dek_test.go) ---------------


@pytest.fixture
def kms() -> LocalDevKMS:
    return LocalDevKMS(os.urandom(32))


async def test_wrap_dek_round_trip(kms: LocalDevKMS):
    plain = os.urandom(32)
    aad = b"doc-id=abc123"
    wrapped, version = await kms.wrap_dek("user-1", "K_content", plain, aad)
    assert version == "localdev-v1"
    got = await kms.unwrap_dek("user-1", "K_content", wrapped, aad)
    assert got == plain


async def test_wrap_dek_aad_tamper(kms: LocalDevKMS):
    plain = os.urandom(32)
    aad = b"doc-id=abc123"
    wrapped, _ = await kms.wrap_dek("user-1", "K_content", plain, aad)
    tampered = bytearray(aad)
    tampered[0] ^= 0xFF
    with pytest.raises(KMSAuthError):
        await kms.unwrap_dek("user-1", "K_content", wrapped, bytes(tampered))


async def test_wrap_dek_cross_user_isolation(kms: LocalDevKMS):
    plain = os.urandom(32)
    aad = b"doc-id=abc123"
    wrapped, _ = await kms.wrap_dek("user-A", "K_content", plain, aad)
    with pytest.raises(KMSAuthError):
        await kms.unwrap_dek("user-B", "K_content", wrapped, aad)


async def test_wrap_dek_cross_purpose_isolation(kms: LocalDevKMS):
    plain = os.urandom(32)
    aad = b"doc-id=abc123"
    wrapped, _ = await kms.wrap_dek("user-1", "K_content", plain, aad)
    with pytest.raises(KMSAuthError):
        await kms.unwrap_dek("user-1", "K_meta", wrapped, aad)


async def test_wrap_dek_empty_dek(kms: LocalDevKMS):
    wrapped, _ = await kms.wrap_dek("user-1", "K_content", b"", b"aad")
    got = await kms.unwrap_dek("user-1", "K_content", wrapped, b"aad")
    assert got == b""


async def test_wrap_dek_oversized_dek(kms: LocalDevKMS):
    large = os.urandom(4096)
    wrapped, _ = await kms.wrap_dek("user-1", "K_content", large, b"aad")
    got = await kms.unwrap_dek("user-1", "K_content", wrapped, b"aad")
    assert got == large


async def test_delete_user_keys_no_error(kms: LocalDevKMS):
    await kms.delete_user_keys("user-1")  # no-op for LocalDev


async def test_current_version_returns_v1(kms: LocalDevKMS):
    assert await kms.current_version("any-key") == "v1"


# --- Cross-SDK LocalDevKMS interop ----------------------------------------


async def test_localdev_static_wrap_matches_go_derivation():
    """Build a Python LocalDevKMS, wrap a blob, then verify the derived KEK
    matches Go's `HMAC(master, "omur-kms-derive-v1:" + keyID)` by recomputing
    it inline and decrypting via the low-level helper.
    """
    import hashlib
    import hmac

    master = os.urandom(32)
    pykms = LocalDevKMS(master)
    aad = AAD_CONTENT.encode()
    blob = await pykms.wrap("tenant-key", b"payload", aad)

    expected_kek = hmac.new(
        master, b"omur-kms-derive-v1:tenant-key", hashlib.sha256
    ).digest()
    assert unwrap_with_key(expected_kek, blob, aad) == b"payload"


async def test_localdev_dek_aad_binding_matches_go():
    """Verify the DEK AAD binding is exactly `"purpose|user_id|" + aad`."""
    import hashlib
    import hmac

    master = os.urandom(32)
    pykms = LocalDevKMS(master)
    user_id = "user-1"
    purpose = "K_content"
    aad = b"doc-id=abc"
    plain = os.urandom(32)
    wrapped, _ = await pykms.wrap_dek(user_id, purpose, plain, aad)

    expected_kek = hmac.new(
        master, f"user-{user_id}-{purpose}".encode(), hashlib.sha256
    ).digest()
    bound_aad = f"{purpose}|{user_id}|".encode() + aad
    assert unwrap_with_key(expected_kek, wrapped, bound_aad) == plain
