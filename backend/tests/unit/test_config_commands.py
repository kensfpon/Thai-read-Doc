import datetime

import pytest

from app.hart.app.codec import decode_date, encode_date
from app.hart.app.commands import (
    ReadDeviceInfo,
    ReadTagDescriptorDate,
    ReadTransducerInfo,
    TagDescriptorDate,
    WriteDamping,
    WriteMessage,
    WriteRangeValues,
    WriteTagDescriptorDate,
)

# tag "TT-101", descriptor "BOILER FEED", date 12 Nov 2026
TAG_PACKED = bytes.fromhex("514B71 C31820")
CMD13 = TAG_PACKED + bytes.fromhex("08F24C 152806 145120 820820") + bytes([12, 11, 126])


def test_date_codec():
    assert encode_date(datetime.date(2026, 11, 12)) == bytes([12, 11, 126])
    assert decode_date(bytes([12, 11, 126])) == datetime.date(2026, 11, 12)
    assert decode_date(bytes([0, 0, 0])) is None  # unset date in a device
    assert decode_date(b"\x01") is None


def test_cmd13_decode():
    value = ReadTagDescriptorDate().decode(CMD13)
    assert value == TagDescriptorDate("TT-101", "BOILER FEED", datetime.date(2026, 11, 12))


def test_cmd18_encode_is_the_cmd13_layout():
    value = TagDescriptorDate("TT-101", "BOILER FEED", datetime.date(2026, 11, 12))
    assert WriteTagDescriptorDate(value).encode() == CMD13


def test_cmd18_validation():
    date = datetime.date(2026, 1, 1)
    with pytest.raises(ValueError):
        WriteTagDescriptorDate(TagDescriptorDate("TOOLONGTAG", "", date))
    with pytest.raises(ValueError):
        WriteTagDescriptorDate(TagDescriptorDate("ท", "", date))
    with pytest.raises(ValueError):
        WriteTagDescriptorDate(TagDescriptorDate("OK", "", None))


def test_cmd15_decode():
    # alarm 0, linear, unit degC, URV 100.0, LRV 0.0, damping 0.5 s, not write protected
    payload = bytes.fromhex("00 00 20 42C80000 00000000 3F000000 00 FA")
    info = ReadDeviceInfo().decode(payload)
    assert (info.upper_range, info.lower_range, info.damping_s) == (100.0, 0.0, 0.5)
    assert info.range_unit == "°C"
    assert not info.is_write_protected
    assert ReadDeviceInfo().decode(payload[:15] + b"\x01").is_write_protected
    short = ReadDeviceInfo().decode(payload[:7])
    assert short.upper_range == 100.0 and short.lower_range is None


def test_cmd14_decode():
    payload = bytes.fromhex("123456 20 44548000 C3480000 3F800000")
    info = ReadTransducerInfo().decode(payload)
    assert info.serial_number == 0x123456
    assert (info.upper_limit, info.lower_limit, info.minimum_span) == (850.0, -200.0, 1.0)


def test_cmd35_encode_upper_before_lower():
    assert WriteRangeValues(32, 150.0, 0.0).encode() == bytes.fromhex("20 43160000 00000000")
    with pytest.raises(ValueError):
        WriteRangeValues(32, 5.0, 5.0)
    with pytest.raises(ValueError):
        WriteRangeValues(32, float("nan"), 0.0)


def test_cmd34_encode():
    assert WriteDamping(2.0).encode() == bytes.fromhex("40000000")
    with pytest.raises(ValueError):
        WriteDamping(-1.0)


def test_cmd17_encode_pads_to_24_bytes():
    encoded = WriteMessage("HI").encode()
    assert len(encoded) == 24
    assert WriteMessage("HI").decode(encoded) == "HI"
    with pytest.raises(ValueError):
        WriteMessage("X" * 33)
