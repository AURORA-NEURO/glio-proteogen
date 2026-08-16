"""Focused schema and deterministic-fixture smoke for provisional M21-02."""

from typing import cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m21_02 import (
    M2102_DOSSIER_SHA256,
    M2102_DOSSIER_SLICE,
    M2102_M2101_INPUT_MEDIA_TYPE,
    M2102_OUTPUT_MEDIA_TYPE,
    M2102_PROVISIONAL_ABI,
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
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["analyticallyKnownFixturesRequired"] is True
        assert metadata["semiSyntheticFixturesRequired"] is True
        assert metadata["normalEdgeMissingShiftedAdversarialCoverage"] is True
        assert metadata["deterministicSeedRequired"] is True
        assert metadata["reproducibilityManifestRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2102_M2101_INPUT_MEDIA_TYPE
        assert metadata["dossierSha256"] == M2102_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M2102_DOSSIER_SLICE
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2102_OUTPUT_MEDIA_TYPE
    assert M2102_PROVISIONAL_ABI is True


def test_fixture_kinds_and_generation_states_are_explicit() -> None:
    assert len(tuple(FixtureKind)) == _FIXTURE_KIND_COUNT
    assert FixtureKind.ADVERSARIAL.value == "adversarial"
    assert TruthRepresentation.ANALYTIC.value == "analytic"
    assert GenerationStatus.GENERATED.value == "generated"
    assert GenerationStatus.ABSTAINED.value == "abstained"
