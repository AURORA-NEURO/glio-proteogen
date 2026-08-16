"""Focused contract/schema smoke for provisional M25-08."""

from typing import cast

from glio_proteogen.contracts.m25_08 import (
    M2508_DOSSIER_SHA256,
    M2508_DOSSIER_SLICE,
    M2508_OUTPUT_MEDIA_TYPE,
    M2508_PROVISIONAL_ABI,
    GateDecision,
    GateRequirement,
    RequirementCategory,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 10


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


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
    schemas = cast("dict[str, dict[str, object]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        cast("str", schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values()
    )
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["conformalProteotypeRequired"]
        and _metadata(schema)["baselineStackFallback"]
        and _metadata(schema)["traceabilityRequired"]
        and _metadata(schema)["qualityControlsRequired"]
        and _metadata(schema)["riskControlsRequired"]
        and _metadata(schema)["benchmarkOutcomesRequired"]
        and _metadata(schema)["claimCeilingRequired"]
        and _metadata(schema)["residualRiskRequired"]
        and _metadata(schema)["approvalRequired"]
        and _metadata(schema)["postReleaseObligationsRequired"]
        and _metadata(schema)["signedReleaseRecordRequired"]
        and _metadata(schema)["noUnresolvedCriticalRequirements"]
        and _metadata(schema)["humanReviewRequired"]
        and _metadata(schema)["explicitAbstentionRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(_metadata(schema)["parentTarget"] == "proteotype" for schema in schemas.values())
    assert _metadata(schemas["output"])["outputMediaType"] == M2508_OUTPUT_MEDIA_TYPE
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


def test_authority_record_is_exact_and_explicitly_provisional() -> None:
    assert M2508_DOSSIER_SHA256 == (
        "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2508_DOSSIER_SLICE.endswith(":8984-9024")


def test_schema_exposes_media_only_dependency_boundary() -> None:
    schema = cast("dict[str, dict[str, object]]", contract_json_schemas())["request"]
    metadata = _metadata(schema)
    assert metadata["declaredUpstreamMediaType"] == "application/vnd.glio-proteogen.m25-07+json"
    assert metadata["mediaOnlyBoundary"] == "application/vnd.glio-proteogen.m25-06+json"
