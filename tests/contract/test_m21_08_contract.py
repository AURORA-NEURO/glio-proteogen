"""Focused contract/schema smoke for provisional M21-08."""

from typing import cast

from glio_proteogen.contracts.m21_08 import (
    M2108_OUTPUT_MEDIA_TYPE,
    M2108_PROVISIONAL_ABI,
    GateDecision,
    GateRequirement,
    RequirementCategory,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 9


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact-1",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared gate evidence.",
    )


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_preserve_gate_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        isinstance(schema["$schema"], str) and schema["$schema"].endswith("2020-12/schema")
        for schema in schemas.values()
    )
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["traceabilityRequired"]
        and _metadata(schema)["riskControlsRequired"]
        and _metadata(schema)["benchmarkOutcomesRequired"]
        and _metadata(schema)["claimCeilingRequired"]
        and _metadata(schema)["residualRiskRequired"]
        and _metadata(schema)["approvalRequired"]
        and _metadata(schema)["postReleaseObligationsRequired"]
        and _metadata(schema)["signedReleaseRecordRequired"]
        and _metadata(schema)["noUnresolvedCriticalRequirements"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        _metadata(schema)["parentTarget"] == "complex activity" for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M2108_OUTPUT_MEDIA_TYPE
    assert M2108_PROVISIONAL_ABI is True


def test_requirement_keeps_category_and_satisfaction_typed() -> None:
    requirement = GateRequirement(
        requirement_id="requirement-1",
        category=RequirementCategory.TRACEABILITY,
        statement="Traceability package is locked.",
        satisfied=True,
        evidence=(_evidence(),),
    )
    assert requirement.category is RequirementCategory.TRACEABILITY
    assert requirement.satisfied is True
    assert GateDecision.PASS.value == "pass"
