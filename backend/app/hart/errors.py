"""Exceptions raised by the HART stack."""

from __future__ import annotations


class HartError(Exception):
    """Base class for every error raised by the HART stack."""


class TransportError(HartError):
    """The underlying port could not be opened, read or written."""


class HartTimeoutError(HartError):
    """No valid response arrived after all retries."""


class HartCommError(HartError):
    """The response was corrupted, or the device reported a communication error."""

    def __init__(self, message: str, flags: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.flags = flags


class HartResponseError(HartError):
    """The device rejected the command (non-zero response code, no payload)."""

    def __init__(self, command: int, code: int, description: str) -> None:
        super().__init__(f"command {command}: response code {code} ({description})")
        self.command = command
        self.code = code
        self.description = description


class CommandNotAllowedError(HartError):
    """The command number is not in the read-only allowlist."""

    def __init__(self, command: int) -> None:
        super().__init__(f"command {command} is not in the read-only allowlist")
        self.command = command
