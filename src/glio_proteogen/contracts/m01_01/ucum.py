"""Pinned UCUM subset and deterministic quantity conversion for M01-01.

The supported codes were checked against the U.S. National Library of Medicine UCUM
validation service on 2026-08-11.  M01-01 deliberately exposes a closed, versioned subset
of UCUM 2.2 instead of accepting caller-declared unit strings as authoritative.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from types import MappingProxyType
from typing import Final, Literal, TypeGuard

type SupportedUcumCode = Literal[
    "1",
    "%",
    "{count}",
    "g",
    "mg",
    "ug",
    "ng",
    "pg",
    "L",
    "mL",
    "uL",
    "s",
    "min",
    "h",
    "d",
    "K",
    "Cel",
    "mol",
    "mmol",
    "umol",
    "nmol",
    "pmol",
    "g/L",
    "mg/mL",
    "ug/uL",
    "mg/L",
    "ug/mL",
    "ng/uL",
    "ng/mL",
    "pmol/uL",
    "nmol/L",
    "Hz",
    "/min",
    "V",
    "mV",
    "kV",
    "A",
    "mA",
    "uA",
    "Pa",
    "kPa",
    "rad",
    "deg",
    "[g]",
]

UCUM_SYSTEM_VERSION: Final = "2.2"
_DECIMAL_CONTEXT: Final = Context(prec=34, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class UcumUnit:
    """One supported unit expressed as an affine transform to its canonical dimension."""

    dimension: str
    scale: Decimal
    offset: Decimal = Decimal(0)


def _unit(dimension: str, scale: str, offset: str = "0") -> UcumUnit:
    return UcumUnit(dimension=dimension, scale=Decimal(scale), offset=Decimal(offset))


_DEFINITIONS: Final[dict[SupportedUcumCode, UcumUnit]] = {
    "1": _unit("dimensionless", "1"),
    "%": _unit("dimensionless", "0.01"),
    "{count}": _unit("count", "1"),
    "g": _unit("mass", "1"),
    "mg": _unit("mass", "1e-3"),
    "ug": _unit("mass", "1e-6"),
    "ng": _unit("mass", "1e-9"),
    "pg": _unit("mass", "1e-12"),
    "L": _unit("volume", "1"),
    "mL": _unit("volume", "1e-3"),
    "uL": _unit("volume", "1e-6"),
    "s": _unit("time", "1"),
    "min": _unit("time", "60"),
    "h": _unit("time", "3600"),
    "d": _unit("time", "86400"),
    "K": _unit("temperature", "1"),
    "Cel": _unit("temperature", "1", "273.15"),
    "mol": _unit("amount", "1"),
    "mmol": _unit("amount", "1e-3"),
    "umol": _unit("amount", "1e-6"),
    "nmol": _unit("amount", "1e-9"),
    "pmol": _unit("amount", "1e-12"),
    "g/L": _unit("mass_concentration", "1"),
    "mg/mL": _unit("mass_concentration", "1"),
    "ug/uL": _unit("mass_concentration", "1"),
    "mg/L": _unit("mass_concentration", "1e-3"),
    "ug/mL": _unit("mass_concentration", "1e-3"),
    "ng/uL": _unit("mass_concentration", "1e-3"),
    "ng/mL": _unit("mass_concentration", "1e-6"),
    "pmol/uL": _unit("amount_concentration", "1e-6"),
    "nmol/L": _unit("amount_concentration", "1e-9"),
    "Hz": _unit("frequency", "1"),
    "/min": _unit("frequency", "0.01666666666666666666666666666666667"),
    "V": _unit("electric_potential", "1"),
    "mV": _unit("electric_potential", "1e-3"),
    "kV": _unit("electric_potential", "1e3"),
    "A": _unit("electric_current", "1"),
    "mA": _unit("electric_current", "1e-3"),
    "uA": _unit("electric_current", "1e-6"),
    "Pa": _unit("pressure", "1"),
    "kPa": _unit("pressure", "1e3"),
    "rad": _unit("plane_angle", "1"),
    "deg": _unit("plane_angle", "0.01745329251994329576923690768488613"),
    "[g]": _unit("acceleration", "9.80665"),
}

UCUM_UNITS: Final[Mapping[SupportedUcumCode, UcumUnit]] = MappingProxyType(_DEFINITIONS)
SUPPORTED_UCUM_CODES: Final = frozenset(_DEFINITIONS)


def is_supported_ucum_code(code: str) -> TypeGuard[SupportedUcumCode]:
    """Return whether a code belongs to the pinned M01-01 UCUM subset."""

    return code in SUPPORTED_UCUM_CODES


def unit_dimension(code: SupportedUcumCode) -> str:
    """Return the pinned physical dimension for one supported code."""

    return UCUM_UNITS[code].dimension


def convert_quantity(
    value: float | Decimal,
    *,
    source: SupportedUcumCode,
    target: SupportedUcumCode,
) -> Decimal:
    """Convert a finite decimal quantity between commensurable supported UCUM codes."""

    source_unit = UCUM_UNITS[source]
    target_unit = UCUM_UNITS[target]
    if source_unit.dimension != target_unit.dimension:
        raise ValueError("UCUM conversion requires matching physical dimensions")
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal_value.is_finite():
        raise ValueError("UCUM conversion requires a finite quantity")
    with localcontext(_DECIMAL_CONTEXT):
        canonical = decimal_value * source_unit.scale + source_unit.offset
        return (canonical - target_unit.offset) / target_unit.scale


__all__ = [
    "SUPPORTED_UCUM_CODES",
    "UCUM_SYSTEM_VERSION",
    "UCUM_UNITS",
    "SupportedUcumCode",
    "UcumUnit",
    "convert_quantity",
    "is_supported_ucum_code",
    "unit_dimension",
]
