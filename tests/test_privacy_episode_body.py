"""Tests for omur_sdk.privacy.episode_body — ADR-029 wire shape."""

from __future__ import annotations

import os

import pytest
from cryptography.exceptions import InvalidTag

from omur_sdk.privacy import (
    AADMismatchError,
    EncryptedBody,
    UnsupportedSchemaError,
    build_aad,
    decrypt_episode_body,
    encrypt_episode_body,
)
from omur_sdk.privacy.episode_body import SCHEMA_V1


class FakeKMS:
    """In-memory KMS stub.

    Wraps DEKs by XOR-ing against a per-(user, purpose) static key. AAD is
    bound by HMAC-style suffix so AAD mismatches surface at unwrap time —
    matching the production invariant without depending on real KMS infra.
    """

    def __init__(self) -> None:
        self.version = "v1"
        self._wrapping_keys: dict[tuple[str, str], bytes] = {}

    def _key_for(self, user_id: str, purpose: str) -> bytes:
        k = (user_id, purpose)
        if k not in self._wrapping_keys:
            self._wrapping_keys[k] = os.urandom(32)
        return self._wrapping_keys[k]

    def wrap_dek(self, *, user_id, purpose, plain_dek, aad):
        kek = self._key_for(user_id, purpose)
        wrapped = bytes(b ^ kek[i % len(kek)] for i, b in enumerate(plain_dek))
        return wrapped + b"|aad=" + aad, self.version

    def unwrap_dek(self, *, user_id, purpose, wrapped_dek, aad, version):
        if version != self.version:
            raise ValueError(f"unknown version: {version}")
        sep = b"|aad="
        if sep not in wrapped_dek:
            raise ValueError("malformed wrapped dek")
        wrapped, bound_aad = wrapped_dek.split(sep, 1)
        if bound_aad != aad:
            raise ValueError("aad mismatch at kms layer")
        kek = self._key_for(user_id, purpose)
        return bytes(b ^ kek[i % len(kek)] for i, b in enumerate(wrapped))


@pytest.fixture
def kms() -> FakeKMS:
    return FakeKMS()


@pytest.fixture
def ctx() -> dict[str, str]:
    return {
        "tenant_id": "tenant-alice",
        "episode_id": "ep-2026-05-08-001",
        "schema_label": "lab_result",
    }


class TestBuildAAD:
    def test_literal_format(self) -> None:
        aad = build_aad(episode_id="ep1", tenant_id="t1", schema_label="lab_result")
        assert aad == "omur:gnokee:episode:ep1:t1:lab_result"

    def test_rejects_colon_in_parts(self) -> None:
        with pytest.raises(ValueError):
            build_aad(episode_id="ep:1", tenant_id="t1", schema_label="lab_result")
        with pytest.raises(ValueError):
            build_aad(episode_id="ep1", tenant_id="t:1", schema_label="lab_result")
        with pytest.raises(ValueError):
            build_aad(episode_id="ep1", tenant_id="t1", schema_label="lab:result")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            build_aad(episode_id="", tenant_id="t1", schema_label="lab_result")


