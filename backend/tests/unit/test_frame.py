import pytest

from app.hart.link.address import Address
from app.hart.link.frame import BadFrame, Frame, FrameParser, checksum
from app.hart.tables import FRAME_ACK, FRAME_STX

# Command 0 to polling address 0 from a primary master: the canonical HART frame.
CMD0_REQUEST = bytes.fromhex("FFFFFFFFFF 02 80 00 00 82")

# Hand-assembled command 1 reply, long frame, PV = 25.0 degC (unit 32).
CMD1_REPLY_BODY = bytes.fromhex("86 A606123456 01 07 0000 20 41C80000")
CMD1_REPLY = b"\xff" * 5 + CMD1_REPLY_BODY + bytes([checksum(CMD1_REPLY_BODY)])


def test_encode_command_0_short_frame():
    frame = Frame(FRAME_STX, Address.short(0).to_wire(primary_master=True), 0)
    assert frame.encode(preambles=5) == CMD0_REQUEST


def test_encode_secondary_master_clears_master_bit():
    frame = Frame(FRAME_STX, Address.short(5).to_wire(primary_master=False), 0)
    assert frame.encode() == bytes.fromhex("02 05 00 00 07")


def test_long_frame_delimiter_and_address():
    address = Address.long(bytes.fromhex("2606123456"))
    frame = Frame(FRAME_STX, address.to_wire(primary_master=True), 3)
    assert frame.encode()[:6] == bytes.fromhex("82 A606123456")


def test_checksum_is_xor():
    assert checksum(bytes.fromhex("02800000")) == 0x82
    assert checksum(CMD1_REPLY[5:]) == 0


def test_parse_reply():
    (frame,) = FrameParser().feed(CMD1_REPLY)
    assert isinstance(frame, Frame)
    assert frame.frame_type == FRAME_ACK
    assert frame.address == bytes.fromhex("A606123456")
    assert frame.command == 1
    assert frame.data == bytes.fromhex("0000 20 41C80000")


@pytest.mark.parametrize("chunk", [1, 2, 3, 7])
def test_parse_any_chunking(chunk):
    parser = FrameParser()
    out = []
    for i in range(0, len(CMD1_REPLY), chunk):
        out += parser.feed(CMD1_REPLY[i : i + chunk])
    assert len(out) == 1 and isinstance(out[0], Frame)


def test_parse_skips_garbage_and_handles_back_to_back_frames():
    stream = bytes.fromhex("00 13 FF 37") + CMD0_REQUEST + b"\x00" + CMD1_REPLY
    frames = FrameParser().feed(stream)
    assert [f.command for f in frames if isinstance(f, Frame)] == [0, 1]


def test_parse_accepts_two_preambles_but_not_one():
    assert len(FrameParser().feed(CMD1_REPLY[3:])) == 1  # 2 preambles left
    assert FrameParser().feed(CMD1_REPLY[4:]) == []  # 1 preamble left


def test_bad_checksum_reported_then_resync():
    corrupted = bytearray(CMD1_REPLY)
    corrupted[-3] ^= 0x10
    out = FrameParser().feed(bytes(corrupted) + CMD1_REPLY)
    assert isinstance(out[0], BadFrame)
    assert isinstance(out[-1], Frame) and out[-1].command == 1


def test_address_validation():
    with pytest.raises(ValueError):
        Address.short(64)
    with pytest.raises(ValueError):
        Address.long(b"\x00\x01")
    assert Address.from_wire(bytes.fromhex("E606123456")) == Address.long(
        bytes.fromhex("2606123456")
    )
