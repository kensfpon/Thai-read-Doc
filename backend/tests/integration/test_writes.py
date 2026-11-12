"""Guarded writes against the simulator."""

import datetime

import pytest

from app.hart.app.client import HartClient
from app.hart.app.commands import ReadDynamicVariables, ReadLoopCurrentAndPercent
from app.hart.app.configurator import Configurator
from app.hart.errors import (
    HartResponseError,
    WriteNotEnabledError,
    WriteProtectedError,
    WriteVerifyError,
)
from app.hart.tables import WRITE_COMMANDS
from app.hart.transport.simulator import SimulatedDevice, SimulatorTransport, SimVariable


def setup(*, allow_writes: bool = True, **device_kwargs):
    device = SimulatedDevice(variables=[SimVariable(32, 25.0)], **device_kwargs)
    sim = SimulatorTransport([device])
    from app.hart.link.master import Master

    master = Master(sim, allow_writes=allow_writes, response_timeout_s=0.02)
    client = HartClient(master)
    return device, sim, client, Configurator(client)


def sent_writes(sim: SimulatorTransport) -> list[int]:
    return [r.command for r in sim.requests if r.command in WRITE_COMMANDS]


async def test_writes_are_disabled_by_default():
    device, sim, client, config = setup(allow_writes=False)
    identity = await client.identify(0)
    with pytest.raises(WriteNotEnabledError):
        await config.write_tag_descriptor_date(identity, tag="NEW")
    with pytest.raises(WriteNotEnabledError):
        await config.write_range(identity, upper=150.0)
    assert sent_writes(sim) == []
    assert device.tag == "SIM-001" and device.upper_range == 100.0


async def test_write_tag_keeps_descriptor_and_date():
    device, _, client, config = setup()
    identity = await client.identify(0)
    result = await config.write_tag_descriptor_date(identity, tag="tt-101")
    assert result.before.tag == "SIM-001"
    assert result.after.tag == "TT-101"
    assert result.after.descriptor == "SIMULATED DEVICE"
    assert result.after.date == datetime.date(2026, 1, 1)
    assert device.tag == "TT-101"


async def test_write_message():
    device, _, client, config = setup()
    identity = await client.identify(0)
    result = await config.write_message(identity, "calibrated 2026")
    assert (result.before, result.after) == ("HART SIMULATOR", "CALIBRATED 2026")


async def test_write_range_rescales_the_loop_current():
    _, _, client, config = setup()
    identity = await client.identify(0)
    before = (await client.execute_on(identity, ReadLoopCurrentAndPercent())).value
    assert before.current_ma == pytest.approx(8.0)  # 25 degC in 0..100

    result = await config.write_range(identity, upper=50.0)
    assert (result.before.lower_range, result.before.upper_range) == (0.0, 100.0)
    assert (result.after.lower_range, result.after.upper_range) == (0.0, 50.0)

    after = await client.execute_on(identity, ReadLoopCurrentAndPercent())
    assert after.value.current_ma == pytest.approx(12.0)  # 25 degC in 0..50
    assert "configuration_changed" in after.status_flags


async def test_write_range_rejected_by_device_changes_nothing():
    device, _, client, config = setup()
    identity = await client.identify(0)
    with pytest.raises(HartResponseError) as info:
        await config.write_range(identity, upper=5000.0)
    assert info.value.code == 11
    assert info.value.description == "upper range value too high"
    assert device.upper_range == 100.0


async def test_write_damping():
    _, _, client, config = setup()
    identity = await client.identify(0)
    result = await config.write_damping(identity, 2.0)
    assert (result.before, result.after) == (0.5, 2.0)
    with pytest.raises(HartResponseError) as info:
        await config.write_damping(identity, 99.0)
    assert info.value.description == "damping value too large"


async def test_write_protected_device_is_never_written():
    device, sim, client, config = setup(write_protected=True)
    identity = await client.identify(0)
    with pytest.raises(WriteProtectedError):
        await config.write_tag_descriptor_date(identity, tag="NEW")
    with pytest.raises(WriteProtectedError):
        await config.write_damping(identity, 1.0)
    assert sent_writes(sim) == []
    assert device.tag == "SIM-001"


async def test_invalid_input_is_rejected_before_anything_is_written():
    _, sim, client, config = setup()
    identity = await client.identify(0)
    with pytest.raises(ValueError):
        await config.write_tag_descriptor_date(identity, tag="WAY-TOO-LONG")
    with pytest.raises(ValueError):
        await config.write_range(identity, lower=100.0, upper=100.0)
    assert sent_writes(sim) == []


async def test_readback_mismatch_is_reported():
    device, _, client, config = setup()
    identity = await client.identify(0)
    original = device._write

    def write_then_revert(command, data):
        result = original(command, data)
        device.damping_s = 0.5  # device silently keeps the old value
        return result

    device._write = write_then_revert  # type: ignore[method-assign]
    with pytest.raises(WriteVerifyError):
        await config.write_damping(identity, 2.0)


async def test_reads_still_work_while_writes_enabled():
    _, _, client, _ = setup()
    identity = await client.identify(0)
    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert reply.value.variables[0].value == 25.0
