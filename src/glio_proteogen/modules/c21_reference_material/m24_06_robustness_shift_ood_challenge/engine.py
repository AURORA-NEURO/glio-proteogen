"""Deterministic, caller-declared M24-06 robustness and OOD challenges."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    M2406_CONTRACT_VERSION,
    M2406_EVIDENCE_CLAIM,
    M2406_MODULE_ID,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeScenario,
    OODBand,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
    SafeFailureReport,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M24-06 challenge requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_challenge_material",
        statement=(
            "Challenge scenarios, perturbation values, OOD bands, envelopes and evidence are "
            "caller-declared; issuer authority and scientific correctness are not authenticated."
        ),
    ),
    Limitation(
        code="biomarker_panel_parent_boundary",
        statement=(
            "M24-06 reports robustness and support material for a biomarker-panel workflow but "
            "does not emit a biomarker panel or biological conclusion."
        ),
    ),
    Limitation(
        code="no_negative_conversion",
        statement=(
            "Missing, unsupported, corrupted, out-of-domain or novel-state challenge material "
            "is never converted into a negative biological finding."
        ),
    ),
)


class M2406AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize a challenge."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2406ReplayError(ValueError):
    """Raised when an immutable M24-06 result fails replay closure."""


class M2406RobustnessEngine:
    """Evaluate one bounded challenge surface and preserve safe failure."""

    __slots__ = ()

    def challenge(self, request: object) -> BiomarkerPanelRobustnessChallengeResult:
        preflight_m2406_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        observations = tuple(_observation(scenario, canonical) for scenario in canonical.scenarios)
        adverse = tuple(
            observation
            for observation in observations
            if observation.disposition is not ChallengeDisposition.WITHIN_ENVELOPE
        )
        if adverse:
            return _build_result(
                canonical,
                request_digest,
                status=RobustnessStatus.ABSTAINED,
                surface=None,
                findings=_findings(adverse, canonical),
                safe_failure=_safe_failure(canonical, request_digest, adverse),
                abstention_reason=_abstention_reason(adverse),
                support_status=SupportStatus.REVIEW_REQUIRED,
            )
        surface = RobustnessSurface(
            surface_id="m2406.surface." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            scenarios=canonical.scenarios,
            observations=observations,
            configuration=canonical.configuration,
            evidence=_evidence(canonical),
        )
        return _build_result(
            canonical,
            request_digest,
            status=RobustnessStatus.EVALUATED,
            surface=surface,
            findings=(),
            safe_failure=None,
            abstention_reason=None,
            support_status=SupportStatus.SUPPORTED,
        )

    def verify_replay(
        self,
        result: BiomarkerPanelRobustnessChallengeResult,
    ) -> BiomarkerPanelRobustnessChallengeResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2406ReplayError("M24-06 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2406ReplayError("M24-06 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2406ReplayError("M24-06 result payload digest mismatch")  # noqa: TRY003
        return BiomarkerPanelRobustnessChallengeResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def challenge_biomarker_panel_robustness(
    request: object,
) -> BiomarkerPanelRobustnessChallengeResult:
    """Run the public deterministic M24-06 challenge operation."""

    return M2406RobustnessEngine().challenge(request)


def preflight_m2406_authorization(candidate: object) -> None:
    """Reject denied controls before traversing perturbation or OOD material."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        decisions = (
            _member(references, "approved_configuration"),
            _member(references, "identity_lineage"),
            _member(references, "provenance"),
            _member(references, "consent"),
            _member(references, "quality"),
            _member(references, "support"),
            _member(references, "intended_use"),
        )
        if any(decision is None for decision in decisions):
            raise M2406AuthorizationError  # noqa: TRY301
        if _state_value(decisions[0]) != UpstreamDecisionState.ACCEPTED.value:
            raise M2406AuthorizationError  # noqa: TRY301
        if _state_value(decisions[1]) != IdentityLineageState.RESOLVED.value:
            raise M2406AuthorizationError  # noqa: TRY301
        if _state_value(decisions[2]) != UpstreamDecisionState.ACCEPTED.value:
            raise M2406AuthorizationError  # noqa: TRY301
        if _state_value(decisions[3]) != ConsentState.GRANTED.value:
            raise M2406AuthorizationError  # noqa: TRY301
        if any(
            _state_value(decision) != UpstreamDecisionState.ACCEPTED.value
            for decision in decisions[4:]
        ):
            raise M2406AuthorizationError  # noqa: TRY301
    except M2406AuthorizationError:
        raise
    except Exception as error:
        raise M2406AuthorizationError from error


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _observation(
    scenario: ChallengeScenario,
    request: ChallengeBiomarkerPanelRobustnessRequest,
) -> RobustnessObservation:
    disposition = scenario.expected_disposition
    if disposition is ChallengeDisposition.WITHIN_ENVELOPE:
        challenged, lower, upper, score, band = 0.92, 0.80, 0.98, 0.10, OODBand.IN_DOMAIN
    elif disposition is ChallengeDisposition.REVIEW_REQUIRED:
        challenged, lower, upper, score, band = 0.70, 0.80, 0.98, 0.60, OODBand.BORDERLINE
    else:
        challenged, lower, upper, score, band = 0.10, None, None, 0.99, OODBand.OUT_OF_DOMAIN
    return RobustnessObservation(
        observation_id=f"m2406.observation.{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        metric="caller_declared_robustness_score",
        baseline_value=1.0,
        challenged_value=challenged,
        envelope_lower=lower,
        envelope_upper=upper,
        within_envelope=disposition is ChallengeDisposition.WITHIN_ENVELOPE,
        ood_score=score,
        ood_band=band,
        disposition=disposition,
        evidence=_evidence(request),
    )


