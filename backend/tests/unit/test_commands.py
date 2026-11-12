import pytest

from app.hart.app.commands import (
    ReadDynamicVariables,
    ReadLoopCurrentAndPercent,
    ReadPrimaryVariable,
    ReadUniqueIdentifier,
)
from app.hart.errors import HartCommError

CMD0_HART5 = bytes.fromhex("FE 26 06 05 05 01 02 08 00 123456")
CMD0_HART7 = bytes.fromhex("FE E1 9D 05 07 03 04 10 00 ABCDEF 05 04 0001 00 0026 0026 01")


def test_cmd0_hart5():
    identity = ReadUniqueIdentifier().decode(CMD0_HART5)
    assert identity.manufacturer_id == 0x26
    assert identity.device_type == 0x06
    assert identity.min_preambles_request == 5
    assert identity.hart_revision == 5
    assert identity.hardware_revision == 1
    assert identity.device_id == 0x123456
    assert identity.unique_id == bytes.fromhex("2606123456")
    assert identity.max_device_variables is None
    assert str(identity.address) == "2606123456"


def test_cmd0_hart7_uses_expanded_device_type():
    identity = ReadUniqueIdentifier().decode(CMD0_HART7)
    assert identity.hart_revision == 7
    assert identity.device_type == 0xE19D
    assert identity.manufacturer_id == 0x0026
    # top two bits of the expanded device type are masked out of the address
    assert identity.unique_id == bytes.fromhex("219DABCDEF")
    assert identity.max_device_variables == 4
    assert identity.config_change_counter == 1
    assert identity.device_profile == 1


def test_cmd0_too_short():
    with pytest.raises(HartCommError):
        ReadUniqueIdentifier().decode(CMD0_HART5[:8])


def test_cmd1():
    pv = ReadPrimaryVariable().decode(bytes.fromhex("20 41C80000"))
    assert pv is not None
    assert (pv.value, pv.unit_code, pv.unit) == (25.0, 32, "°C")
    assert ReadPrimaryVariable().decode(b"") is None


def test_cmd2():
    loop = ReadLoopCurrentAndPercent().decode(bytes.fromhex("41400000 42480000"))
    assert (loop.current_ma, loop.percent_of_range) == (12.0, 50.0)


def test_cmd3_full():
    payload = bytes.fromhex("41400000 20 41C80000 20 41C00000 07 3F800000 FA 7FA00000")
    value = ReadDynamicVariables().decode(payload)
    assert value.current_ma == 12.0
    assert [(v.name, v.value, v.unit) for v in value.variables] == [
        ("PV", 25.0, "°C"),
        ("SV", 24.0, "°C"),
        ("TV", 1.0, "bar"),
        ("QV", None, ""),
    ]


def test_cmd3_truncated_and_oversized():
    two = ReadDynamicVariables().decode(bytes.fromhex("41400000 20 41C80000 20 41C00000"))
    assert [v.name for v in two.variables] == ["PV", "SV"]
    partial = ReadDynamicVariables().decode(bytes.fromhex("41400000 20 41C8"))
    assert partial.variables == ()
    extra = ReadDynamicVariables().decode(bytes.fromhex("41400000") + bytes(25))
    assert len(extra.variables) == 4
    assert ReadDynamicVariables().decode(b"").current_ma is None
