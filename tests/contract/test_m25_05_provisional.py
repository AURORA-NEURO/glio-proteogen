"""Focused contract/schema smoke for provisional M25-05."""

from typing import Any, cast

from glio_proteogen.contracts.m25_05 import (
    M2505_OUTPUT_MEDIA_TYPE,
    M2505_PROVISIONAL_ABI,
    CoverageStatus,
    EquityStatus,
    EvaluationStatus,
    SubgroupDimension,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_subgroup_equity_controls() -> None:
    schemas = contract_json_schemas()
    metadata = [cast("dict[str, Any]", schema["x-glio-contract"]) for schema in schemas.values()]
    assert len(schemas) == _SCHEMA_COUNT
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["subgroupDimensionsRequired"]
        and item["equitySafetyFloorRequired"]
        and item["calibrationRequired"]
        and item["coverageRequired"]
        and item["rareContextRestrictionRequired"]
        and item["explicitAbstentionRequired"]
        and item["unsupportedToNegative"] is False
        for item in metadata
    )
    assert all(
        item["upstreamInputMediaType"].endswith("m25-04+json")
        and item["parentTarget"] == "proteotype"
        for item in metadata
    )
    output = cast("dict[str, Any]", schemas["output"]["x-glio-contract"])
    assert output["outputMediaType"] == M2505_OUTPUT_MEDIA_TYPE
    assert output["primaryArchitecture"] == "latent_class_proteotype"
    assert output["alternateArchitecture"] == "latent_class_proteotype"
    assert M2505_PROVISIONAL_ABI is True


def test_subgroup_dimensions_and_safe_states_are_explicit() -> None:
    assert SubgroupDimension.PEDIATRIC_AYA.value == "pediatric_aya"
    assert SubgroupDimension.RARE_BIOLOGICAL_STATE.value == "rare_biological_state"
    assert CoverageStatus.UNSUPPORTED.value == "unsupported"
    assert EquityStatus.BELOW_FLOOR.value == "below_floor"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
    assert EvaluationStatus.EVALUATED.value == "evaluated"
