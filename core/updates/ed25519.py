"""Ed25519 signatures (RFC 8032), pure Python, used to authenticate update manifests.

Monograph PDF only *verifies* signatures at run time; :func:`sign` and :func:`public_key` exist for
the maintainer's offline release tooling and for the tests (never with a key stored in the app).

Verification is strict:
* public key, R and S must be canonical encodings (y < p, S < L), points must decode;
* the group equation [S]B == R + [k]A is checked without the cofactor (the same rule OpenSSL uses).

Timing side channels are irrelevant to verification (no secret is involved). :func:`sign` is not
constant-time and must only be used on the maintainer's own offline machine.
Cross-checked against RFC 8032 section 7.1 test vectors and OpenSSL (via ``cryptography``) in
tests/unit/test_update_crypto.py.
"""

from __future__ import annotations

import hashlib

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, P - 2, P)) % P
_SQRT_M1 = pow(2, (P - 1) // 4, P)


class SignatureError(ValueError):
    """Malformed key or signature (a well-formed but wrong signature returns False instead)."""


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


# Points in extended coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, x*y = T/Z
def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % P
    b = (p[1] + p[0]) * (q[1] + q[0]) % P
    c = 2 * p[3] * q[3] * _D % P
    d = 2 * p[2] * q[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(s: int, p):
    q = (0, 1, 1, 0)  # neutral element
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p, q) -> bool:
    return (p[0] * q[2] - q[0] * p[2]) % P == 0 and (p[1] * q[2] - q[1] * p[2]) % P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, P - 2, P) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * _SQRT_M1 % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_GY = 4 * pow(5, P - 2, P) % P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % P)


def _compress(p) -> bytes:
    zinv = pow(p[2], P - 2, P)
    x = p[0] * zinv % P
    y = p[1] * zinv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _secret_expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise SignatureError("an Ed25519 secret key has 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    """Public key of a 32-byte secret (release tooling and tests only)."""
    a, _ = _secret_expand(secret)
    return _compress(_mul(a, _G))


def sign(secret: bytes, message: bytes) -> bytes:
    """RFC 8032 signature (release tooling and tests only; not constant-time)."""
    a, prefix = _secret_expand(secret)
    pk = _compress(_mul(a, _G))
    r = int.from_bytes(_sha512(prefix + message), "little") % L
    big_r = _compress(_mul(r, _G))
    k = int.from_bytes(_sha512(big_r + pk + message), "little") % L
    s = (r + k * a) % L
    return big_r + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """True only for a valid signature of ``message`` by ``public``."""
    if not isinstance(public, (bytes, bytearray)) or len(public) != 32:
        raise SignatureError("an Ed25519 public key has 32 bytes")
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
        return False
    a_point = _decompress(bytes(public))
    if a_point is None:
        raise SignatureError("the public key is not a valid curve point")
    r_bytes = bytes(signature[:32])
    r_point = _decompress(r_bytes)
    if r_point is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    k = int.from_bytes(_sha512(r_bytes + bytes(public) + message), "little") % L
    return _equal(_mul(s, _G), _add(r_point, _mul(k, a_point)))
