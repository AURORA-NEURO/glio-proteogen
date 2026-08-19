"""Focused schema and unsupported-abstention smoke for provisional M24-06."""

from typing import Any, cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m24_06 import (
    M2406_M2405_INPUT_MEDIA_TYPE,
    M2406_OUTPUT_MEDIA_TYPE,
    M2406_PROVISIONAL_ABI,
    ChallengeDisposition,
    ChallengeKind,
    OODBand,
    RobustnessStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_CHALLENGE_KIND_COUNT = 8


def test_provisional_schemas_require_robustness_and_safe_failure_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "surface",
        "scenario",
        "observation",
        "safe-failure",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast(dict[str, Any], schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["robustnessSurfaceRequired"] is True
        assert metadata["oodScoreRequired"] is True
        assert metadata["safeFailureReportRequired"] is True
        assert metadata["unsupportedAbstentionRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "biomarker panel"
        assert metadata["upstreamInputMediaType"] == M2406_M2405_INPUT_MEDIA_TYPE
    output_schema = cast(dict[str, Any], schemas["output"])
    output_metadata = cast(dict[str, Any], output_schema["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2406_OUTPUT_MEDIA_TYPE
    assert M2406_PROVISIONAL_ABI is True


def test_challenge_kinds_and_safe_dispositions_are_explicit() -> None:
    assert len(tuple(ChallengeKind)) == _CHALLENGE_KIND_COUNT
    assert ChallengeKind.NOVEL_STATE.value == "novel_state"
    assert ChallengeDisposition.ABSTAIN_UNSUPPORTED.value == "abstain_unsupported"
    assert OODBand.OUT_OF_DOMAIN.value == "out_of_domain"
    assert RobustnessStatus.ABSTAINED.value == "abstained"
