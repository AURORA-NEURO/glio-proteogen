"""Deep M23-08 contract closure and adversarial schema tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from glio_proteogen.contracts.m23_08 import (
    M2308_DOSSIER_SHA256,
    M2308_DOSSIER_SLICE,
    AdjudicateVariantPeptideEvidenceGateRequest,
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    GateConfiguration,
    GateDecision,
    GateRequirement,
    PostReleaseObligation,
    RequirementCategory,
    ResidualRisk,
    RiskSeverity,
    SignedReleaseRecord,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_CATEGORIES = tuple(RequirementCategory)
_SCHEMA_COUNT = 10


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2308.{label}",
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type="application/vnd.glio-proteogen.evidence+json",
    )


def _evidence(label: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M23-08 gate evidence.",
    )


def _controls() -> ContextReferences:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2308.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="0.1.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ContextReferences(
        approved_configuration=decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="m2308.decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="0.1.0",
            binding_digest=sha256_digest("identity-binding"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decision("provenance"),
        consent=ConsentReference(
            decision_id="m2308.decision.consent",
            state=ConsentState.GRANTED,
            policy_version="0.1.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decision("quality"),
        support=decision("support"),
        intended_use=decision("intended-use"),
    )


def _requirements(*, satisfied: bool = True) -> tuple[GateRequirement, ...]:
    return tuple(
        GateRequirement(
            requirement_id=f"m2308.requirement.{category.value}",
            category=category,
            statement=f"The {category.value} package is complete.",
            satisfied=satisfied,
            evidence=(_evidence(f"requirement-{category.value}"),),
        )
        for category in _CATEGORIES
    )


def _benchmarks(*, passed: bool = True) -> tuple[BenchmarkOutcome, ...]:
    return (
        BenchmarkOutcome(
            benchmark_id="m2308.benchmark.locked",
            name="locked release benchmark",
            metric_name="conformance rate",
            observed_value=0.99 if passed else 0.5,
            required_floor=0.95,
            passed=passed,
            report_artifact=_artifact("benchmark-report"),
            evidence=(_evidence("benchmark"),),
        ),
    )


def _risks(*, accepted: bool = True) -> tuple[ResidualRisk, ...]:
    return (
        ResidualRisk(
            risk_id="m2308.risk.material",
            severity=RiskSeverity.MATERIAL,
            statement="Issuer authority remains caller-declared.",
            mitigation="Human review remains required.",
            accepted=accepted,
            evidence=(_evidence("risk"),),
        ),
    )


def _approvals(
    *, decision: ApprovalDecision = ApprovalDecision.APPROVE
) -> tuple[ApprovalRecord, ...]:
    return (
        ApprovalRecord(
            approval_id="m2308.approval.release",
            approver_token="declared-reviewer-token",  # noqa: S106
            role="release reviewer",
            decision=decision,
            signature_digest=sha256_digest("approval-signature"),
            evidence=(_evidence("approval"),),
        ),
    )


def _obligations() -> tuple[PostReleaseObligation, ...]:
    return (
        PostReleaseObligation(
            obligation_id="m2308.obligation.review",
            owner="governed reviewer",
            trigger="new evidence or changed risk",
            action="reopen the evidence gate",
            evidence=(_evidence("obligation"),),
        ),
    )


def _configuration() -> GateConfiguration:
    return GateConfiguration(
        configuration_id="m2308.configuration.locked",
        version="0.1.0",
        evidence=(_evidence("configuration"),),
    )


def _request(
    *,
    satisfied: bool = True,
    benchmark_passed: bool = True,
    approval_decision: ApprovalDecision = ApprovalDecision.APPROVE,
    request_id: str = "m2308.request.1",
) -> AdjudicateVariantPeptideEvidenceGateRequest:
    inputs = tuple(
        _artifact(label)
        for label in (
            "mass-spectrometry-proteome",
            "genome-transcriptome",
            "ptm-annotations",
            "upstream-evidence",
        )
    )
    return AdjudicateVariantPeptideEvidenceGateRequest(
        request_id=request_id,
        context=ExecutionContext(
            request_id=request_id,
            actor_id="m2308.actor",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(),
        ),
        mass_spectrometry_proteome=inputs[0],
        genome_transcriptome=inputs[1],
        ptm_annotations=inputs[2],
        upstream_evidence=inputs[3],
        requirements=_requirements(satisfied=satisfied),
        benchmarks=_benchmarks(passed=benchmark_passed),
        residual_risks=_risks(),
        approvals=_approvals(decision=approval_decision),
        post_release_obligations=_obligations(),
        configuration=_configuration(),
        source_artifacts=inputs,
    )


def test_authority_schema_and_all_requirement_categories_are_locked() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert M2308_DOSSIER_SHA256.startswith("sha256:")
    assert M2308_DOSSIER_SLICE.endswith("8264-8304")
    assert all(
        schema["x-glio-contract"]["dossierSha256"] == M2308_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    request = _request()
    assert {item.category for item in request.requirements} == set(_CATEGORIES)
    assert canonical_request_digest(request).startswith("sha256:")


def test_exact_source_artifacts_and_context_identity_are_closed() -> None:
    request = _request()
    data = request.model_dump(mode="json")
    data["source_artifacts"][-1]["artifact_id"] = "m2308.forged"
    with pytest.raises(ValueError, match="source artifacts"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate_json(
            canonical_json_bytes(data),
            strict=True,
        )
    data = request.model_dump(mode="json")
    data["context"]["request_id"] = "m2308.mismatch"
    with pytest.raises(ValueError, match="context"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate_json(
            canonical_json_bytes(data),
            strict=True,
        )


def test_benchmark_and_record_status_closures_are_explicit() -> None:
    with pytest.raises(ValueError, match="passed flag"):
        BenchmarkOutcome(
            benchmark_id="m2308.invalid-benchmark",
            name="invalid benchmark",
            metric_name="rate",
            observed_value=0.2,
            required_floor=0.9,
            passed=True,
            report_artifact=_artifact("invalid-report"),
            evidence=(_evidence("invalid-benchmark"),),
        )
    with pytest.raises(ValueError, match="unsatisfied"):
        SignedReleaseRecord(
            release_id="m2308.release.invalid",
            version="0.1.0",
            decision=GateDecision.PASS,
            requirements=_requirements(satisfied=False),
            benchmarks=_benchmarks(),
            residual_risks=_risks(),
            approvals=_approvals(),
            post_release_obligations=_obligations(),
            limitations=("Human review required.",),
            signature_digest=sha256_digest("invalid-release"),
            evidence=(_evidence("invalid-release"),),
        )


def test_duplicate_ids_and_missing_categories_are_rejected() -> None:
    request = _request()
    data = request.model_dump(mode="json")
    data["requirements"][-1]["requirement_id"] = data["requirements"][0]["requirement_id"]
    with pytest.raises(ValueError, match="identifiers"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate_json(
            canonical_json_bytes(data),
            strict=True,
        )
    data = request.model_dump(mode="json")
    data["requirements"] = data["requirements"][:-1]
    with pytest.raises(ValueError, match="cover every required"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate_json(
            canonical_json_bytes(data),
            strict=True,
        )
