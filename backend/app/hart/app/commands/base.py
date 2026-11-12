"""A command is a pure encoder/decoder: no I/O."""

from __future__ import annotations

from typing import ClassVar, TypeVar

T = TypeVar("T")


class Command[T]:
    number: ClassVar[int]
    # Command-specific meanings of response codes (override the common table).
    response_codes: ClassVar[dict[int, str]] = {}

    def encode(self) -> bytes:
        """Request data bytes."""
        return b""

    def decode(self, payload: bytes) -> T:
        """Decode response data (after the two status bytes).

        Must tolerate payloads shorter or longer than the spec: missing fields
        become ``None``, extra bytes are ignored.
        """
        raise NotImplementedError
