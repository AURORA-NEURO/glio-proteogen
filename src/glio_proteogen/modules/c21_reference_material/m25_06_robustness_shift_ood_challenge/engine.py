"""Deterministic, caller-declared M25-06 robustness challenge execution.

M25-06 is deliberately metadata-only at this provisional boundary.  It never
traverses the M25-04 payload or mutates upstream material.  The challenge
scenario declarations are evaluated into a bounded robustness surface, while
unsupported or reviewer-required perturbations fail closed with an explicit
safe-failure report.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_06 import (
    M2506_CONTRACT_VERSION,
    M2506_MODULE_ID,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeProteotypeRobustnessRequest,
    ChallengeScenario,
    OODBand,
    ProteotypeRobustnessChallengeResult,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
    SafeFailureReport,
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
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeProteotypeRobustnessRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-06 challenge execution requires accepted configuration, resolved identity, "
    "granted consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_challenges",
        statement=(
            "Scenario perturbations, envelope values and source authority are caller-declared; "
            "the engine does not traverse raw scientific content."
        ),
    ),
    Limitation(
        code="safe_failure_ceiling",
        statement=(
            "Missing, corrupt, unsupported, novel-state and reviewer-required cases abstain; "
            "abstention is not a negative biological finding."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "The result is a robustness/OOD challenge report only. It emits no proteotype, "
            "kinase activity, all-omics fusion, treatment recommendation or identity inference."
        ),
    ),
)
_PENALTIES: Final = {
    "missing_data": 0.05,
    "low_input": 0.10,
    "corruption": 0.18,
    "batch_shift": 0.12,
    "platform_shift": 0.14,
    "site_shift": 0.16,
    "artifact": 0.22,
    "novel_state": 0.30,
}


class M2506AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2506ReplayError(ValueError):
    """Raised when an immutable M25-06 result fails canonical replay."""

    def __init__(self, message: str = "M25-06 replay verification failed") -> None:
        super().__init__(message)


class M2506RobustnessEngine:
    """Execute and verify the bounded M25-06 challenge contract."""

    __slots__ = ()

    def challenge(self, request: object) -> ProteotypeRobustnessChallengeResult:
        preflight_m2506_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical.scenarios)
        can_evaluate = not any(
            item.expected_disposition is not ChallengeDisposition.WITHIN_ENVELOPE
            for item in canonical.scenarios
        )
        surface = _surface(canonical, request_digest) if can_evaluate else None
        status = RobustnessStatus.EVALUATED if surface is not None else RobustnessStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "proteotype_robustness_challenge",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2506_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + "0" * 64,
            "request": canonical,
            "status": status,
            "robustness_surface": surface,
            "safe_failure_report": (
                None if surface is not None else _safe_failure(canonical, findings)
            ),
            "findings": findings,
            "abstention_reason": (
                None
                if surface is not None
                else "Robustness challenge was not safely evaluable under the declared controls."
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(surface),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": any(
                item.expected_disposition is not ChallengeDisposition.WITHIN_ENVELOPE
                for item in canonical.scenarios
            ),
        }
        provisional = ProteotypeRobustnessChallengeResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeRobustnessChallengeResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self, result: ProteotypeRobustnessChallengeResult
    ) -> ProteotypeRobustnessChallengeResult:
        try:
            replayed = ProteotypeRobustnessChallengeResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise M2506ReplayError from error
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2506ReplayError
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2506ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2506ReplayError
        return replayed


def challenge_proteotype_robustness(
    request: object,
) -> ProteotypeRobustnessChallengeResult:
    """Public stateless M25-06 challenge entry point."""

    return M2506RobustnessEngine().challenge(request)


def preflight_m2506_authorization(candidate: object) -> None:
    """Reject denied controls before reading scenario declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, ChallengeProteotypeRobustnessRequest)
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
        raise M2506AuthorizationError from None
    if not authorized:
        raise M2506AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(scenarios: tuple[ChallengeScenario, ...]) -> tuple[ChallengeFinding, ...]:
    findings: list[ChallengeFinding] = []
    for scenario in scenarios:
        if scenario.expected_disposition is ChallengeDisposition.REVIEW_REQUIRED:
            findings.append(
                ChallengeFinding(
                    finding_id=f"finding.review.{scenario.scenario_id}",
                    code=ChallengeFindingCode.ENVELOPE_EXCEEDED,
                    message=f"Challenge {scenario.kind.value} requires reviewer adjudication.",
                    evidence=scenario.evidence,
                )
            )
        elif scenario.expected_disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED:
            findings.append(
                ChallengeFinding(
                    finding_id=f"finding.unsupported.{scenario.scenario_id}",
                    code=ChallengeFindingCode.UNSUPPORTED_PERTURBATION,
                    message=f"Challenge {scenario.kind.value} is unsupported and must abstain.",
                    evidence=scenario.evidence,
                )
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _surface(
    request: ChallengeProteotypeRobustnessRequest,
    request_digest: str,
) -> RobustnessSurface:
    observations = tuple(_observation(scenario) for scenario in request.scenarios)
    return RobustnessSurface(
        surface_id="m2506.surface." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        scenarios=request.scenarios,
        observations=observations,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _observation(scenario: ChallengeScenario) -> RobustnessObservation:
    penalty = _PENALTIES[scenario.kind.value]
    return RobustnessObservation(
        observation_id=f"observation.{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        metric="proteotype_support_retention",
        baseline_value=1.0,
        challenged_value=round(1.0 - penalty, 6),
        envelope_lower=0.0,
        envelope_upper=1.0,
        within_envelope=True,
        ood_score=round(min(0.99, penalty), 6),
        ood_band=OODBand.IN_DOMAIN,
        disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        evidence=scenario.evidence,
    )


def _safe_failure(
    request: ChallengeProteotypeRobustnessRequest,
    findings: tuple[ChallengeFinding, ...],
) -> SafeFailureReport:
    reason = (
        "Unsupported or reviewer-required challenge declarations prevent a safe robustness surface."
        if findings
        else "The declared challenge set is not safely evaluable."
    )
    return SafeFailureReport(
        report_id="m2506.safe-failure." + request.request_id,
        version=request.configuration.version,
        trigger=reason,
        action=(
            "Abstain and route the challenge set to human review; do not infer a negative finding."
        ),
        recovery_note="Provide supported, complete and reviewer-cleared challenge declarations.",
        evidence=_evidence(request),
    )


def _support(surface: RobustnessSurface | None) -> SupportDecision:
    if surface is None:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="robustness_challenge_abstained",
            rationale="At least one challenge is unsupported or requires reviewer adjudication.",
        )
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="robustness_challenge_completed",
        rationale="All eight caller-declared challenge kinds remained within the envelope.",
    )


