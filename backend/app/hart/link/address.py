"""Short (polling) and long (unique ID) HART addresses."""

from __future__ import annotations

from dataclasses import dataclass

_MASTER_BIT = 0x80
_BURST_BIT = 0x40
_ADDRESS_MASK = 0x3F


@dataclass(frozen=True)
class Address:
    """Device address without the master/burst bits.

    ``value`` is 1 byte (polling address 0..63) or 5 bytes (38-bit unique ID).
    """

    value: bytes

    def __post_init__(self) -> None:
        if len(self.value) not in (1, 5):
            raise ValueError("address must be 1 or 5 bytes")
        if self.value[0] & ~_ADDRESS_MASK:
            raise ValueError("top two bits of an address are reserved for master/burst")

    @classmethod
    def short(cls, polling_address: int) -> Address:
        if not 0 <= polling_address <= 63:
            raise ValueError("polling address must be 0..63")
        return cls(bytes([polling_address]))

    @classmethod
    def long(cls, unique_id: bytes) -> Address:
        if len(unique_id) != 5:
            raise ValueError("unique ID must be 5 bytes")
        return cls(bytes([unique_id[0] & _ADDRESS_MASK]) + unique_id[1:])

    @classmethod
    def from_wire(cls, raw: bytes) -> Address:
        return cls(bytes([raw[0] & _ADDRESS_MASK]) + raw[1:])

    @property
    def is_long(self) -> bool:
        return len(self.value) == 5

    def to_wire(self, *, primary_master: bool, burst: bool = False) -> bytes:
        first = self.value[0]
        if primary_master:
            first |= _MASTER_BIT
        if burst:
            first |= _BURST_BIT
        return bytes([first]) + self.value[1:]

    def __str__(self) -> str:
        return self.value.hex().upper() if self.is_long else f"poll {self.value[0]}"


def is_primary_master(wire_address: bytes) -> bool:
    return bool(wire_address[0] & _MASTER_BIT)
