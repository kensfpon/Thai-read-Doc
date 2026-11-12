import pytest

from app.hart.app.codec import (
    decode_float,
    decode_packed_ascii,
    encode_float,
    encode_packed_ascii,
)


def test_float_golden_bytes():
    assert decode_float(bytes.fromhex("41C80000")) == 25.0
    assert decode_float(bytes.fromhex("00 40800000"), 1) == 4.0
    assert encode_float(12.0) == bytes.fromhex("41400000")


def test_float_nan_means_not_available():
    assert decode_float(bytes.fromhex("7FA00000")) is None
    assert encode_float(None) == bytes.fromhex("7FA00000")


def test_float_missing_bytes():
    assert decode_float(b"\x41\xc8") is None
    assert decode_float(b"", 4) is None


def test_packed_ascii_golden_bytes():
    # 6-bit codes: T=010100 T=010100 -=101101 1=110001 | 0=110000 1=110001 sp=100000 sp=100000
    packed = bytes.fromhex("514B71 C31820")
    assert encode_packed_ascii("TT-101", 6) == packed
    assert decode_packed_ascii(packed) == "TT-101"


def test_packed_ascii_lowercase_is_uppercased_and_truncated():
    assert decode_packed_ascii(encode_packed_ascii("abcdefghijk", 6)) == "ABCDEFGH"


def test_packed_ascii_rejects_unpackable():
    with pytest.raises(ValueError):
        encode_packed_ascii("a{b", 3)
