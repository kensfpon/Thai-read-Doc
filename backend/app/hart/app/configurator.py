"""Guarded writes: check write protection, write, read back, verify.

Every write follows the same sequence so that a caller always learns what the
device held before, and what it actually holds afterwards.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass

from app.hart.app.client import HartClient
from app.hart.app.commands import (
    DeviceIdentity,
    DeviceInfo,
    ReadDeviceInfo,
    ReadMessage,
    ReadTagDescriptorDate,
    TagDescriptorDate,
    WriteDamping,
    WriteMessage,
    WriteRangeValues,
    WriteTagDescriptorDate,
)
from app.hart.errors import WriteProtectedError, WriteVerifyError


@dataclass(frozen=True)
class WriteResult[T]:
    before: T
    after: T  # read back from the device after the write
    warning: str | None = None  # device accepted the write with a warning


def _close(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-6)


class Configurator:
    def __init__(self, client: HartClient) -> None:
        self._client = client

    async def read_info(self, device: DeviceIdentity) -> DeviceInfo:
        return (await self._client.execute_on(device, ReadDeviceInfo())).value

    async def _require_writable(self, device: DeviceIdentity) -> DeviceInfo:
        info = await self.read_info(device)
        if info.is_write_protected:
            raise WriteProtectedError(
                "device is write protected; clear the protection on the device first"
            )
        return info

    async def write_tag_descriptor_date(
        self,
        device: DeviceIdentity,
        *,
        tag: str | None = None,
        descriptor: str | None = None,
        date: datetime.date | None = None,
    ) -> WriteResult[TagDescriptorDate]:
        """Command 18 writes all three fields at once; unspecified ones keep their value."""
        await self._require_writable(device)
        before = (await self._client.execute_on(device, ReadTagDescriptorDate())).value
        wanted = TagDescriptorDate(
            tag=before.tag if tag is None else tag,
            descriptor=before.descriptor if descriptor is None else descriptor,
            # A device with an unset/invalid date still needs a valid one written.
            date=date or before.date or datetime.date(1900, 1, 1),
        ).normalized()
        command = WriteTagDescriptorDate(wanted)
        await self._client.execute_on(device, command)
        after = (await self._client.execute_on(device, ReadTagDescriptorDate())).value
        if after != wanted:
            raise WriteVerifyError(f"wrote {wanted} but the device now reports {after}")
        return WriteResult(before, after)

    async def write_message(self, device: DeviceIdentity, message: str) -> WriteResult[str]:
        await self._require_writable(device)
        before = (await self._client.execute_on(device, ReadMessage())).value
        await self._client.execute_on(device, WriteMessage(message))
        after = (await self._client.execute_on(device, ReadMessage())).value
        if after != message.upper().rstrip():
            raise WriteVerifyError(f"wrote {message!r} but the device now reports {after!r}")
        return WriteResult(before, after)

    async def write_range(
        self,
        device: DeviceIdentity,
        *,
        lower: float | None = None,
        upper: float | None = None,
        unit_code: int | None = None,
    ) -> WriteResult[DeviceInfo]:
        """Change the PV range. This rescales the 4-20 mA output immediately."""
        before = await self._require_writable(device)
        new_lower = before.lower_range if lower is None else lower
        new_upper = before.upper_range if upper is None else upper
        new_unit = before.range_unit_code if unit_code is None else unit_code
        if new_lower is None or new_upper is None or new_unit is None:
            raise ValueError("device did not report its current range; give lower, upper and unit")
        command = WriteRangeValues(new_unit, new_upper, new_lower)
        reply = await self._client.execute_on(device, command)
        after = await self.read_info(device)
        if not (
            _close(after.lower_range, new_lower)
            and _close(after.upper_range, new_upper)
            and after.range_unit_code == new_unit
        ):
            raise WriteVerifyError(
                f"wrote range {new_lower}..{new_upper} (unit {new_unit}) but the device now "
                f"reports {after.lower_range}..{after.upper_range} (unit {after.range_unit_code})"
            )
        return WriteResult(before, after, command.response_codes.get(reply.response_code))

    async def write_damping(
        self, device: DeviceIdentity, seconds: float
    ) -> WriteResult[float | None]:
        before = await self._require_writable(device)
        command = WriteDamping(seconds)
        reply = await self._client.execute_on(device, command)
        after = await self.read_info(device)
        warning = command.response_codes.get(reply.response_code)
        # With a "set to nearest possible value" warning the device chose its own value.
        if warning is None and not _close(after.damping_s, seconds):
            raise WriteVerifyError(
                f"wrote damping {seconds} s but the device now reports {after.damping_s} s"
            )
        return WriteResult(before.damping_s, after.damping_s, warning)