class TestRoundTrip:
    def test_round_trip_plaintext_recovered(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        plaintext = b"specimen note: hemolysed"
        envelope = encrypt_episode_body(plaintext, kms=kms, **ctx)
        recovered = decrypt_episode_body(envelope, kms=kms, **ctx)
        assert recovered == plaintext

    def test_envelope_to_dict_round_trip(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        envelope = encrypt_episode_body(b"x", kms=kms, **ctx)
        again = EncryptedBody.from_dict(envelope.to_dict())
        assert again == envelope

    def test_envelope_shape(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        assert env.schema == SCHEMA_V1
        assert env.alg == "AES-256-GCM"
        assert env.key_id.endswith(":v1")
        assert env.aad == "omur:gnokee:episode:ep-2026-05-08-001:tenant-alice:lab_result"


class TestTamperDetection:
    def test_aad_mismatch_episode_id(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        with pytest.raises(AADMismatchError):
            decrypt_episode_body(env, kms=kms, tenant_id="tenant-alice", episode_id="ep-OTHER", schema_label="lab_result")

    def test_aad_mismatch_tenant(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        with pytest.raises(AADMismatchError):
            decrypt_episode_body(env, kms=kms, tenant_id="tenant-bob", episode_id=ctx["episode_id"], schema_label=ctx["schema_label"])

    def test_aad_mismatch_schema_label(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        with pytest.raises(AADMismatchError):
            decrypt_episode_body(env, kms=kms, tenant_id=ctx["tenant_id"], episode_id=ctx["episode_id"], schema_label="medication")

    def test_ciphertext_tamper_fails_gcm(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"some real plaintext", kms=kms, **ctx)
        # flip a byte in the ciphertext
        import base64

        raw = base64.urlsafe_b64decode(env.ciphertext + "==")
        tampered = bytes([raw[0] ^ 0x01]) + raw[1:]
        bad = EncryptedBody(
            schema=env.schema,
            key_id=env.key_id,
            nonce=env.nonce,
            ciphertext=base64.urlsafe_b64encode(tampered).decode().rstrip("="),
            aad=env.aad,
            alg=env.alg,
            wrapped_dek=env.wrapped_dek,
        )
        with pytest.raises(InvalidTag):
            decrypt_episode_body(bad, kms=kms, **ctx)


class TestSchemaGuard:
    def test_unknown_schema_rejected(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        bad = EncryptedBody(
            schema="omur.encrypted_body.v999",
            key_id=env.key_id,
            nonce=env.nonce,
            ciphertext=env.ciphertext,
            aad=env.aad,
            alg=env.alg,
            wrapped_dek=env.wrapped_dek,
        )
        with pytest.raises(UnsupportedSchemaError):
            decrypt_episode_body(bad, kms=kms, **ctx)

    def test_unknown_alg_rejected(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        bad = EncryptedBody(
            schema=env.schema,
            key_id=env.key_id,
            nonce=env.nonce,
            ciphertext=env.ciphertext,
            aad=env.aad,
            alg="ChaCha20-Poly1305",
            wrapped_dek=env.wrapped_dek,
        )
        with pytest.raises(UnsupportedSchemaError):
            decrypt_episode_body(bad, kms=kms, **ctx)


class TestNoPlaintextLeak:
    def test_envelope_metadata_does_not_contain_plaintext(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        plaintext = b"the patient reports left-sided chest pain"
        env = encrypt_episode_body(plaintext, kms=kms, **ctx)
        for field in (env.schema, env.key_id, env.nonce, env.aad, env.alg, env.wrapped_dek):
            assert b"chest pain" not in field.encode()
            assert b"patient reports" not in field.encode()


class TestEmbedWindow:
    """ADR-029 amendment (2026-05-16): optional `content_for_embedding`
    plaintext window for the gnokee cosine recall lane.

    gnokee 0.8 contract (gnokeelabs/gnokee#132) guarantees the window
    leaves gnokee only over the TEI socket and is dropped from gnokee
    local scope before any persistence stage; here we exercise only the
    SDK-side wire shape.
    """

    def test_default_is_none(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        assert env.content_for_embedding is None

    def test_dict_omits_field_when_none(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, **ctx)
        wire = env.to_dict()
        assert "content_for_embedding" not in wire

    def test_dict_includes_field_when_set(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, embed_window="Hemoglobin: 13.5 g/dL", **ctx)
        wire = env.to_dict()
        assert wire["content_for_embedding"] == "Hemoglobin: 13.5 g/dL"

    def test_from_dict_round_trip_preserves_window(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        env = encrypt_episode_body(b"x", kms=kms, embed_window="window text", **ctx)
        again = EncryptedBody.from_dict(env.to_dict())
        assert again.content_for_embedding == "window text"
        assert again == env

    def test_from_dict_backward_compat_missing_field(self) -> None:
        wire = {
            "schema": SCHEMA_V1,
            "key_id": "omur:tenant:t:k_user:v1",
            "nonce": "AAAA",
            "ciphertext": "BBBB",
            "aad": "omur:gnokee:episode:e:t:lab_result",
            "alg": "AES-256-GCM",
            "wrapped_dek": "CCCC",
        }
        env = EncryptedBody.from_dict(wire)
        assert env.content_for_embedding is None

    def test_embed_window_rejects_bytes(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        with pytest.raises(TypeError):
            encrypt_episode_body(b"x", kms=kms, embed_window=b"oops bytes", **ctx)  # type: ignore[arg-type]

    def test_window_does_not_alter_ciphertext_path(self, kms: FakeKMS, ctx: dict[str, str]) -> None:
        """The window is an out-of-band hint; the ciphertext + AAD path
        must round-trip identically whether or not the window is set."""
        plaintext = b"baseline encrypted body content"
        with_window = encrypt_episode_body(plaintext, kms=kms, embed_window="hint", **ctx)
        assert decrypt_episode_body(with_window, kms=kms, **ctx) == plaintext

    def test_window_visible_in_dict_does_not_leak_into_aad(
        self, kms: FakeKMS, ctx: dict[str, str]
    ) -> None:
        """The window rides on the envelope as a separate field; it must
        not be bound into AAD (that would change tamper-detection
        semantics on recall when gnokee echoes the envelope back)."""
        env = encrypt_episode_body(b"x", kms=kms, embed_window="window text", **ctx)
        assert "window text" not in env.aad
