"""Locked caller-declared M25-08 evidence-gate fixture builders."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m25_08 import (
    M2508_M2506_INPUT_MEDIA_TYPE,
    M2508_M2507_INPUT_MEDIA_TYPE,
    AdjudicateProteotypeEvidenceGateRequest,
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    GateConfiguration,
    GateRequirement,
    PostReleaseObligation,
    RequirementCategory,
    ResidualRisk,
    RiskSeverity,
)
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

FIXTURE_REQUEST_ID = "m2508-fixture-request"
FIXTURE_VERSION = "0.1.0"
FIXTURE_DIGEST = "sha256:" + ("d" * 64)


def artifact(artifact_id: str, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=FIXTURE_VERSION,
        digest=FIXTURE_DIGEST,
        media_type=media_type,
    )


def evidence(
    reference: ArtifactReference,
    claim: str = "Locked M25-08 fixture evidence.",
) -> EvidenceReference:
    return EvidenceReference(reference=reference, role="evidence", claim=claim)


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact(
        "m2508-control-evidence", "application/vnd.glio-proteogen.control+json"
    )

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2508-fixture-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2508-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2508-identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=FIXTURE_DIGEST,
                evidence=control_evidence,
            ),
            provenance=decision("m2508-provenance"),
            consent=ConsentReference(
                decision_id="m2508-consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2508-quality"),
            support=decision("m2508-support"),
            intended_use=decision("m2508-intended-use"),
        ),
    )


def requirements(*, satisfied: bool = True) -> tuple[GateRequirement, ...]:
    return tuple(
        GateRequirement(
            requirement_id=f"m2508.requirement.{category.value}",
            category=category,
            statement=f"{category.value} evidence is locked and traceable.",
            satisfied=satisfied,
            evidence=(
                evidence(
                    artifact(f"m2508.requirement-evidence.{category.value}", "application/json")
                ),
            ),
        )
        for category in RequirementCategory
    )


def benchmarks(*, passed: bool = True) -> tuple[BenchmarkOutcome, ...]:
    return (
        BenchmarkOutcome(
            benchmark_id="m2508.benchmark.replay",
            name="canonical replay latency",
            metric_name="p95_nanoseconds",
            observed_value=600_000_000.0 if passed else 400_000_000.0,
            required_floor=500_000_000.0,
            passed=passed,
            report_artifact=artifact("m2508-benchmark-report", "application/json"),
            evidence=(evidence(artifact("m2508-benchmark-evidence", "application/json")),),
        ),
    )


def residual_risks(*, critical_open: bool = False) -> tuple[ResidualRisk, ...]:
    return (
        ResidualRisk(
            risk_id="m2508.risk.provisional-authority",
            severity=RiskSeverity.CRITICAL if critical_open else RiskSeverity.ROUTINE,
            statement="Issuer authority is caller-declared and requires governance review.",
            mitigation="Retain human review and the provisional ABI ceiling.",
            accepted=not critical_open,
            evidence=(evidence(artifact("m2508-risk-evidence", "application/json")),),
        ),
    )


def approvals(
    *, decision: ApprovalDecision = ApprovalDecision.APPROVE
) -> tuple[ApprovalRecord, ...]:
    return (
        ApprovalRecord(
            approval_id="m2508.approval.platform",
            approver_token="m2508.approver.platform",  # noqa: S106 - fixture token, not a secret.
            role="Platform engineering reviewer",
            decision=decision,
            signature_digest=FIXTURE_DIGEST,
            evidence=(evidence(artifact("m2508-approval-evidence", "application/json")),),
        ),
    )


def obligations() -> tuple[PostReleaseObligation, ...]:
    return (
        PostReleaseObligation(
            obligation_id="m2508.obligation.replay-audit",
            owner="Platform engineering",
            trigger="Every release or material evidence change.",
            action="Re-run the locked evaluator and review residual risk.",
            evidence=(evidence(artifact("m2508-obligation-evidence", "application/json")),),
        ),
    )


def configuration() -> GateConfiguration:
    return GateConfiguration(
        configuration_id="m2508.locked-gate-configuration",
        version=FIXTURE_VERSION,
        evidence=(evidence(artifact("m2508-configuration-evidence", "application/json")),),
    )


def build_request(
    *,
    requirement_satisfied: bool = True,
    benchmark_passed: bool = True,
    critical_risk_open: bool = False,
    approval_decision: ApprovalDecision = ApprovalDecision.APPROVE,
) -> AdjudicateProteotypeEvidenceGateRequest:
    mass = artifact(
        "m2508-mass-spectrometry", "application/vnd.glio-proteogen.mass-spectrometry+json"
    )
    genome = artifact(
        "m2508-genome-transcriptome", "application/vnd.glio-proteogen.genome-transcriptome+json"
    )
    ptm = artifact("m2508-ptm-annotations", "application/vnd.glio-proteogen.ptm-annotations+json")
    upstream = artifact("m2508-m2507-upstream", M2508_M2507_INPUT_MEDIA_TYPE)
    media_only = artifact("m2508-m2506-media-only", M2508_M2506_INPUT_MEDIA_TYPE)
    return AdjudicateProteotypeEvidenceGateRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        mass_spectrometry_proteome=mass,
        genome_transcriptome=genome,
        ptm_annotations=ptm,
        upstream_evidence=upstream,
        requirements=requirements(satisfied=requirement_satisfied),
        benchmarks=benchmarks(passed=benchmark_passed),
        residual_risks=residual_risks(critical_open=critical_risk_open),
        approvals=approvals(decision=approval_decision),
        post_release_obligations=obligations(),
        configuration=configuration(),
        source_artifacts=(mass, genome, ptm, upstream, media_only),
    )


def denied_request() -> AdjudicateProteotypeEvidenceGateRequest:
    request = build_request()
    references = request.context.references
    denied = references.support.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"support": denied})}
            )
        }
    )


__all__ = ["FIXTURE_DIGEST", "FIXTURE_REQUEST_ID", "build_request", "denied_request"]
