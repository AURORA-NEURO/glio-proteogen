"""Focused schema and deterministic-fixture smoke for provisional M24-02."""

from typing import Any, cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m24_02 import (
    M2402_M2401_INPUT_MEDIA_TYPE,
    M2402_OUTPUT_MEDIA_TYPE,
    M2402_PROVISIONAL_ABI,
    FixtureKind,
    GenerationStatus,
    TruthRepresentation,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7
_FIXTURE_KIND_COUNT = 5


def test_provisional_schemas_require_reproducible_truth_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "corpus",
        "case",
        "manifest",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, Any]", cast("dict[str, Any]", schema)["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["analyticallyKnownFixturesRequired"] is True
        assert metadata["semiSyntheticFixturesRequired"] is True
        assert metadata["normalEdgeMissingShiftedAdversarialCoverage"] is True
        assert metadata["deterministicSeedRequired"] is True
        assert metadata["reproducibilityManifestRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "biomarker panel"
        assert metadata["upstreamInputMediaType"] == M2402_M2401_INPUT_MEDIA_TYPE
    output_schema = cast("dict[str, Any]", schemas["output"])
    output_metadata = cast("dict[str, Any]", output_schema["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2402_OUTPUT_MEDIA_TYPE
    assert M2402_PROVISIONAL_ABI is True


def test_fixture_kinds_and_generation_states_are_explicit() -> None:
    assert len(tuple(FixtureKind)) == _FIXTURE_KIND_COUNT
    assert FixtureKind.ADVERSARIAL.value == "adversarial"
    assert TruthRepresentation.ANALYTIC.value == "analytic"
    assert GenerationStatus.GENERATED.value == "generated"
    assert GenerationStatus.ABSTAINED.value == "abstained"
