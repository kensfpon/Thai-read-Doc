"""Simulated HART loop: answers real frames, so the whole stack runs without hardware."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.hart.app.codec import (
    decode_float,
    decode_packed_ascii,
    encode_float,
    encode_packed_ascii,
)
from app.hart.link.address import Address
from app.hart.link.frame import Frame, FrameParser
from app.hart.tables import FRAME_ACK, FRAME_STX

_BYTE_TIME_S = 11 / 1200  # start + 8 data + parity + stop at 1200 baud
_RC_NOT_IMPLEMENTED = 64
_RC_TOO_FEW_BYTES = 5
_RC_WRITE_PROTECTED = 7
_STATUS_CONFIG_CHANGED = 0x40


@dataclass
class SimVariable:
    unit_code: int
    base: float | None  # None = "not available" (NaN on the wire)
    amplitude: float = 0.0
    period_s: float = 60.0

    def value(self, t: float) -> float | None:
        if self.base is None:
            return None
        return self.base + self.amplitude * math.sin(2 * math.pi * t / self.period_s)


@dataclass
class SimulatedDevice:
    polling_address: int = 0
    manufacturer_id: int = 0x26
    device_type: int = 0x06
    device_id: int = 0x123456
    hart_revision: int = 5
    min_preambles: int = 5
    lower_range: float = 0.0
    upper_range: float = 100.0
    device_status: int = 0
    # Configuration, changed by write commands. Text is stored packed, as on the wire.
    tag: str = "SIM-001"
    descriptor: str = "SIMULATED DEVICE"
    date: bytes = bytes([1, 1, 126])  # 1 Jan 2026
    message: str = "HART SIMULATOR"
    damping_s: float = 0.5
    max_damping_s: float = 32.0
    sensor_lower_limit: float = -200.0
    sensor_upper_limit: float = 850.0
    write_protected: bool = False
    variables: list[SimVariable] = field(
        default_factory=lambda: [SimVariable(32, 25.0, 5.0), SimVariable(32, 24.0)]
    )

    @property
    def unique_id(self) -> bytes:
        return bytes([self.manufacturer_id & 0x3F, self.device_type]) + self.device_id.to_bytes(
            3, "big"
        )

    def _loop(self, t: float) -> tuple[float | None, float | None, int]:
        """Loop current (mA), percent of range, and extra status bits."""
        pv = self.variables[0].value(t) if self.variables else None
        if pv is None:
            return None, None, 0
        percent = (pv - self.lower_range) / (self.upper_range - self.lower_range) * 100
        if self.polling_address != 0:
            return 4.0, percent, 0x08  # multidrop: loop current fixed
        current = 4 + 16 * percent / 100
        clamped = min(max(current, 3.8), 20.5)
        return clamped, percent, (0x04 if clamped != current else 0)

    def _tag_descriptor_date(self) -> bytes:
        return (
            encode_packed_ascii(self.tag, 6) + encode_packed_ascii(self.descriptor, 12) + self.date
        )

    def _device_info(self) -> bytes:
        unit = self.variables[0].unit_code if self.variables else 251
        return (
            bytes([0, 0, unit])  # alarm selection, transfer function (linear), range unit
            + encode_float(self.upper_range)
            + encode_float(self.lower_range)
            + encode_float(self.damping_s)
            + bytes([1 if self.write_protected else 0, 250])
        )

    def _write(self, command: int, data: bytes) -> tuple[int, bytes] | None:
        """Apply a write command. Returns (response code, payload), or None if not a write."""
        lengths = {17: 24, 18: 21, 34: 4, 35: 9}
        if command not in lengths:
            return None
        if self.write_protected:
            return _RC_WRITE_PROTECTED, b""
        if len(data) < lengths[command]:
            return _RC_TOO_FEW_BYTES, b""
        code = 0
        if command == 17:
            self.message = decode_packed_ascii(data[:24])
            payload = encode_packed_ascii(self.message, 24)
        elif command == 18:
            self.tag = decode_packed_ascii(data[0:6])
            self.descriptor = decode_packed_ascii(data[6:18])
            self.date = bytes(data[18:21])
            payload = self._tag_descriptor_date()
        elif command == 34:
            damping = decode_float(data, 0)
            if damping is None or damping < 0:
                return 4, b""
            if damping > self.max_damping_s:
                return 3, b""
            self.damping_s = damping
            payload = encode_float(self.damping_s)
        else:
            unit = self.variables[0].unit_code if self.variables else 251
            upper, lower = decode_float(data, 1), decode_float(data, 5)
            lo, hi = self.sensor_lower_limit, self.sensor_upper_limit
            if data[0] != unit:
                return 2, b""  # the simulator does not convert units
            if upper is None or lower is None or upper == lower:
                return 13, b""
            if lower > hi:
                return 9, b""
            if lower < lo:
                return 10, b""
            if upper > hi:
                return 11, b""
            if upper < lo:
                return 12, b""
            self.upper_range, self.lower_range = upper, lower
            payload = bytes([unit]) + encode_float(upper) + encode_float(lower)
        self.device_status |= _STATUS_CONFIG_CHANGED
        return code, payload

    def respond(self, command: int, t: float, data: bytes = b"") -> tuple[int, int, bytes]:
        """Return (response code, device status, payload)."""
        written = self._write(command, data)
        current, percent, extra_status = self._loop(t)
        status = self.device_status | extra_status
        if written is not None:
            return written[0], status, written[1]
        if command == 12:
            return 0, status, encode_packed_ascii(self.message, 24)
        if command == 13:
            return 0, status, self._tag_descriptor_date()
        if command == 14:
            unit = self.variables[0].unit_code if self.variables else 251
            return (
                0,
                status,
                (
                    (self.device_id & 0xFFFFFF).to_bytes(3, "big")
                    + bytes([unit])
                    + encode_float(self.sensor_upper_limit)
                    + encode_float(self.sensor_lower_limit)
                    + encode_float(1.0)
                ),
            )
        if command == 15:
            return 0, status, self._device_info()
        if command == 0:
            payload = bytes(
                [
                    254,
                    self.manufacturer_id,
                    self.device_type,
                    self.min_preambles,
                    self.hart_revision,
                    1,  # device revision
                    1,  # software revision
                    0x08,  # hardware revision 1, physical signaling 0 (Bell 202 current)
                    0,  # flags
                ]
            ) + self.device_id.to_bytes(3, "big")
            if self.hart_revision >= 6:
                payload += bytes([5, len(self.variables), 0, 0, 0])
            if self.hart_revision >= 7:
                payload += self.manufacturer_id.to_bytes(2, "big") * 2 + bytes([1])
            return 0, status, payload
        if command == 1 and self.variables:
            pv = self.variables[0]
            return 0, status, bytes([pv.unit_code]) + encode_float(pv.value(t))
        if command == 2:
            return 0, status, encode_float(current) + encode_float(percent)
        if command == 3:
            payload = encode_float(current)
            for var in self.variables[:4]:
                payload += bytes([var.unit_code]) + encode_float(var.value(t))
            return 0, status, payload
        return _RC_NOT_IMPLEMENTED, status, b""


class SimulatorTransport:
    """In-memory transport with optional fault injection.

    ``realtime=True`` paces bytes at 1200 baud, which exercises the master's timing.
    """

    def __init__(
        self,
        devices: list[SimulatedDevice] | None = None,
        *,
        realtime: bool = False,
        echo: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.devices = devices if devices is not None else [SimulatedDevice()]
        self.realtime = realtime
        self.echo = echo
        self._clock = clock
        self._rx = bytearray()
        self._rx_started = 0.0
        self._delivered = 0
        self._open = False
        # Fault injection: counters are decremented as each fault is applied.
        self.drop_responses = 0
        self.corrupt_responses = 0
        self.comm_error_responses = 0
        self.garbage_before_response = b""
        self.requests: list[Frame] = []

    async def open(self) -> None:
        self._open = True

    async def close(self) -> None:
        self._open = False

    async def drain_input(self) -> None:
        self._rx.clear()
        self._delivered = 0

    async def write(self, data: bytes) -> None:
        if self.realtime:
            await asyncio.sleep(len(data) * _BYTE_TIME_S)
        await self.drain_input()
        if self.echo:
            self._rx += data
        for item in FrameParser().feed(data):
            if isinstance(item, Frame) and item.frame_type == FRAME_STX:
                self.requests.append(item)
                self._rx += self._answer(item)
        self._rx_started = time.monotonic()

    async def read(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while True:
            ready = len(self._rx)
            if self.realtime:
                elapsed = time.monotonic() - self._rx_started
                ready = min(ready, int(elapsed / _BYTE_TIME_S))
            if ready > self._delivered:
                chunk = bytes(self._rx[self._delivered : ready])
                self._delivered = ready
                return chunk
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return b""
            await asyncio.sleep(min(remaining, 0.005))

    def _find(self, request: Frame) -> SimulatedDevice | None:
        address = Address.from_wire(request.address)
        for device in self.devices:
            if address.is_long:
                if address.value == device.unique_id:
                    return device
            elif request.command == 0 and address.value[0] == device.polling_address:
                return device  # short frames are only valid for command 0
        return None

    def _answer(self, request: Frame) -> bytes:
        device = self._find(request)
        if device is None:
            return b""
        if self.drop_responses > 0:
            self.drop_responses -= 1
            return b""
        code, status, payload = device.respond(request.command, self._clock(), request.data)
        # At most one fault per response, so each one costs exactly one retry.
        corrupt = False
        if self.comm_error_responses > 0:
            self.comm_error_responses -= 1
            code, status, payload = 0x88, 0, b""  # comm error: longitudinal parity
        elif self.corrupt_responses > 0:
            self.corrupt_responses -= 1
            corrupt = True
        raw = bytearray(
            Frame(
                frame_type=FRAME_ACK,
                address=request.address,
                command=request.command,
                data=bytes([code, status]) + payload,
            ).encode(device.min_preambles)
        )
        if corrupt:
            raw[-2] ^= 0x01
        return self.garbage_before_response + bytes(raw)
