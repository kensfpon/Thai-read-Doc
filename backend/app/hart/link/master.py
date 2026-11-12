"""HART master: one transaction at a time, with retries and response matching."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.hart.errors import (
    CommandNotAllowedError,
    HartCommError,
    HartError,
    HartTimeoutError,
    WriteNotEnabledError,
)
from app.hart.link.address import Address
from app.hart.link.frame import BadFrame, Frame, FrameParser
from app.hart.tables import (
    COMM_ERROR_FLAGS,
    DEFAULT_TX_PREAMBLES,
    DEVICE_STATUS_FLAGS,
    FRAME_ACK,
    FRAME_STX,
    MAX_TX_PREAMBLES,
    READ_ONLY_COMMANDS,
    RESPONSE_CODE_BUSY,
    WRITE_COMMANDS,
    decode_flags,
)
from app.hart.transport.base import Transport

FrameHook = Callable[[str, bytes], None]  # ("tx" | "rx", raw bytes)


@dataclass(frozen=True)
class Response:
    command: int
    address: Address
    response_code: int
    device_status: int
    payload: bytes  # data after the two status bytes

    @property
    def status_flags(self) -> tuple[str, ...]:
        return decode_flags(self.device_status, DEVICE_STATUS_FLAGS)


class Master:
    """Owns the transport. Every byte sent to the loop goes through ``transact``."""

    def __init__(
        self,
        transport: Transport,
        *,
        primary: bool = True,
        retries: int = 3,
        # TODO(spec): timing values are approximations of the data link spec.
        response_timeout_s: float = 0.3,
        inter_byte_timeout_s: float = 0.1,
        max_transaction_s: float = 3.0,
        allow_writes: bool = False,
        on_frame: FrameHook | None = None,
    ) -> None:
        self._transport = transport
        self._primary = primary
        self._retries = retries
        self._response_timeout_s = response_timeout_s
        self._inter_byte_timeout_s = inter_byte_timeout_s
        self._max_transaction_s = max_transaction_s
        self._allow_writes = allow_writes
        self._on_frame = on_frame
        self._lock = asyncio.Lock()

    async def transact(
        self,
        address: Address,
        command: int,
        data: bytes = b"",
        *,
        preambles: int = DEFAULT_TX_PREAMBLES,
        retries: int | None = None,
    ) -> Response:
        if command in WRITE_COMMANDS:
            if not self._allow_writes:
                raise WriteNotEnabledError(command)
        elif command not in READ_ONLY_COMMANDS:
            raise CommandNotAllowedError(command)
        preambles = min(max(preambles, DEFAULT_TX_PREAMBLES), MAX_TX_PREAMBLES)
        request = Frame(
            frame_type=FRAME_STX,
            address=address.to_wire(primary_master=self._primary),
            command=command,
            data=data,
        ).encode(preambles)

        attempts = (self._retries if retries is None else retries) + 1
        last_error: HartError = HartTimeoutError(f"no response from {address}")
        async with self._lock:
            for _ in range(attempts):
                try:
                    return await self._attempt(address, command, request)
                except (HartTimeoutError, HartCommError) as exc:
                    last_error = exc
        raise last_error

    async def _attempt(self, address: Address, command: int, request: bytes) -> Response:
        await self._transport.drain_input()
        if self._on_frame:
            self._on_frame("tx", request)
        await self._transport.write(request)

        parser = FrameParser()
        received = bytearray()
        now = time.monotonic()
        hard_deadline = now + self._max_transaction_s
        deadline = now + self._response_timeout_s
        corrupted = False

        while True:
            remaining = min(deadline, hard_deadline) - time.monotonic()
            if remaining <= 0:
                break
            chunk = await self._transport.read(remaining)
            if not chunk:
                continue
            received += chunk
            # Bytes are flowing: allow the rest of the frame to arrive.
            deadline = max(deadline, time.monotonic() + self._inter_byte_timeout_s)
            for item in parser.feed(chunk):
                if isinstance(item, BadFrame):
                    corrupted = True
                    continue
                if not self._is_reply(item, address, command):
                    continue  # our own echo, a burst frame, or another device
                if self._on_frame:
                    self._on_frame("rx", bytes(received))
                return self._to_response(item, address)

        if received and self._on_frame:
            self._on_frame("rx", bytes(received))
        if corrupted:
            raise HartCommError(f"corrupted response from {address}", ("checksum",))
        raise HartTimeoutError(f"no response from {address}")

    @staticmethod
    def _is_reply(frame: Frame, address: Address, command: int) -> bool:
        return (
            frame.frame_type == FRAME_ACK
            and frame.command == command
            and len(frame.address) == len(address.value)
            and Address.from_wire(frame.address) == address
        )

    @staticmethod
    def _to_response(frame: Frame, address: Address) -> Response:
        if len(frame.data) < 2:
            raise HartCommError(f"response from {address} has no status bytes")
        code, status = frame.data[0], frame.data[1]
        if code & 0x80:
            flags = decode_flags(code, COMM_ERROR_FLAGS)
            raise HartCommError(
                f"{address} reported communication error: {', '.join(flags) or hex(code)}", flags
            )
        if code == RESPONSE_CODE_BUSY:
            raise HartCommError(f"{address} is busy", ("busy",))
        return Response(
            command=frame.command,
            address=address,
            response_code=code,
            device_status=status,
            payload=frame.data[2:],
        )
