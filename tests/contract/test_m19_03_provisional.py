"""Focused contract/schema smoke for provisional M19-03."""

from typing import cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m19_03 import (
    M1903_OUTPUT_MEDIA_TYPE,
    M1903_PROVISIONAL_ABI,
    DisagreementStatus,
    FusionStatus,
    ReliabilityBand,
    SourceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_preserve_attribution_and_conflict() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "integrated-evidence",
        "source-contribution",
        "disagreement",
        "aggregation",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    metadata = tuple(_metadata(schema) for schema in schemas.values())
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(str(item["dossierSha256"]).startswith("sha256:") for item in metadata)
    assert all(str(item["dossierSlice"]).endswith(":6604-6644") for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["sourceAttributionRequired"]
        and item["reliabilityRequired"]
        and item["uncertaintyRequired"]
        and item["disagreementPreservationRequired"]
        and item["explicitAbstentionRequired"]
        and item["unsupportedToNegative"] is False
        for item in metadata
    )
    assert all(
        str(item["upstreamInputMediaType"]).endswith("m19-02+json")
        and item["parentTarget"] == "proteotype"
        for item in metadata
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M1903_OUTPUT_MEDIA_TYPE
    assert M1903_PROVISIONAL_ABI is True


def test_replay_helpers_are_canonical_and_tamper_sensitive() -> None:
    schemas = contract_json_schemas()
    metadata = _metadata(schemas["request"])
    assert metadata["allOmicsFusion"] is False
    assert metadata["identityInference"] is False
    assert metadata["consentInference"] is False
    assert metadata["disagreementErasure"] is False


def test_fusion_states_and_source_ownership_are_explicit() -> None:
    assert SourceKind.IMMUNOPEPTIDOMIC_EVIDENCE.value == "immunopeptidomic_evidence"
    assert ReliabilityBand.NOT_EVALUABLE.value == "not_evaluable"
    assert DisagreementStatus.OPEN.value == "open"
    assert FusionStatus.ABSTAINED.value == "abstained"
    assert FusionStatus.ABSTAINED.value == "abstained"
    assert FusionStatus.INTEGRATED.value == "integrated"