def _uncertainty() -> UncertaintyProfile:
    def estimated(dimension: str, probability: float) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=f"Caller-declared M25-06 challenge sensitivity for {dimension}.",
        )

    return UncertaintyProfile(
        measurement=estimated("measurement", 0.10),
        sampling=estimated("sampling", 0.12),
        parameter=estimated("parameter", 0.08),
        model_form=estimated("model form", 0.16),
        identification=estimated("identification", 0.10),
        support=estimated("support", 0.18),
        transport=estimated("transport", 0.20),
        sensitivity_notes=(
            (
                "Scores summarize declared challenge sensitivity; they are not calibrated "
                "probabilities."
            ),
            "Novel-state and unsupported perturbations are routed to safe failure.",
        ),
    )


def _provenance(request: ChallengeProteotypeRobustnessRequest) -> ProvenanceRecord:
    references = request.context.references
    records = (
        _control(ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        _control(ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        _control(ControlRole.PROVENANCE, references.provenance),
        _control(ControlRole.CONSENT, references.consent),
        _control(ControlRole.QUALITY, references.quality),
        _control(ControlRole.SUPPORT, references.support),
        _control(ControlRole.INTENDED_USE, references.intended_use),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m2506.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2506_MODULE_ID,
        module_version=M2506_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=records,
    )


def _control(role: ControlRole, reference: object) -> ControlDecisionRecord:
    evidence = _member(reference, "evidence")
    decision_id = _member(reference, "decision_id")
    policy_version = _member(reference, "policy_version")
    state = _state_value(reference)
    subject_digest = (
        _member(reference, "binding_digest") if role is ControlRole.IDENTITY_LINEAGE else None
    )
    digest = _member(evidence, "digest")
    return ControlDecisionRecord(
        role=role,
        decision_id=str(decision_id),
        state=str(state),
        policy_version=str(policy_version),
        evidence_digest=str(digest),
        subject_digest=subject_digest if isinstance(subject_digest, str) else None,
    )


def _evidence(
    request: ChallengeProteotypeRobustnessRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M25-06 challenge input or control evidence.",
        )
        for artifact in request.source_artifacts
    )


__all__ = [
    "M2506AuthorizationError",
    "M2506ReplayError",
    "M2506RobustnessEngine",
    "challenge_proteotype_robustness",
    "preflight_m2506_authorization",
]
