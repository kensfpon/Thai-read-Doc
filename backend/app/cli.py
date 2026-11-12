"""hartcli: talk to a HART loop from the command line.

hartcli scan
hartcli read 3 --address 0
hartcli monitor --interval 1
hartcli --port COM5 scan            # real modem (default transport is the simulator)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from app.hart.app.client import HartClient
from app.hart.app.commands import (
    Command,
    DeviceIdentity,
    DynamicVariables,
    ReadDynamicVariables,
    ReadLoopCurrentAndPercent,
    ReadPrimaryVariable,
    ReadUniqueIdentifier,
)
from app.hart.errors import HartError
from app.hart.link.master import Master
from app.hart.transport.base import Transport
from app.hart.transport.simulator import SimulatedDevice, SimulatorTransport, SimVariable

COMMANDS: dict[int, type[Command[Any]]] = {
    0: ReadUniqueIdentifier,
    1: ReadPrimaryVariable,
    2: ReadLoopCurrentAndPercent,
    3: ReadDynamicVariables,
}


def demo_devices() -> list[SimulatedDevice]:
    return [
        SimulatedDevice(polling_address=0),
        SimulatedDevice(
            polling_address=3,
            device_type=0x2A,
            device_id=0xABCDEF,
            hart_revision=7,
            upper_range=16.0,
            variables=[SimVariable(7, 10.0, 2.0, 30.0), SimVariable(32, 31.5)],
        ),
    ]


def build_transport(args: argparse.Namespace) -> Transport:
    if args.port:
        from app.hart.transport.serial import SerialTransport

        return SerialTransport(args.port, rts_mode=args.rts)
    return SimulatorTransport(demo_devices(), realtime=args.realtime)


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def describe(identity: DeviceIdentity) -> str:
    return (
        f"unique ID {identity.unique_id.hex().upper()}  "
        f"manufacturer 0x{identity.manufacturer_id:02X}  "
        f"device type 0x{identity.device_type:0{4 if identity.hart_revision >= 7 else 2}X}  "
        f"HART {identity.hart_revision}"
    )


def print_dynamic(value: DynamicVariables) -> None:
    print(f"  loop current  {fmt(value.current_ma)} mA")
    for var in value.variables:
        print(f"  {var.name}            {fmt(var.value)} {var.unit}")


def print_value(value: object) -> None:
    if isinstance(value, DynamicVariables):
        print_dynamic(value)
    elif isinstance(value, DeviceIdentity):
        print(f"  {describe(value)}")
    elif is_dataclass(value) and not isinstance(value, type):
        for key, item in asdict(value).items():
            print(f"  {key:16} {fmt(item) if isinstance(item, float) or item is None else item}")
    else:
        print(f"  {value}")


async def cmd_scan(client: HartClient, args: argparse.Namespace) -> int:
    found = 0
    async for result in client.scan(args.first, args.last):
        if result.identity:
            found += 1
            print(f"address {result.polling_address:2}: {describe(result.identity)}")
        elif result.error:
            print(f"address {result.polling_address:2}: error — {result.error}")
    print(f"found {found} device(s) at addresses {args.first}..{args.last}")
    return 0


async def cmd_read(client: HartClient, args: argparse.Namespace) -> int:
    if args.command not in COMMANDS:
        print(f"command {args.command} is not supported yet", file=sys.stderr)
        return 2
    identity = await client.identify(args.address)
    reply = (
        await client.execute_on(identity, COMMANDS[args.command]()) if args.command != 0 else None
    )
    print(f"address {args.address}: command {args.command}")
    if reply is None:
        print_value(identity)
        return 0
    print_value(reply.value)
    if reply.response_code:
        print(f"  warning: response code {reply.response_code}")
    print(f"  status        {', '.join(reply.status_flags) or 'ok'}")
    return 0


async def cmd_monitor(client: HartClient, args: argparse.Namespace) -> int:
    identity = await client.identify(args.address)
    print(describe(identity))
    count = 0
    while args.count == 0 or count < args.count:
        reply = await client.execute_on(identity, ReadDynamicVariables())
        values = "  ".join(f"{v.name} {fmt(v.value)} {v.unit}" for v in reply.value.variables)
        status = ", ".join(reply.status_flags) or "ok"
        print(f"{fmt(reply.value.current_ma)} mA  {values}  [{status}]", flush=True)
        count += 1
        await asyncio.sleep(args.interval)
    return 0


async def run(args: argparse.Namespace) -> int:
    def show(direction: str, raw: bytes) -> None:
        print(f"    {direction} {raw.hex(' ').upper()}")

    transport = build_transport(args)
    await transport.open()
    try:
        master = Master(
            transport,
            primary=args.master == "primary",
            retries=args.retries,
            on_frame=show if args.frames else None,
        )
        handler = {"scan": cmd_scan, "read": cmd_read, "monitor": cmd_monitor}[args.action]
        return await handler(HartClient(master), args)
    except HartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="hartcli", description=__doc__.split("\n")[0])
    parser.add_argument("--port", help="serial port of the HART modem; omit to use the simulator")
    parser.add_argument("--rts", choices=["toggle", "none"], default="toggle")
    parser.add_argument("--master", choices=["primary", "secondary"], default="primary")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--frames", action="store_true", help="print raw frames as hex")
    parser.add_argument(
        "--realtime", action="store_true", help="simulator: pace bytes at 1200 baud"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    scan = sub.add_parser("scan", help="find devices by polling address")
    scan.add_argument("--first", type=int, default=0)
    scan.add_argument("--last", type=int, default=15)

    read = sub.add_parser("read", help="send one command and print the decoded reply")
    read.add_argument("command", type=int)
    read.add_argument("--address", type=int, default=0, help="polling address")

    monitor = sub.add_parser("monitor", help="poll command 3 repeatedly")
    monitor.add_argument("--address", type=int, default=0, help="polling address")
    monitor.add_argument("--interval", type=float, default=1.0)
    monitor.add_argument("--count", type=int, default=0, help="stop after N readings (0 = forever)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(parse_args(argv)))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
