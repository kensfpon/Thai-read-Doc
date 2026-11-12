"""Decoders/encoders for HART data types. All multi-byte values are big-endian."""

from __future__ import annotations

import datetime
import math
import struct


def decode_float(data: bytes, offset: int = 0) -> float | None:
    """IEEE 754 single. Returns ``None`` for NaN ("not available") or missing bytes."""
    chunk = data[offset : offset + 4]
    if len(chunk) < 4:
        return None
    value: float = struct.unpack(">f", chunk)[0]
    return None if math.isnan(value) else value


def encode_float(value: float | None) -> bytes:
    if value is None:
        return bytes.fromhex("7FA00000")
    return struct.pack(">f", value)


def decode_uint(data: bytes, offset: int, length: int) -> int | None:
    chunk = data[offset : offset + length]
    return int.from_bytes(chunk, "big") if len(chunk) == length else None


def byte_at(data: bytes, offset: int) -> int | None:
    return data[offset] if offset < len(data) else None


def decode_date(data: bytes, offset: int = 0) -> datetime.date | None:
    """3 bytes: day, month, year - 1900. ``None`` if missing or not a real date."""
    chunk = data[offset : offset + 3]
    if len(chunk) < 3:
        return None
    try:
        return datetime.date(1900 + chunk[2], chunk[1], chunk[0])
    except ValueError:
        return None


def encode_date(value: datetime.date) -> bytes:
    if not 1900 <= value.year <= 2155:
        raise ValueError("HART dates cover the years 1900..2155")
    return bytes([value.day, value.month, value.year - 1900])


def decode_packed_ascii(data: bytes) -> str:
    """6-bit packed ASCII: every 3 bytes hold 4 characters. Trailing spaces are stripped."""
    chars: list[str] = []
    for i in range(0, len(data) - len(data) % 3, 3):
        word = int.from_bytes(data[i : i + 3], "big")
        for shift in (18, 12, 6, 0):
            code = (word >> shift) & 0x3F
            chars.append(chr(code + 0x40 if code < 0x20 else code))
    return "".join(chars).rstrip()


def encode_packed_ascii(text: str, length: int) -> bytes:
    """Encode ``text`` into ``length`` bytes (``length`` must be a multiple of 3)."""
    if length % 3:
        raise ValueError("packed ASCII length must be a multiple of 3")
    n_chars = length // 3 * 4
    padded = text.upper()[:n_chars].ljust(n_chars)
    out = bytearray()
    for i in range(0, n_chars, 4):
        word = 0
        for ch in padded[i : i + 4]:
            code = ord(ch)
            if not 0x20 <= code <= 0x5F:
                raise ValueError(f"character {ch!r} cannot be packed")
            word = (word << 6) | (code & 0x3F)
        out += word.to_bytes(3, "big")
    return bytes(out)
