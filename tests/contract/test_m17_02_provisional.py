"""Focused schema and conflict-preservation smoke for provisional M17-02."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m17_02 import (
    M1702_OUTPUT_MEDIA_TYPE,
    M1702_PROVISIONAL_ABI,
    AlignmentAxis,
    AlignmentStatus,
    Discrepancy,
    DiscrepancyCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_conflict_preservation() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "observation",
        "discrepancy",
        "bundle",
        "configuration",
        "policy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["conflictDetectionRequired"] is True
        assert metadata["conflictPreservationRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1702_OUTPUT_MEDIA_TYPE
    assert M1702_PROVISIONAL_ABI is True


def test_discrepancy_keeps_irreconcilable_sources_explicit() -> None:
    discrepancy = Discrepancy(
        discrepancy_id="discrepancy-1",
        code=DiscrepancyCode.SAMPLE_MISMATCH,
        axis=AlignmentAxis.SAMPLE,
        observation_ids=("observation-a", "observation-b"),
        message="Source sample keys disagree.",
    )
    assert discrepancy.review_required is True


def test_alignment_status_does_not_hide_conflict() -> None:
    assert AlignmentStatus.CONFLICTED.value == "conflicted"
