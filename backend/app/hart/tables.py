"""Protocol constants and lookup tables.

TODO(spec): values here are transcribed from general knowledge of the HART
specifications (HCF_SPEC-081 / -127 / -151 / -183). Verify against the official
documents and real devices before relying on them.
"""

from __future__ import annotations

PREAMBLE_BYTE = 0xFF
MIN_RX_PREAMBLES = 2
DEFAULT_TX_PREAMBLES = 5
MAX_TX_PREAMBLES = 20

# Delimiter frame types (bits 2..0).
FRAME_BACK = 0x01  # burst frame, slave -> master
FRAME_STX = 0x02  # master -> slave
FRAME_ACK = 0x06  # slave -> master

# Commands the master may always transmit. All of them are reads.
READ_ONLY_COMMANDS: frozenset[int] = frozenset({0, 1, 2, 3, 9, 11, 12, 13, 14, 15, 16, 20, 48})

# Commands that change the device's configuration. The master transmits these only
# when it was created with ``allow_writes=True``. Anything in neither set is never sent.
#   17 Write Message, 18 Write Tag/Descriptor/Date,
#   34 Write PV Damping Value, 35 Write PV Range Values
WRITE_COMMANDS: frozenset[int] = frozenset({17, 18, 34, 35})

# Command 15 "write protect code".
WRITE_PROTECTED = 1

MANUFACTURERS: dict[int, str] = {
    0x11: "Endress+Hauser",
    0x26: "Rosemount",
    0x37: "Yokogawa",
}

# Float value devices send when a variable is not available.
NAN_NOT_AVAILABLE = bytes.fromhex("7FA00000")

# First response byte with bit 7 set: communication error bitmask.
COMM_ERROR_FLAGS: dict[int, str] = {
    0x40: "vertical_parity_error",
    0x20: "overrun_error",
    0x10: "framing_error",
    0x08: "longitudinal_parity_error",
    0x02: "buffer_overflow",
}

# Second response byte: field device status.
DEVICE_STATUS_FLAGS: dict[int, str] = {
    0x80: "device_malfunction",
    0x40: "configuration_changed",
    0x20: "cold_start",
    0x10: "more_status_available",
    0x08: "loop_current_fixed",
    0x04: "loop_current_saturated",
    0x02: "non_primary_variable_out_of_limits",
    0x01: "primary_variable_out_of_limits",
}

# Response codes whose meaning is the same for every command.
RESPONSE_CODES: dict[int, str] = {
    0: "success",
    2: "invalid selection",
    5: "too few data bytes received",
    6: "device-specific command error",
    7: "in write protect mode",
    3: "passed parameter too large",
    4: "passed parameter too small",
    16: "access restricted",
    32: "busy",
    33: "delayed response initiated",
    64: "command not implemented",
}
RESPONSE_CODE_BUSY = 32

# Engineering unit codes (subset).
UNITS: dict[int, str] = {
    1: "inH2O",
    2: "inHg",
    3: "ftH2O",
    4: "mmH2O",
    5: "mmHg",
    6: "psi",
    7: "bar",
    8: "mbar",
    9: "g/cm²",
    10: "kg/cm²",
    11: "Pa",
    12: "kPa",
    13: "torr",
    14: "atm",
    16: "gal/min",
    17: "L/min",
    19: "m³/h",
    24: "L/s",
    28: "m³/s",
    32: "°C",
    33: "°F",
    34: "°R",
    35: "K",
    36: "mV",
    37: "Ω",
    38: "Hz",
    39: "mA",
    40: "gal",
    41: "L",
    43: "m³",
    44: "ft",
    45: "m",
    47: "in",
    48: "cm",
    49: "mm",
    50: "min",
    51: "s",
    57: "%",
    58: "V",
    60: "g",
    61: "kg",
    237: "MPa",
    250: "",  # not used
    251: "",  # none
}


def manufacturer_name(code: int) -> str:
    return MANUFACTURERS.get(code, f"manufacturer 0x{code:02X}")


def unit_name(code: int) -> str:
    """Human-readable unit, or ``unit <code>`` when the code is not in the table."""
    return UNITS.get(code, f"unit {code}")


def response_code_name(code: int) -> str:
    return RESPONSE_CODES.get(code, f"response code {code}")


def decode_flags(value: int, table: dict[int, str]) -> tuple[str, ...]:
    return tuple(name for bit, name in table.items() if value & bit)
