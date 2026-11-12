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
    """The command number is in neither the read nor the write allowlist."""

    def __init__(self, command: int, message: str | None = None) -> None:
        super().__init__(message or f"command {command} is not in the allowlist")
        self.command = command


class WriteNotEnabledError(CommandNotAllowedError):
    """A write command was attempted on a master created without ``allow_writes``."""

    def __init__(self, command: int) -> None:
        super().__init__(command, f"command {command} is a write and writes are not enabled")


class WriteProtectedError(HartError):
    """The device reports write protection; nothing was sent."""


class WriteVerifyError(HartError):
    """The device accepted the write but reading back gave a different value."""
