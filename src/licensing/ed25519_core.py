from __future__ import annotations

import hashlib


P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, -1, P) % P
I = pow(2, (P - 1) // 4, P)
B = (
    15112221349535400772501151409588531511454012693041857206046113283949847762202,
    46316835694926478169428394003475163141307993866256225615783033603165251855960,
)


def publickey(seed: bytes) -> bytes:
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    a = _secret_scalar(seed)
    return _encode_point(_scalarmult(B, a))


def sign(seed: bytes, message: bytes) -> bytes:
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    digest = hashlib.sha512(seed).digest()
    a = _clamp(digest[:32])
    prefix = digest[32:]
    public_key = _encode_point(_scalarmult(B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % Q
    encoded_r = _encode_point(_scalarmult(B, r))
    h = int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(), "little") % Q
    s = (r + h * a) % Q
    return encoded_r + s.to_bytes(32, "little")


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    try:
        a = _decode_point(public_key)
        r = _decode_point(signature[:32])
        s = int.from_bytes(signature[32:], "little")
    except Exception:
        return False
    if s >= Q:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % Q
    left = _scalarmult(B, s)
    right = _edwards_add(r, _scalarmult(a, h))
    return left == right


def _secret_scalar(seed: bytes) -> int:
    return _clamp(hashlib.sha512(seed).digest()[:32])


def _clamp(value: bytes) -> int:
    data = bytearray(value)
    data[0] &= 248
    data[31] &= 63
    data[31] |= 64
    return int.from_bytes(data, "little")


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(D * y * y + 1, -1, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * I) % P
    if x % 2 != 0:
        x = P - x
    return x


def _encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    bits = bytearray(y.to_bytes(32, "little"))
    bits[31] |= (x & 1) << 7
    return bytes(bits)


def _decode_point(encoded: bytes) -> tuple[int, int]:
    y = int.from_bytes(encoded, "little") & ((1 << 255) - 1)
    sign = encoded[31] >> 7
    if y >= P:
        raise ValueError("invalid point")
    x = _xrecover(y)
    if x & 1 != sign:
        x = P - x
    if not _isoncurve((x, y)):
        raise ValueError("point is not on curve")
    return x, y


def _isoncurve(point: tuple[int, int]) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - D * x * x * y * y) % P == 0


def _edwards_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    denominator = pow(1 + D * x1 * x2 * y1 * y2, -1, P)
    x3 = (x1 * y2 + x2 * y1) * denominator % P
    denominator = pow(1 - D * x1 * x2 * y1 * y2, -1, P)
    y3 = (y1 * y2 + x1 * x2) * denominator % P
    return x3, y3


def _scalarmult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result
