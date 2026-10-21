"""Ed25519 verification used for update manifests: RFC 8032 vectors, strictness, and agreement
with OpenSSL (through ``cryptography``, when it is installed)."""

from __future__ import annotations

import os

import pytest

from core.updates import ed25519

# RFC 8032 section 7.1 (TEST 1, 2, 3 and SHA(abc)): secret, public, message, signature
RFC8032 = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b58909351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]


@pytest.mark.parametrize("sk,pk,msg,sig", RFC8032, ids=["test1", "test2", "test3", "sha-abc"])
def test_rfc8032_vectors(sk, pk, msg, sig):
    sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
    assert ed25519.public_key(sk) == pk
    assert ed25519.sign(sk, msg) == sig
    assert ed25519.verify(pk, msg, sig)
    assert not ed25519.verify(pk, msg + b"x", sig)


def test_any_changed_bit_breaks_the_signature():
    sk = bytes(range(32))
    pk = ed25519.public_key(sk)
    msg = b"MonographPDF_0.3.1_Setup.exe sha256 ..."
    sig = ed25519.sign(sk, msg)
    for i in (0, 31, 32, 63):
        bad = bytearray(sig)
        bad[i] ^= 0x01
        assert not ed25519.verify(pk, msg, bytes(bad))
    other = ed25519.public_key(bytes(32))
    assert not ed25519.verify(other, msg, sig)


def test_non_canonical_and_malformed_signatures_are_refused():
    sk = os.urandom(32)
    pk = ed25519.public_key(sk)
    msg = b"m"
    sig = ed25519.sign(sk, msg)
    s = int.from_bytes(sig[32:], "little")
    # S + L describes the same scalar but is not canonical (signature malleability)
    assert not ed25519.verify(pk, msg, sig[:32] + int.to_bytes(s + ed25519.L, 32, "little"))
    assert not ed25519.verify(pk, msg, sig[:63])
    assert not ed25519.verify(pk, msg, b"")
    # R with y >= p is not a canonical point encoding
    assert not ed25519.verify(pk, msg, int.to_bytes(ed25519.P + 1, 32, "little") + sig[32:])
    with pytest.raises(ed25519.SignatureError):
        ed25519.verify(pk[:31], msg, sig)
    with pytest.raises(ed25519.SignatureError):
        ed25519.verify(int.to_bytes(ed25519.P, 32, "little"), msg, sig)


def test_agrees_with_openssl_on_random_keys():
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    for n in range(40):
        sk = os.urandom(32)
        msg = os.urandom(n * 7)
        ref = crypto.Ed25519PrivateKey.from_private_bytes(sk)
        pk = ref.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        assert ed25519.public_key(sk) == pk
        assert ed25519.sign(sk, msg) == ref.sign(msg)
        assert ed25519.verify(pk, msg, ref.sign(msg))
        tampered = bytearray(ref.sign(msg))
        tampered[n % 64] ^= 0x80
        ours = ed25519.verify(pk, msg, bytes(tampered))
        try:
            ref.public_key().verify(bytes(tampered), msg)
            theirs = True
        except Exception:  # noqa: BLE001
            theirs = False
        assert ours == theirs == False  # noqa: E712
