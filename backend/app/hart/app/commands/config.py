"""Device configuration: commands 12-15 (read) and 17, 18, 34, 35 (write).

TODO(spec): byte layouts and command-specific response codes are transcribed from
general knowledge of the universal / common practice command specs. Verify against
HCF_SPEC-127 / -151 and real devices.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, replace

from app.hart.app.codec import (
    byte_at,
    decode_date,
    decode_float,
    decode_packed_ascii,
    decode_uint,
    encode_date,
    encode_float,
    encode_packed_ascii,
)
from app.hart.app.commands.base import Command
from app.hart.tables import WRITE_PROTECTED, unit_name

TAG_LENGTH = 8
DESCRIPTOR_LENGTH = 16
MESSAGE_LENGTH = 32


def _check_text(text: str, max_length: int, what: str) -> None:
    if len(text) > max_length:
        raise ValueError(f"{what} is limited to {max_length} characters")
    encode_packed_ascii(text, 3)  # raises on characters that cannot be packed


@dataclass(frozen=True)
class TagDescriptorDate:
    tag: str
    descriptor: str
    date: datetime.date | None

    def normalized(self) -> TagDescriptorDate:
        """As the device will store it: upper case, trailing spaces stripped."""
        return replace(
            self, tag=self.tag.upper().rstrip(), descriptor=self.descriptor.upper().rstrip()
        )


@dataclass(frozen=True)
class TransducerInfo:
    serial_number: int | None
    unit_code: int | None
    upper_limit: float | None
    lower_limit: float | None
    minimum_span: float | None


@dataclass(frozen=True)
class DeviceInfo:
    alarm_selection: int | None
    transfer_function: int | None
    range_unit_code: int | None
    upper_range: float | None
    lower_range: float | None
    damping_s: float | None
    write_protect: int | None

    @property
    def range_unit(self) -> str:
        return "" if self.range_unit_code is None else unit_name(self.range_unit_code)

    @property
    def is_write_protected(self) -> bool:
        return self.write_protect == WRITE_PROTECTED


@dataclass(frozen=True)
class RangeValues:
    unit_code: int | None
    upper: float | None
    lower: float | None


class ReadMessage(Command[str]):
    number = 12

    def decode(self, payload: bytes) -> str:
        return decode_packed_ascii(payload[:24])


class ReadTagDescriptorDate(Command[TagDescriptorDate]):
    number = 13

    def decode(self, payload: bytes) -> TagDescriptorDate:
        return TagDescriptorDate(
            tag=decode_packed_ascii(payload[0:6]),
            descriptor=decode_packed_ascii(payload[6:18]),
            date=decode_date(payload, 18),
        )


class ReadTransducerInfo(Command[TransducerInfo]):
    number = 14

    def decode(self, payload: bytes) -> TransducerInfo:
        return TransducerInfo(
            serial_number=decode_uint(payload, 0, 3),
            unit_code=byte_at(payload, 3),
            upper_limit=decode_float(payload, 4),
            lower_limit=decode_float(payload, 8),
            minimum_span=decode_float(payload, 12),
        )


class ReadDeviceInfo(Command[DeviceInfo]):
    number = 15

    def decode(self, payload: bytes) -> DeviceInfo:
        return DeviceInfo(
            alarm_selection=byte_at(payload, 0),
            transfer_function=byte_at(payload, 1),
            range_unit_code=byte_at(payload, 2),
            upper_range=decode_float(payload, 3),
            lower_range=decode_float(payload, 7),
            damping_s=decode_float(payload, 11),
            write_protect=byte_at(payload, 15),
        )


_WRITE_CODES = {7: "in write protect mode"}


class WriteMessage(Command[str]):
    number = 17
    response_codes = _WRITE_CODES

    def __init__(self, message: str) -> None:
        _check_text(message, MESSAGE_LENGTH, "message")
        self.message = message

    def encode(self) -> bytes:
        return encode_packed_ascii(self.message, 24)

    def decode(self, payload: bytes) -> str:
        return decode_packed_ascii(payload[:24])


class WriteTagDescriptorDate(Command[TagDescriptorDate]):
    number = 18
    response_codes = {**_WRITE_CODES, 9: "invalid date code detected"}

    def __init__(self, value: TagDescriptorDate) -> None:
        _check_text(value.tag, TAG_LENGTH, "tag")
        _check_text(value.descriptor, DESCRIPTOR_LENGTH, "descriptor")
        if value.date is None:
            raise ValueError("a date is required")
        self.value = value

    def encode(self) -> bytes:
        assert self.value.date is not None
        return (
            encode_packed_ascii(self.value.tag, 6)
            + encode_packed_ascii(self.value.descriptor, 12)
            + encode_date(self.value.date)
        )

    def decode(self, payload: bytes) -> TagDescriptorDate:
        return ReadTagDescriptorDate().decode(payload)


class WriteDamping(Command[float | None]):
    number = 34
    response_codes = {
        **_WRITE_CODES,
        3: "damping value too large",
        4: "damping value too small",
        8: "warning: set to nearest possible value",
    }

    def __init__(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("damping must be a finite number of seconds, 0 or more")
        self.seconds = seconds

    def encode(self) -> bytes:
        return encode_float(self.seconds)

    def decode(self, payload: bytes) -> float | None:
        return decode_float(payload, 0)


class WriteRangeValues(Command[RangeValues]):
    number = 35
    response_codes = {
        **_WRITE_CODES,
        2: "invalid units code",
        9: "lower range value too high",
        10: "lower range value too low",
        11: "upper range value too high",
        12: "upper range value too low",
        13: "upper and lower range values out of limits",
        14: "warning: span too small",
    }

    def __init__(self, unit_code: int, upper: float, lower: float) -> None:
        if not (math.isfinite(upper) and math.isfinite(lower)):
            raise ValueError("range values must be finite numbers")
        if upper == lower:
            raise ValueError("upper and lower range values must differ")
        if not 0 <= unit_code <= 255:
            raise ValueError("unit code must fit in one byte")
        self.unit_code = unit_code
        self.upper = upper
        self.lower = lower

    def encode(self) -> bytes:
        return bytes([self.unit_code]) + encode_float(self.upper) + encode_float(self.lower)

    def decode(self, payload: bytes) -> RangeValues:
        return RangeValues(byte_at(payload, 0), decode_float(payload, 1), decode_float(payload, 5))
