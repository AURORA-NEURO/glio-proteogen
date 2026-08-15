"""Focused contract/schema smoke for provisional M25-08."""

from glio_proteogen.contracts.m25_08 import (
    M2508_OUTPUT_MEDIA_TYPE,
    M2508_PROVISIONAL_ABI,
    GateDecision,
    GateRequirement,
    RequirementCategory,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 10


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


def test_provisional_schemas_preserve_proteotype_gate_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["conformalProteotypeRequired"]
        and schema["x-glio-contract"]["baselineStackFallback"]
        and schema["x-glio-contract"]["traceabilityRequired"]
        and schema["x-glio-contract"]["qualityControlsRequired"]
        and schema["x-glio-contract"]["riskControlsRequired"]
        and schema["x-glio-contract"]["benchmarkOutcomesRequired"]
        and schema["x-glio-contract"]["claimCeilingRequired"]
        and schema["x-glio-contract"]["residualRiskRequired"]
        and schema["x-glio-contract"]["approvalRequired"]
        and schema["x-glio-contract"]["postReleaseObligationsRequired"]
        and schema["x-glio-contract"]["signedReleaseRecordRequired"]
        and schema["x-glio-contract"]["noUnresolvedCriticalRequirements"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2508_OUTPUT_MEDIA_TYPE
    assert M2508_PROVISIONAL_ABI is True


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
