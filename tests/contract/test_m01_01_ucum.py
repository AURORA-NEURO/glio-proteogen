"""Pinned UCUM catalog and deterministic conversion invariants for M01-01."""

from __future__ import annotations

from decimal import Decimal

import pytest

from glio_proteogen.contracts.m01_01.ucum import (
    SUPPORTED_UCUM_CODES,
    UCUM_SYSTEM_VERSION,
    SupportedUcumCode,
    convert_quantity,
    is_supported_ucum_code,
    unit_dimension,
)

pytestmark = pytest.mark.contract


def test_catalog_version_and_case_sensitive_supported_subset_are_locked() -> None:
    assert UCUM_SYSTEM_VERSION == "2.2"
    assert {"ug", "mg", "g", "Cel", "K", "mg/mL"} <= SUPPORTED_UCUM_CODES
    assert is_supported_ucum_code("ug") is True
    assert is_supported_ucum_code("mcg") is False
    assert is_supported_ucum_code("µg") is False
    assert is_supported_ucum_code("MG") is False


@pytest.mark.parametrize(
    ("code", "dimension"),
    [
        ("ug", "mass"),
        ("mL", "volume"),
        ("Cel", "temperature"),
        ("mg/mL", "mass_concentration"),
        ("pmol/uL", "amount_concentration"),
    ],
)
def test_catalog_dimensions_are_not_caller_asserted(
    code: SupportedUcumCode,
    dimension: str,
) -> None:
    assert code in SUPPORTED_UCUM_CODES
    assert unit_dimension(code) == dimension


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (Decimal(1), "mg", "ug", Decimal("1E+3")),
        (Decimal(1000), "ug", "mg", Decimal(1)),
        (Decimal(1), "min", "s", Decimal(60)),
        (Decimal(0), "Cel", "K", Decimal("273.15")),
        (Decimal("273.15"), "K", "Cel", Decimal(0)),
        (Decimal(1), "g/L", "mg/mL", Decimal(1)),
    ],
)
def test_conversion_is_exact_for_ratio_and_affine_units(
    value: Decimal,
    source: SupportedUcumCode,
    target: SupportedUcumCode,
    expected: Decimal,
) -> None:
    assert source in SUPPORTED_UCUM_CODES
    assert target in SUPPORTED_UCUM_CODES
    assert (
        convert_quantity(
            value,
            source=source,
            target=target,
        )
        == expected
    )


def test_conversion_rejects_incommensurable_dimensions() -> None:
    with pytest.raises(ValueError, match="matching physical dimensions"):
        convert_quantity(1, source="mg", target="s")


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf"), Decimal("NaN"), Decimal("Infinity")],
)
def test_conversion_rejects_nonfinite_quantities(value: float | Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        convert_quantity(value, source="mg", target="ug")
