"""ADR-031/036: key ring, purpose binding, rotation, blind index; ADR-034 tokens."""

import base64

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.core import crypto
from apps.core.tokens import generate_token, hash_token

K1 = "k1:" + base64.urlsafe_b64encode(b"1" * 32).decode()
K2 = "k2:" + base64.urlsafe_b64encode(b"2" * 32).decode()


def test_round_trip_and_ciphertext_differs_from_plaintext():
    blob = crypto.encrypt_str("JBSWY3DPEHPK3PXP", purpose="p")
    assert b"JBSWY3DPEHPK3PXP" not in blob
    assert crypto.decrypt_str(blob, purpose="p") == "JBSWY3DPEHPK3PXP"
    # Random nonce: the same plaintext never produces the same ciphertext.
    assert crypto.encrypt_str("x", purpose="p") != crypto.encrypt_str("x", purpose="p")


def test_purpose_is_bound_into_the_tag():
    blob = crypto.encrypt_str("secret", purpose="identity.mfadevice.secret:1")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_str(blob, purpose="identity.mfadevice.secret:2")


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(crypto.encrypt_str("secret", purpose="p"))
    blob[-1] ^= 1
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(bytes(blob), purpose="p")


def test_rotation_old_keys_still_decrypt_and_primary_encrypts():
    with override_settings(FIELD_ENCRYPTION_KEYS=[K1]):
        old = crypto.encrypt_str("v", purpose="p")
        assert crypto.key_id_of(old) == "k1"
    with override_settings(FIELD_ENCRYPTION_KEYS=[K2, K1]):
        assert crypto.decrypt_str(old, purpose="p") == "v"
        assert crypto.key_id_of(crypto.encrypt_str("v", purpose="p")) == "k2"
    with override_settings(FIELD_ENCRYPTION_KEYS=[K2]), pytest.raises(crypto.DecryptionError):
        crypto.decrypt_str(old, purpose="p")


@pytest.mark.parametrize(
    "entries",
    [[], ["nokeyid"], ["k1:short"], [K1, K1], ["k1:" + "!" * 43]],
)
def test_invalid_key_rings_are_refused(entries):
    with pytest.raises(ImproperlyConfigured):
        crypto.parse_key_ring(entries)


def test_blind_index_is_keyed_deterministic_and_purpose_separated():
    a = crypto.blind_index("203.0.113.9", purpose="security.ip.index")
    assert a == crypto.blind_index("203.0.113.9", purpose="security.ip.index")
    assert a != crypto.blind_index("203.0.113.9", purpose="other")
    assert "203.0.113.9" not in a
    with override_settings(IP_INDEX_KEY=base64.urlsafe_b64encode(b"z" * 32).decode()):
        assert crypto.blind_index("203.0.113.9", purpose="security.ip.index") != a


def test_generate_key_is_a_valid_32_byte_key():
    assert crypto.parse_key_ring(["x:" + crypto.generate_key()]).primary_id == "x"


def test_tokens_have_256_bits_and_only_hash_is_derived():
    raw, digest = generate_token()
    assert len(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))) == 32
    assert digest == hash_token(raw) and len(digest) == 64 and raw not in digest
    assert generate_token()[0] != raw