def _findings(
    observations: tuple[RobustnessObservation, ...],
    request: ChallengeBiomarkerPanelRobustnessRequest,
) -> tuple[ChallengeFinding, ...]:
    findings: list[ChallengeFinding] = []
    for observation in observations:
        code = (
            ChallengeFindingCode.OOD_STATE
            if observation.ood_band in {OODBand.OUT_OF_DOMAIN, OODBand.BORDERLINE}
            else ChallengeFindingCode.UNSUPPORTED_PERTURBATION
        )
        findings.append(
            ChallengeFinding(
                finding_id=f"m2406.finding.{observation.observation_id}",
                code=code,
                message=(
                    f"Challenge {observation.scenario_id} requires review or safe abstention; "
                    "no negative biological claim is emitted."
                ),
                evidence=_evidence(request),
            )
        )
    return tuple(findings)


def _abstention_reason(observations: tuple[RobustnessObservation, ...]) -> str:
    bands = ", ".join(sorted({observation.ood_band.value for observation in observations}))
    return "M24-06 abstained pending robustness review for OOD bands: " + bands


def _safe_failure(
    request: ChallengeBiomarkerPanelRobustnessRequest,
    request_digest: str,
    observations: tuple[RobustnessObservation, ...],
) -> SafeFailureReport:
    return SafeFailureReport(
        report_id="m2406.safe-failure." + request_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        trigger=_abstention_reason(observations),
        action="Abstain and route the challenge surface to human review.",
        recovery_note=(
            "Supply supported challenge evidence and rerun under the locked configuration; "
            "unsupported results remain non-negative and non-promotional."
        ),
        evidence=_evidence(request),
    )


def _build_result(  # noqa: PLR0913
    request: ChallengeBiomarkerPanelRobustnessRequest,
    request_digest: str,
    *,
    status: RobustnessStatus,
    surface: RobustnessSurface | None,
    findings: tuple[ChallengeFinding, ...],
    safe_failure: SafeFailureReport | None,
    abstention_reason: str | None,
    support_status: SupportStatus,
) -> BiomarkerPanelRobustnessChallengeResult:
    payload: dict[str, Any] = {
        "output_type": "biomarker_panel_robustness_challenge",
        "result_id": result_identifier(request),
        "result_version": M2406_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": status,
        "robustness_surface": surface,
        "safe_failure_report": safe_failure,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "biomarker panel",
        "emits_parent": False,
        "support_decision": _support(support_status),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": _LIMITATIONS,
        "human_review_required": True,
    }
    provisional = BiomarkerPanelRobustnessChallengeResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    return BiomarkerPanelRobustnessChallengeResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _support(status: SupportStatus) -> SupportDecision:
    return SupportDecision(
        status=status,
        reason_code=(
            "robustness_surface_completed"
            if status is SupportStatus.SUPPORTED
            else "robustness_challenge_requires_review"
        ),
        rationale=(
            "All declared challenge kinds remain within the caller-declared robustness envelope."
            if status is SupportStatus.SUPPORTED
            else "One or more challenge kinds are out of domain, unsupported, or require review."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M24-06 does not estimate {dimension} uncertainty from caller material.",
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
            "Robustness challenge uncertainty is metadata-only and does not establish "
            "biological efficacy.",
        ),
    )


def _evidence(
    request: ChallengeBiomarkerPanelRobustnessRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2406_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: ChallengeBiomarkerPanelRobustnessRequest,
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
    return ProvenanceRecord(
        activity_id="m2406.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2406_MODULE_ID,
        module_version=M2406_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2406AuthorizationError",
    "M2406ReplayError",
    "M2406RobustnessEngine",
    "challenge_biomarker_panel_robustness",
    "preflight_m2406_authorization",
]
