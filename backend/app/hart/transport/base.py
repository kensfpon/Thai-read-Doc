"""Transport interface: the only place that touches hardware."""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def write(self, data: bytes) -> None:
        """Send ``data`` and return once it has fully left the port."""
        ...

    async def read(self, timeout: float) -> bytes:
        """Return whatever arrives within ``timeout`` seconds (possibly empty)."""
        ...

    async def drain_input(self) -> None:
        """Discard any bytes received but not yet read."""
        ...
