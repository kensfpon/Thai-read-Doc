"""High-level operations built on the master: execute a command, identify, scan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypeVar

from app.hart.app.commands import Command, DeviceIdentity, ReadUniqueIdentifier
from app.hart.errors import HartError, HartResponseError, HartTimeoutError
from app.hart.link.address import Address
from app.hart.link.master import Master
from app.hart.tables import DEFAULT_TX_PREAMBLES, response_code_name

T = TypeVar("T")


@dataclass(frozen=True)
class Reply[T]:
    value: T
    response_code: int  # non-zero here is a warning: the device still sent data
    device_status: int
    status_flags: tuple[str, ...]


@dataclass(frozen=True)
class ScanResult:
    polling_address: int
    identity: DeviceIdentity | None  # None = no usable answer at this address
    error: str | None = None  # something answered but could not be understood


class HartClient:
    def __init__(self, master: Master) -> None:
        self._master = master

    async def execute(
        self,
        address: Address,
        command: Command[T],
        *,
        preambles: int = DEFAULT_TX_PREAMBLES,
        retries: int | None = None,
    ) -> Reply[T]:
        response = await self._master.transact(
            address, command.number, command.encode(), preambles=preambles, retries=retries
        )
        if response.response_code != 0 and not response.payload:
            raise HartResponseError(
                command.number,
                response.response_code,
                response_code_name(response.response_code),
            )
        return Reply(
            value=command.decode(response.payload),
            response_code=response.response_code,
            device_status=response.device_status,
            status_flags=response.status_flags,
        )

    async def execute_on(self, device: DeviceIdentity, command: Command[T]) -> Reply[T]:
        """Execute using the device's long address and requested preamble count."""
        return await self.execute(device.address, command, preambles=device.min_preambles_request)

    async def identify(self, polling_address: int, *, retries: int | None = None) -> DeviceIdentity:
        reply = await self.execute(
            Address.short(polling_address), ReadUniqueIdentifier(), retries=retries
        )
        return reply.value

    async def scan(self, first: int = 0, last: int = 15) -> AsyncIterator[ScanResult]:
        """Poll each address with command 0. Silent addresses get a single retry."""
        for polling_address in range(first, last + 1):
            try:
                identity = await self.identify(polling_address, retries=1)
            except HartTimeoutError:
                yield ScanResult(polling_address, None)
            except HartError as exc:
                # e.g. two devices answering on the same polling address
                yield ScanResult(polling_address, None, str(exc))
            else:
                yield ScanResult(polling_address, identity)
