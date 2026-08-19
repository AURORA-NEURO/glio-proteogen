"""Deterministic, caller-declared M22-08 evidence gate runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_08 import (
    M2208_CONTRACT_VERSION,
    M2208_MODULE_ID,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ApprovalDecision,
    GateDecision,
    GateFinding,
    GateFindingCode,
    GateRunStatus,
    ProteinRnaDiscordanceEvidenceGateResult,
    SignedReleaseRecord,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinRnaDiscordanceEvidenceGateRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M22-08 evidence adjudication requires accepted configuration, resolved identity, granted "
    "consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "M22-07 upstream evidence is accepted only as an opaque caller-declared artifact; "
            "issuer authority and source content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="research_only_gate",
        statement=(
            "A gate decision is a research-and-development release record, not a clinical, "
            "treatment, identity, consent, kinase, or generic all-omics conclusion."
        ),
    ),
    Limitation(
        code="human_review_required",
        statement=(
            "Quality engineering review remains required for provisional ABI confirmation, "
            "critical risk, support override, claim promotion, and release exception."
        ),
    ),
)


class M2208AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize adjudication."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2208ReplayError(ValueError):
    """Raised when a gate result fails canonical replay verification."""

    def __init__(self, message: str = "M22-08 replay verification failed") -> None:
        super().__init__(message)


class M2208EvidenceGateEngine:
    """Build and replay one deterministic metadata-only evidence gate decision."""

    __slots__ = ()

    def adjudicate(self, request: object) -> ProteinRnaDiscordanceEvidenceGateResult:
        preflight_m2208_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        decision = _gate_decision(canonical)
        release_record = _release_record(canonical, decision, request_digest)
        findings = _findings(canonical)
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_evidence_gate",
            "result_id": result_identifier(request_digest),
            "result_version": M2208_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": GateRunStatus.ADJUDICATED,
            "release_record": release_record,
            "findings": findings,
            "abstention_reason": None,
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": _support(decision),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteinRnaDiscordanceEvidenceGateResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteinRnaDiscordanceEvidenceGateResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: ProteinRnaDiscordanceEvidenceGateResult,
    ) -> ProteinRnaDiscordanceEvidenceGateResult:
        """Regenerate and compare the complete canonical gate result.

        Digest checks preserve stable identity failures, but a caller could otherwise
        mutate a release record or evidence tuple and self-rehash ``result_digest``.
        Regeneration from the validated request makes replay verify the adjudication
        semantics rather than only the submitted envelope.
        """
        if result.request_digest != canonical_request_digest(result.request):
            raise M2208ReplayError("M22-08 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request_digest):
            raise M2208ReplayError("M22-08 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2208ReplayError("M22-08 result payload digest mismatch")  # noqa: TRY003
        try:
            canonical_result = ProteinRnaDiscordanceEvidenceGateResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            regenerated = self.adjudicate(canonical_result.request)
        except Exception as error:
            raise M2208ReplayError from error
        if canonical_json_bytes(canonical_result) != canonical_json_bytes(regenerated):
            raise M2208ReplayError
        return canonical_result


def adjudicate_protein_rna_discordance_evidence_gate(
    request: object,
) -> ProteinRnaDiscordanceEvidenceGateResult:
    """Public stateless M22-08 evidence gate entry point."""

    return M2208EvidenceGateEngine().adjudicate(request)


def preflight_m2208_authorization(candidate: object) -> None:
    """Reject denied controls before reading caller-declared gate material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, AdjudicateProteinRnaDiscordanceEvidenceGateRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2208AuthorizationError from None
    if not authorized:
        raise M2208AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _gate_decision(request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest) -> GateDecision:
    if any(not item.satisfied for item in request.requirements):
        return GateDecision.BLOCK
    if any(not item.passed for item in request.benchmarks):
        return GateDecision.BLOCK
    if any(
        item.severity.value == "critical" and not item.accepted for item in request.residual_risks
    ):
        return GateDecision.BLOCK
    if any(item.decision is not ApprovalDecision.APPROVE for item in request.approvals):
        return GateDecision.REVIEW_REQUIRED
    return GateDecision.PASS


