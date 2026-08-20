"""Deterministic, caller-declared M23-08 evidence-gate runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_08 import (
    M2308_CONTRACT_VERSION,
    M2308_EVIDENCE_CLAIM,
    M2308_MODULE_ID,
    AdjudicateVariantPeptideEvidenceGateRequest,
    ApprovalDecision,
    GateDecision,
    GateFinding,
    GateFindingCode,
    GateRunStatus,
    SignedReleaseRecord,
    VariantPeptideEvidenceGateResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateVariantPeptideEvidenceGateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideEvidenceGateResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M2308AuthorizationError(ValueError):
    """Caller-declared controls do not authorize adjudication."""

    def __init__(self) -> None:
        super().__init__(
            "M23-08 evidence adjudication requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2308ReplayError(ValueError):
    """A gate result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def preflight_m2308_authorization(candidate: object) -> None:
    """Reject denied controls before reading caller-declared gate material."""

    try:
        context = _member(candidate, "context")
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
            _state_value(_member(references, role)) == value for role, value in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2308AuthorizationError from None
    if not authorized:
        raise M2308AuthorizationError


def _gate_decision(request: AdjudicateVariantPeptideEvidenceGateRequest) -> GateDecision:
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


def _evidence(
    request: AdjudicateVariantPeptideEvidenceGateRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts = list(request.source_artifacts)
    artifacts.extend(
        evidence.reference for item in request.requirements for evidence in item.evidence
    )
    artifacts.extend(item.report_artifact for item in request.benchmarks)
    artifacts.extend(
        evidence.reference for item in request.benchmarks for evidence in item.evidence
    )
    artifacts.extend(
        evidence.reference for item in request.residual_risks for evidence in item.evidence
    )
    artifacts.extend(
        evidence.reference for item in request.approvals for evidence in item.evidence
    )
    artifacts.extend(
        evidence.reference
        for item in request.post_release_obligations
        for evidence in item.evidence
    )
    artifacts.extend(evidence.reference for evidence in request.configuration.evidence)
    artifacts.extend(
        (
            references.approved_configuration.evidence,
            references.identity_lineage.evidence,
            references.provenance.evidence,
            references.consent.evidence,
            references.quality.evidence,
            references.support.evidence,
            references.intended_use.evidence,
        )
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2308_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _findings(
    request: AdjudicateVariantPeptideEvidenceGateRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[GateFinding, ...]:
    findings: list[GateFinding] = []
    findings.extend(
        GateFinding(
            finding_id="m2308.finding." + item.requirement_id,
            code=GateFindingCode.REQUIREMENT_UNSATISFIED,
            message=f"requirement {item.requirement_id} is not satisfied",
            evidence=item.evidence,
        )
        for item in request.requirements
        if not item.satisfied
    )
    findings.extend(
        GateFinding(
            finding_id="m2308.finding." + item.benchmark_id,
            code=GateFindingCode.BENCHMARK_FAILED,
            message=f"benchmark {item.benchmark_id} did not meet its required floor",
            evidence=item.evidence,
        )
        for item in request.benchmarks
        if not item.passed
    )
    findings.extend(
        GateFinding(
            finding_id="m2308.finding." + item.risk_id,
            code=GateFindingCode.CRITICAL_RISK_OPEN,
            message=f"critical residual risk {item.risk_id} is open",
            evidence=item.evidence,
        )
        for item in request.residual_risks
        if item.severity.value == "critical" and not item.accepted
    )
    findings.extend(
        GateFinding(
            finding_id="m2308.finding." + item.approval_id,
            code=GateFindingCode.APPROVAL_MISSING,
            message=f"approval {item.approval_id} requires review",
            evidence=item.evidence,
        )
        for item in request.approvals
        if item.decision is not ApprovalDecision.APPROVE
    )
    if not findings:
        findings.append(
            GateFinding(
                finding_id="m2308.finding.provisional-review",
                code=GateFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The provisional ABI and caller authority require governed review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _release_record(
    request: AdjudicateVariantPeptideEvidenceGateRequest,
    decision: GateDecision,
    request_digest: str,
    evidence: tuple[EvidenceReference, ...],
) -> SignedReleaseRecord:
    return SignedReleaseRecord(
        release_id="m2308.release." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        decision=decision,
        requirements=request.requirements,
        benchmarks=request.benchmarks,
        residual_risks=request.residual_risks,
        approvals=request.approvals,
        post_release_obligations=request.post_release_obligations,
        limitations=(
            "Issuer authority remains caller-declared.",
            "Gate output is research-use-only and not a biological or treatment claim.",
            "Human review is required for provisional ABI confirmation and exceptions.",
        ),
        signature_digest=sha256_digest(
            {
                "request_digest": request_digest,
                "decision": decision.value,
                "approvals": request.approvals,
            }
        ),
        evidence=evidence,
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M23-08 does not estimate {dimension} uncertainty from gate material.",
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


def _provenance(
    request: AdjudicateVariantPeptideEvidenceGateRequest,
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
            state=str(_state_value(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    emitted_evidence = _evidence(request)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.reference.digest for item in emitted_evidence),
            )
        )
    )
    return ProvenanceRecord(
        activity_id="m2308.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2308_MODULE_ID,
        module_version=M2308_CONTRACT_VERSION,
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


class M2308EvidenceGateEngine:
    """Adjudicate one immutable caller-declared evidence gate."""

    __slots__ = ()

    def adjudicate(self, request: object) -> VariantPeptideEvidenceGateResult:
        preflight_m2308_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        decision = _gate_decision(canonical)
        evidence = _evidence(canonical)
        record = _release_record(canonical, decision, request_digest, evidence)
        findings = _findings(canonical, evidence)
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_evidence_gate",
            "result_id": result_identifier(request_digest),
            "result_version": M2308_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "status": GateRunStatus.ADJUDICATED,
            "release_record": record,
            "findings": findings,
            "abstention_reason": None,
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="evidence_gate_adjudicated",
                rationale=(
                    f"Caller-declared gate material was structurally adjudicated as "
                    f"{decision.value}; "
                    "unsupported evidence was not converted into a negative finding."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(
                    code="caller_declared_authority",
                    statement=(
                        "Issuer authority and signatures are caller-declared and unauthenticated."
                    ),
                ),
                Limitation(
                    code="research_only_gate",
                    statement=(
                        "The gate is not a biological, clinical, treatment, identity, "
                        "consent, or kinase claim."
                    ),
                ),
                Limitation(
                    code="human_review_required",
                    statement=(
                        "Human review remains required for provisional ABI confirmation "
                        "and exceptions."
                    ),
                ),
            ),
            "human_review_required": True,
        }
        provisional = VariantPeptideEvidenceGateResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: VariantPeptideEvidenceGateResult) -> VariantPeptideEvidenceGateResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2308ReplayError  # noqa: TRY301
            if validated.result_id != result_identifier(validated.request_digest):
                raise M2308ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2308ReplayError  # noqa: TRY301
            expected = self.adjudicate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2308ReplayError  # noqa: TRY301
        except M2308ReplayError:
            raise
        except Exception as error:
            raise M2308ReplayError from error
        return validated


def adjudicate_variant_peptide_evidence_gate(
    request: object,
) -> VariantPeptideEvidenceGateResult:
    """Public stateless M23-08 evidence gate entry point."""

    return M2308EvidenceGateEngine().adjudicate(request)


__all__ = [
    "M2308AuthorizationError",
    "M2308EvidenceGateEngine",
    "M2308ReplayError",
    "adjudicate_variant_peptide_evidence_gate",
    "preflight_m2308_authorization",
]
