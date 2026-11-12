"""Command 0: Read Unique Identifier."""

from __future__ import annotations

from dataclasses import dataclass

from app.hart.app.codec import byte_at, decode_uint
from app.hart.app.commands.base import Command
from app.hart.errors import HartCommError
from app.hart.link.address import Address


@dataclass(frozen=True)
class DeviceIdentity:
    manufacturer_id: int
    device_type: int  # 8-bit (HART 5/6) or 16-bit expanded device type (HART 7)
    min_preambles_request: int
    hart_revision: int
    device_revision: int
    software_revision: int
    hardware_revision: int
    physical_signaling: int
    flags: int
    device_id: int  # 24-bit
    unique_id: bytes  # 5 bytes, the long address
    # HART 6+
    min_preambles_response: int | None = None
    max_device_variables: int | None = None
    config_change_counter: int | None = None
    extended_device_status: int | None = None
    # HART 7+
    private_label: int | None = None
    device_profile: int | None = None

    @property
    def address(self) -> Address:
        return Address.long(self.unique_id)


class ReadUniqueIdentifier(Command[DeviceIdentity]):
    number = 0

    def decode(self, payload: bytes) -> DeviceIdentity:
        if len(payload) < 12:
            raise HartCommError(f"command 0 response too short ({len(payload)} bytes)")
        revision = payload[4]
        manufacturer = payload[1]
        device_type = payload[2]
        if revision >= 7:
            # Bytes 1-2 hold the expanded device type; the manufacturer moved to 17-18.
            device_type = (payload[1] << 8) | payload[2]
            manufacturer = decode_uint(payload, 17, 2) or payload[1]
        return DeviceIdentity(
            manufacturer_id=manufacturer,
            device_type=device_type,
            min_preambles_request=payload[3],
            hart_revision=revision,
            device_revision=payload[5],
            software_revision=payload[6],
            hardware_revision=payload[7] >> 3,
            physical_signaling=payload[7] & 0x07,
            flags=payload[8],
            device_id=int.from_bytes(payload[9:12], "big"),
            unique_id=bytes([payload[1] & 0x3F, payload[2]]) + payload[9:12],
            min_preambles_response=byte_at(payload, 12),
            max_device_variables=byte_at(payload, 13),
            config_change_counter=decode_uint(payload, 14, 2),
            extended_device_status=byte_at(payload, 16),
            private_label=decode_uint(payload, 19, 2),
            device_profile=byte_at(payload, 21),
        )
