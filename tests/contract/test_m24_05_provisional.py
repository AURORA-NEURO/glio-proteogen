"""Focused contract/schema smoke for provisional M24-05."""

from typing import cast

from glio_proteogen.contracts.m24_05 import (
    M2405_OUTPUT_MEDIA_TYPE,
    M2405_PROVISIONAL_ABI,
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
    metadata = [cast("dict[str, object]", schema["x-glio-contract"]) for schema in schemas.values()]
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
        cast("str", item["upstreamInputMediaType"]).endswith("m24-04+json")
        and item["parentTarget"] == "biomarker panel"
        for item in metadata
    )
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2405_OUTPUT_MEDIA_TYPE
    assert output_metadata["primaryArchitecture"] == "open_set_proteotype"
    assert output_metadata["alternateArchitecture"] == "semi_supervised_classifier"
    assert M2405_PROVISIONAL_ABI is True


def test_subgroup_dimensions_and_safe_states_are_explicit() -> None:
    assert SubgroupDimension.PEDIATRIC_AYA.value == "pediatric_aya"
    assert SubgroupDimension.RARE_BIOLOGICAL_STATE.value == "rare_biological_state"
    assert CoverageStatus.UNSUPPORTED.value == "unsupported"
    assert EquityStatus.BELOW_FLOOR.value == "below_floor"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
