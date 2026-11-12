"""HART frame encoding and a resynchronising stream parser."""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce

from app.hart.tables import (
    FRAME_ACK,
    FRAME_BACK,
    FRAME_STX,
    MIN_RX_PREAMBLES,
    PREAMBLE_BYTE,
)

_VALID_FRAME_TYPES = (FRAME_BACK, FRAME_STX, FRAME_ACK)


def checksum(data: bytes) -> int:
    """Longitudinal parity: XOR of every byte from the delimiter onwards."""
    return reduce(lambda a, b: a ^ b, data, 0)


@dataclass(frozen=True)
class Frame:
    frame_type: int  # FRAME_STX / FRAME_ACK / FRAME_BACK
    address: bytes  # as on the wire, including master/burst bits (1 or 5 bytes)
    command: int
    data: bytes = b""
    expansion: bytes = b""

    def __post_init__(self) -> None:
        if self.frame_type not in _VALID_FRAME_TYPES:
            raise ValueError(f"invalid frame type {self.frame_type}")
        if len(self.address) not in (1, 5):
            raise ValueError("address must be 1 or 5 bytes")
        if len(self.data) > 255:
            raise ValueError("data longer than 255 bytes")
        if len(self.expansion) > 3:
            raise ValueError("at most 3 expansion bytes")
        if not 0 <= self.command <= 255:
            raise ValueError("command must fit in one byte")

    @property
    def delimiter(self) -> int:
        long_bit = 0x80 if len(self.address) == 5 else 0
        return long_bit | (len(self.expansion) << 5) | self.frame_type

    def encode(self, preambles: int = 0) -> bytes:
        body = (
            bytes([self.delimiter])
            + self.address
            + self.expansion
            + bytes([self.command, len(self.data)])
            + self.data
        )
        return bytes([PREAMBLE_BYTE]) * preambles + body + bytes([checksum(body)])


@dataclass(frozen=True)
class BadFrame:
    """Bytes that looked like a frame but failed the checksum."""

    raw: bytes


def _is_delimiter(byte: int) -> bool:
    # bits 4..3 select the physical layer; 0 = asynchronous FSK.
    return (byte & 0x07) in _VALID_FRAME_TYPES and (byte & 0x18) == 0


class FrameParser:
    """Feed it received bytes in any chunking; get complete frames back.

    Discards garbage, requires at least two preamble bytes before a delimiter,
    and resynchronises after a checksum failure.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame | BadFrame]:
        self._buf += data
        out: list[Frame | BadFrame] = []
        while (item := self._next()) is not None:
            out.append(item)
        return out

    def _next(self) -> Frame | BadFrame | None:
        buf = self._buf
        preamble = bytes([PREAMBLE_BYTE]) * MIN_RX_PREAMBLES
        search_from = 0
        while True:
            n = len(buf)
            start = buf.find(preamble, search_from)
            if start < 0:
                # Keep a single trailing 0xFF: it may be the start of a preamble.
                keep = 1 if n and buf[-1] == PREAMBLE_BYTE else 0
                del buf[: n - keep]
                return None
            pos = start
            while pos < n and buf[pos] == PREAMBLE_BYTE:
                pos += 1
            if pos == n:
                del buf[:start]
                return None  # preamble only so far
            delimiter = buf[pos]
            if not _is_delimiter(delimiter):
                search_from = pos + 1
                continue

            address_len = 5 if delimiter & 0x80 else 1
            expansion_len = (delimiter >> 5) & 0x03
            header_len = 1 + address_len + expansion_len + 2
            if n - pos < header_len:
                del buf[:start]
                return None
            total = header_len + buf[pos + header_len - 1] + 1
            if n - pos < total:
                del buf[:start]
                return None

            raw = bytes(buf[pos : pos + total])
            if checksum(raw) != 0:
                del buf[: pos + 1]
                return BadFrame(raw)
            del buf[: pos + total]
            a0 = 1
            e0 = a0 + address_len
            c0 = e0 + expansion_len
            return Frame(
                frame_type=delimiter & 0x07,
                address=raw[a0:e0],
                expansion=raw[e0:c0],
                command=raw[c0],
                data=raw[c0 + 2 : -1],
            )
