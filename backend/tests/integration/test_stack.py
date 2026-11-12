"""Whole HART stack (client -> master -> frames) against the simulator."""

import asyncio

import pytest

from app.hart.app.client import HartClient
from app.hart.app.commands import (
    Command,
    ReadDynamicVariables,
    ReadLoopCurrentAndPercent,
    ReadPrimaryVariable,
)
from app.hart.errors import (
    CommandNotAllowedError,
    HartCommError,
    HartResponseError,
    HartTimeoutError,
)
from app.hart.link.address import Address
from app.hart.link.master import Master
from app.hart.transport.simulator import SimulatedDevice, SimulatorTransport, SimVariable


def fixed_device(**kwargs) -> SimulatedDevice:
    return SimulatedDevice(variables=[SimVariable(32, 25.0), SimVariable(32, 24.0)], **kwargs)


def make(sim: SimulatorTransport, **kwargs) -> tuple[HartClient, Master]:
    kwargs.setdefault("response_timeout_s", 0.02)
    kwargs.setdefault("inter_byte_timeout_s", 0.02)
    master = Master(sim, **kwargs)
    return HartClient(master), master


async def test_identify_and_read_all_variables():
    sim = SimulatorTransport([fixed_device()])
    client, _ = make(sim)
    identity = await client.identify(0)
    assert identity.unique_id == bytes.fromhex("2606123456")

    pv = (await client.execute_on(identity, ReadPrimaryVariable())).value
    assert pv is not None and pv.value == 25.0

    loop = (await client.execute_on(identity, ReadLoopCurrentAndPercent())).value
    assert loop.current_ma == pytest.approx(8.0)
    assert loop.percent_of_range == pytest.approx(25.0)

    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert [v.value for v in reply.value.variables] == [25.0, 24.0]
    assert reply.status_flags == ()
    # command 0 went out as a short frame, everything else as a long frame
    assert [len(r.address) for r in sim.requests] == [1, 5, 5, 5]


async def test_scan_finds_hart5_and_hart7_devices():
    sim = SimulatorTransport(
        [fixed_device(polling_address=0), fixed_device(polling_address=3, hart_revision=7)]
    )
    client, _ = make(sim)
    results = [r async for r in client.scan(0, 5)]
    found = {r.polling_address: r.identity for r in results if r.identity}
    assert sorted(found) == [0, 3]
    assert found[0].hart_revision == 5 and found[3].hart_revision == 7
    assert len(results) == 6


async def test_multidrop_reports_fixed_current_status():
    sim = SimulatorTransport([fixed_device(polling_address=3)])
    client, _ = make(sim)
    identity = await client.identify(3)
    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert reply.value.current_ma == 4.0
    assert reply.status_flags == ("loop_current_fixed",)


async def test_not_available_value_is_none():
    sim = SimulatorTransport([SimulatedDevice(variables=[SimVariable(32, None)])])
    client, _ = make(sim)
    identity = await client.identify(0)
    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert reply.value.current_ma is None
    assert reply.value.variables[0].value is None


async def test_retry_after_dropped_and_corrupted_responses():
    sim = SimulatorTransport([fixed_device()])
    client, _ = make(sim, retries=3)
    sim.drop_responses = 1
    sim.corrupt_responses = 1
    sim.comm_error_responses = 1
    assert (await client.identify(0)).device_id == 0x123456
    assert len(sim.requests) == 4


async def test_timeout_after_retries_exhausted():
    sim = SimulatorTransport([fixed_device()])
    client, _ = make(sim, retries=2)
    with pytest.raises(HartTimeoutError):
        await client.identify(9)
    assert len(sim.requests) == 3


async def test_persistent_corruption_is_a_comm_error_not_a_timeout():
    sim = SimulatorTransport([fixed_device()])
    client, _ = make(sim, retries=1)
    sim.corrupt_responses = 10
    with pytest.raises(HartCommError):
        await client.identify(0)


async def test_echo_and_garbage_are_ignored():
    sim = SimulatorTransport([fixed_device()], echo=True)
    sim.garbage_before_response = bytes.fromhex("00 FF 13 55")
    client, _ = make(sim)
    identity = await client.identify(0)
    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert reply.value.variables[0].value == 25.0


async def test_write_commands_never_reach_the_wire():
    sim = SimulatorTransport([fixed_device()])
    _, master = make(sim)
    for command in (6, 17, 18, 35, 40, 45, 46):
        with pytest.raises(CommandNotAllowedError):
            await master.transact(Address.short(0), command)
    assert sim.requests == []


async def test_unimplemented_command_raises_response_error():
    class ReadMessage(Command[bytes]):
        number = 12

        def decode(self, payload: bytes) -> bytes:
            return payload

    sim = SimulatorTransport([fixed_device()])
    client, _ = make(sim)
    identity = await client.identify(0)
    with pytest.raises(HartResponseError) as info:
        await client.execute_on(identity, ReadMessage())
    assert info.value.code == 64


async def test_concurrent_transactions_are_serialised():
    sim = SimulatorTransport([fixed_device(), fixed_device(polling_address=1, device_id=0x654321)])
    client, _ = make(sim)
    a, b = await asyncio.gather(client.identify(0), client.identify(1))
    assert (a.device_id, b.device_id) == (0x123456, 0x654321)


async def test_realtime_pacing_with_default_timing():
    """At 1200 baud a command 3 reply takes longer than the response timeout to arrive;
    the master must keep reading while bytes are flowing."""
    sim = SimulatorTransport([fixed_device()], realtime=True)
    client = HartClient(Master(sim))
    identity = await client.identify(0)
    reply = await client.execute_on(identity, ReadDynamicVariables())
    assert reply.value.variables[0].value == 25.0
