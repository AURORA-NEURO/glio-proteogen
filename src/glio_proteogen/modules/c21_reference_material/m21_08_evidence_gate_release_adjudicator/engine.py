"""Deterministic caller-declared M21-08 evidence-gate runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_08 import (
    M2108_CONTRACT_VERSION,
    M2108_EVIDENCE_CLAIM,
    M2108_MODULE_ID,
    AdjudicateComplexActivityEvidenceGateRequest,
    ApprovalDecision,
    ComplexActivityEvidenceGateResult,
    GateDecision,
    GateFinding,
    GateFindingCode,
    GateRunStatus,
    RiskSeverity,
    SignedReleaseRecord,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

# ruff: noqa: TRY003

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateComplexActivityEvidenceGateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityEvidenceGateResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M2108AuthorizationError(ValueError):
    """Caller-declared controls do not authorize evidence adjudication."""


class M2108EvaluationError(ValueError):
    """An evidence-gate request failed safe validation."""


class M2108ReplayError(ValueError):
    """A gate result failed canonical replay verification."""


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> str | None:
    value = _member(candidate, "state")
    state = getattr(value, "value", value)
    return state if isinstance(state, str) else None


def preflight_m2108_authorization(candidate: object) -> None:
    """Reject denied controls before reading release evidence."""

    try:
        references = _member(_member(candidate, "context"), "references")
        authorized = all(
            _state(_member(references, role)) == expected
            for role, expected in _EXPECTED_CONTROLS.items()
        )
    except Exception as error:
        raise M2108AuthorizationError("M21-08 controls are malformed") from error
    if not authorized:
        raise M2108AuthorizationError("M21-08 requires all seven accepted controls")


def _evidence(
    request: AdjudicateComplexActivityEvidenceGateRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [request.upstream_evidence, *request.source_artifacts]
    artifacts.extend(evidence_item.reference for evidence_item in request.configuration.evidence)
    artifacts.extend(
        evidence_item.reference
        for requirement_item in request.requirements
        for evidence_item in requirement_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for benchmark_item in request.benchmarks
        for evidence_item in benchmark_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for risk_item in request.residual_risks
        for evidence_item in risk_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for approval_item in request.approvals
        for evidence_item in approval_item.evidence
    )
    artifacts.extend(
        evidence_item.reference
        for obligation_item in request.post_release_obligations
        for evidence_item in obligation_item.evidence
    )
    refs = request.context.references
    artifacts.extend(
        (
            refs.approved_configuration.evidence,
            refs.identity_lineage.evidence,
            refs.provenance.evidence,
            refs.consent.evidence,
            refs.quality.evidence,
            refs.support.evidence,
            refs.intended_use.evidence,
        )
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2108_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M21-08 adjudicates caller-declared evidence and does not estimate scientific error."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Gate status is sensitive to evidence completeness, benchmark floors, risk acceptance, "
            "approval, and owner review.",
        ),
    )


def _provenance(
    request: AdjudicateComplexActivityEvidenceGateRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=_state(decision) or "unknown",
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=getattr(decision, "binding_digest", None),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"m2108.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2108_MODULE_ID,
        module_version=M2108_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.upstream_evidence.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _finding(
    finding_id: str,
    code: GateFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> GateFinding:
    return GateFinding(finding_id=finding_id, code=code, message=message, evidence=evidence[:1])


def _findings(
    request: AdjudicateComplexActivityEvidenceGateRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[GateFinding, ...]:
    findings: list[GateFinding] = []
    findings.extend(
        _finding(
            f"finding.{item.requirement_id}",
            GateFindingCode.REQUIREMENT_UNSATISFIED,
            "A required release criterion is not satisfied.",
            evidence,
        )
        for item in request.requirements
        if not item.satisfied
    )
    findings.extend(
        _finding(
            f"finding.{item.benchmark_id}",
            GateFindingCode.BENCHMARK_FAILED,
            "A locked benchmark outcome did not pass its required floor.",
            evidence,
        )
        for item in request.benchmarks
        if not item.passed
    )
    findings.extend(
        _finding(
            f"finding.{item.risk_id}",
            GateFindingCode.CRITICAL_RISK_OPEN,
            "A critical residual risk remains open for release.",
            evidence,
        )
        for item in request.residual_risks
        if item.severity is RiskSeverity.CRITICAL and not item.accepted
    )
    findings.extend(
        _finding(
            f"finding.{item.approval_id}",
            GateFindingCode.APPROVAL_MISSING,
            "A release approval is not an explicit approval decision.",
            evidence,
        )
        for item in request.approvals
        if item.decision is not ApprovalDecision.APPROVE
    )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m2108_caller_declared_evidence",
            statement=(
                "Release evidence, benchmark values, risk acceptance, approvals, and "
                "issuer authority are caller-declared."
            ),
        ),
        Limitation(
            code="m2108_prohibited_outputs",
            statement=(
                "No complex-activity estimate, kinase, all-omics, treatment, identity, "
                "or consent inference is emitted."
            ),
        ),
        Limitation(
            code="m2108_abstention" if abstained else "m2108_provisional",
            statement=(
                "Unsafe or incomplete release evidence is withheld pending external review."
                if abstained
                else "The provisional ABI remains subject to owner confirmation before promotion."
            ),
        ),
    )


def _release_record(
    request: AdjudicateComplexActivityEvidenceGateRequest,
    evidence: tuple[EvidenceReference, ...],
    request_digest: str,
) -> SignedReleaseRecord:
    return SignedReleaseRecord(
        release_id=f"release.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        decision=GateDecision.PASS,
        requirements=request.requirements,
        benchmarks=request.benchmarks,
        residual_risks=request.residual_risks,
        approvals=request.approvals,
        post_release_obligations=request.post_release_obligations,
        limitations=("M21-08 remains provisional pending owner confirmation.",),
        signature_digest=sha256_digest(f"m2108.release:{request_digest}"),
        evidence=evidence,
    )


class M2108Engine:
    """Stateless deterministic M21-08 evidence-gate adjudicator."""

    def validate_request(self, candidate: object) -> AdjudicateComplexActivityEvidenceGateRequest:
        preflight_m2108_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M2108EvaluationError("M21-08 request is invalid") from error

    def evaluate(self, candidate: object) -> ComplexActivityEvidenceGateResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        findings = _findings(request, evidence)
        adjudicated = not findings
        record = _release_record(request, evidence, request_digest) if adjudicated else None
        support = SupportDecision(
            status=SupportStatus.SUPPORTED if adjudicated else SupportStatus.REVIEW_REQUIRED,
            reason_code="m2108_gate_passed" if adjudicated else "m2108_review_required",
            rationale=(
                "All declared evidence-gate requirements pass and approvals are present."
                if adjudicated
                else "Release evidence cannot be safely promoted without external review."
            ),
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_evidence_gate",
            "result_id": result_identifier(request),
            "result_version": M2108_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": GateRunStatus.ADJUDICATED if adjudicated else GateRunStatus.ABSTAINED,
            "release_record": record,
            "findings": findings,
            "abstention_reason": (
                None
                if adjudicated
                else "M21-08 abstained because release evidence is not safely adjudicable."
            ),
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=not adjudicated),
            "human_review_required": True,
        }
        constructed = ComplexActivityEvidenceGateResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2108EvaluationError("M21-08 result construction failed safely") from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityEvidenceGateResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2108ReplayError("M21-08 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2108ReplayError("M21-08 result digest mismatch")
        if replay:
            expected = self.evaluate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2108ReplayError("M21-08 deterministic replay mismatch")
        return validated


def adjudicate_complex_activity_evidence_gate(
    candidate: object,
) -> ComplexActivityEvidenceGateResult:
    """Public stateless M21-08 adjudication entry point."""

    return M2108Engine().evaluate(candidate)


__all__ = [
    "M2108AuthorizationError",
    "M2108Engine",
    "M2108EvaluationError",
    "M2108ReplayError",
    "adjudicate_complex_activity_evidence_gate",
    "preflight_m2108_authorization",
]