def _release_record(
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    decision: GateDecision,
    request_digest: str,
) -> SignedReleaseRecord:
    return SignedReleaseRecord(
        release_id="m2208.release." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        decision=decision,
        requirements=request.requirements,
        benchmarks=request.benchmarks,
        residual_risks=request.residual_risks,
        approvals=request.approvals,
        post_release_obligations=request.post_release_obligations,
        limitations=tuple(item.statement for item in _LIMITATIONS),
        signature_digest=sha256_digest(
            {
                "request_digest": request_digest,
                "decision": decision.value,
                "approvals": request.approvals,
            }
        ),
        evidence=_evidence(request),
    )


def _findings(
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
) -> tuple[GateFinding, ...]:
    findings: list[GateFinding] = []
    findings.extend(
        GateFinding(
            finding_id="m2208.finding." + item.requirement_id,
            code=GateFindingCode.REQUIREMENT_UNSATISFIED,
            message=f"requirement {item.requirement_id} is not satisfied",
            evidence=item.evidence,
        )
        for item in request.requirements
        if not item.satisfied
    )
    findings.extend(
        GateFinding(
            finding_id="m2208.finding." + item.benchmark_id,
            code=GateFindingCode.BENCHMARK_FAILED,
            message=f"benchmark {item.benchmark_id} did not meet its required floor",
            evidence=item.evidence,
        )
        for item in request.benchmarks
        if not item.passed
    )
    findings.extend(
        GateFinding(
            finding_id="m2208.finding." + item.risk_id,
            code=GateFindingCode.CRITICAL_RISK_OPEN,
            message=f"critical residual risk {item.risk_id} is open",
            evidence=item.evidence,
        )
        for item in request.residual_risks
        if item.severity.value == "critical" and not item.accepted
    )
    findings.extend(
        GateFinding(
            finding_id="m2208.finding." + item.approval_id,
            code=GateFindingCode.APPROVAL_MISSING,
            message=f"approval {item.approval_id} requires review",
            evidence=item.evidence,
        )
        for item in request.approvals
        if item.decision is not ApprovalDecision.APPROVE
    )
    return tuple(findings)


def _support(decision: GateDecision) -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="evidence_gate_adjudicated",
        rationale=(
            f"Caller-declared M22-08 gate material was structurally adjudicated as "
            f"{decision.value}; unsupported evidence was not converted into a negative finding."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M22-08 does not estimate {dimension} uncertainty from gate material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Gate evidence is caller-declared and does not establish biological or clinical "
            "uncertainty.",
        ),
    )


def _evidence(
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=("Caller-declared M22-08 gate evidence; issuer authority is not authenticated."),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    input_digests = tuple(
        dict.fromkeys(
            (
                *(artifact.digest for artifact in request.source_artifacts),
                *(
                    evidence.reference.digest
                    for evidence in request.configuration.evidence
                ),
                *(
                    evidence.reference.digest
                    for requirement in request.requirements
                    for evidence in requirement.evidence
                ),
                *(benchmark.report_artifact.digest for benchmark in request.benchmarks),
                *(
                    evidence.reference.digest
                    for benchmark in request.benchmarks
                    for evidence in benchmark.evidence
                ),
                *(
                    evidence.reference.digest
                    for risk in request.residual_risks
                    for evidence in risk.evidence
                ),
                *(
                    evidence.reference.digest
                    for approval in request.approvals
                    for evidence in approval.evidence
                ),
                *(
                    evidence.reference.digest
                    for obligation in request.post_release_obligations
                    for evidence in obligation.evidence
                ),
            )
        )
    )
    return ProvenanceRecord(
        activity_id="m2208.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2208_MODULE_ID,
        module_version=M2208_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(
            {
                "configuration": request.configuration,
                "requirements": request.requirements,
                "benchmarks": request.benchmarks,
                "risks": request.residual_risks,
                "approvals": request.approvals,
                "obligations": request.post_release_obligations,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2208AuthorizationError",
    "M2208EvidenceGateEngine",
    "M2208ReplayError",
    "adjudicate_protein_rna_discordance_evidence_gate",
    "preflight_m2208_authorization",
]
