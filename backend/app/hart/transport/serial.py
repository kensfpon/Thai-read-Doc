"""HART modem on a serial port (1200 baud, 8 data bits, odd parity, 1 stop bit).

NOTE: not yet verified against real hardware. RTS handling in particular
differs between modems; see DESIGN.md section 10.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import serial

from app.hart.errors import TransportError

RtsMode = Literal["toggle", "none"]


class SerialTransport:
    def __init__(
        self,
        port: str,
        *,
        rts_mode: RtsMode = "toggle",
        carrier_settle_s: float = 0.005,
    ) -> None:
        self._port = port
        self._rts_mode = rts_mode
        self._carrier_settle_s = carrier_settle_s
        self._serial: serial.Serial | None = None

    def _require(self) -> serial.Serial:
        if self._serial is None:
            raise TransportError(f"port {self._port} is not open")
        return self._serial

    async def open(self) -> None:
        def _open() -> serial.Serial:
            ser = serial.Serial(
                self._port,
                baudrate=1200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
            )
            if self._rts_mode == "toggle":
                ser.rts = False
            return ser

        try:
            self._serial = await asyncio.to_thread(_open)
        except serial.SerialException as exc:
            raise TransportError(f"cannot open {self._port}: {exc}") from exc

    async def close(self) -> None:
        if self._serial is not None:
            ser, self._serial = self._serial, None
            await asyncio.to_thread(ser.close)

    async def write(self, data: bytes) -> None:
        ser = self._require()

        def _write() -> None:
            if self._rts_mode == "toggle":
                ser.rts = True
            try:
                ser.write(data)
                ser.flush()  # blocks until the OS transmit buffer is empty
            finally:
                if self._rts_mode == "toggle":
                    ser.rts = False

        try:
            if self._rts_mode == "toggle":
                ser.rts = True
                await asyncio.sleep(self._carrier_settle_s)
            await asyncio.to_thread(_write)
        except serial.SerialException as exc:
            raise TransportError(f"write failed on {self._port}: {exc}") from exc

    async def read(self, timeout: float) -> bytes:
        ser = self._require()

        def _read() -> bytes:
            ser.timeout = max(timeout, 0)
            first: bytes = ser.read(1)
            if not first:
                return b""
            rest: bytes = ser.read(ser.in_waiting)
            return first + rest

        try:
            return await asyncio.to_thread(_read)
        except serial.SerialException as exc:
            raise TransportError(f"read failed on {self._port}: {exc}") from exc

    async def drain_input(self) -> None:
        ser = self._require()
        await asyncio.to_thread(ser.reset_input_buffer)
