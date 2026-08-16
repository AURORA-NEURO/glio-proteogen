"""Focused contract/schema smoke for provisional M23-05."""

from typing import cast

from glio_proteogen.contracts.m23_05 import (
    M2305_OUTPUT_MEDIA_TYPE,
    M2305_PROVISIONAL_ABI,
    CoverageStatus,
    EquityStatus,
    EvaluationStatus,
    SubgroupDimension,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_subgroup_equity_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        cast("dict[str, object]", schema["x-glio-contract"])["provisionalAbi"] is True
        for schema in schemas.values()
    )
    assert all(
        cast("dict[str, object]", schema["x-glio-contract"])["pendingOwnerConfirmation"] is True
        for schema in schemas.values()
    )
    assert all(
        all(
            cast("dict[str, object]", schema["x-glio-contract"])[key] is True
            for key in (
                "subgroupDimensionsRequired",
                "equitySafetyFloorRequired",
                "calibrationRequired",
                "coverageRequired",
                "rareContextRestrictionRequired",
                "explicitAbstentionRequired",
            )
        )
        and cast("dict[str, object]", schema["x-glio-contract"])["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        str(
            cast("dict[str, object]", schema["x-glio-contract"])["upstreamInputMediaType"]
        ).endswith("m23-04+json")
        and cast("dict[str, object]", schema["x-glio-contract"])["parentTarget"]
        == "variant peptide"
        for schema in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["outputMediaType"]
        == M2305_OUTPUT_MEDIA_TYPE
    )
    assert M2305_PROVISIONAL_ABI is True


def test_subgroup_dimensions_and_safe_states_are_explicit() -> None:
    assert SubgroupDimension.PEDIATRIC_AYA.value == "pediatric_aya"
    assert SubgroupDimension.RARE_BIOLOGICAL_STATE.value == "rare_biological_state"
    assert CoverageStatus.UNSUPPORTED.value == "unsupported"
    assert EquityStatus.BELOW_FLOOR.value == "below_floor"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
    assert EvaluationStatus.ABSTAINED in set(EvaluationStatus)
