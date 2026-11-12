"""Commands 1, 2, 3: process values."""

from __future__ import annotations

from dataclasses import dataclass

from app.hart.app.codec import byte_at, decode_float
from app.hart.app.commands.base import Command
from app.hart.tables import unit_name

VARIABLE_NAMES = ("PV", "SV", "TV", "QV")


@dataclass(frozen=True)
class Variable:
    name: str
    value: float | None  # None = device reported "not available"
    unit_code: int

    @property
    def unit(self) -> str:
        return unit_name(self.unit_code)


@dataclass(frozen=True)
class LoopCurrent:
    current_ma: float | None
    percent_of_range: float | None


@dataclass(frozen=True)
class DynamicVariables:
    current_ma: float | None
    variables: tuple[Variable, ...]  # 0..4 entries, as many as the device sent


class ReadPrimaryVariable(Command[Variable | None]):
    number = 1

    def decode(self, payload: bytes) -> Variable | None:
        unit = byte_at(payload, 0)
        if unit is None:
            return None
        return Variable("PV", decode_float(payload, 1), unit)


class ReadLoopCurrentAndPercent(Command[LoopCurrent]):
    number = 2

    def decode(self, payload: bytes) -> LoopCurrent:
        return LoopCurrent(decode_float(payload, 0), decode_float(payload, 4))


class ReadDynamicVariables(Command[DynamicVariables]):
    number = 3

    def decode(self, payload: bytes) -> DynamicVariables:
        variables: list[Variable] = []
        for i, name in enumerate(VARIABLE_NAMES):
            offset = 4 + i * 5
            if len(payload) < offset + 5:
                break
            variables.append(Variable(name, decode_float(payload, offset + 1), payload[offset]))
        return DynamicVariables(decode_float(payload, 0), tuple(variables))
