"""Deterministic caller-declared M21-06 robustness challenge runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_06 import (
    M2106_CONTRACT_VERSION,
    M2106_MODULE_ID,
    ChallengeComplexActivityRobustnessRequest,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeScenario,
    ComplexActivityRobustnessChallengeResult,
    OODBand,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeComplexActivityRobustnessRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M21-06 robustness challenges require accepted configuration, resolved identity, granted "
    "consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M21-05 estimator result and challenge artifacts are caller-declared; issuer "
            "authority and scientific source content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_robustness",
        statement=(
            "The runtime constructs a deterministic robustness surface from declared challenge "
            "metadata; it does not execute a biological model or estimate primary error."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation, "
            "identity or consent inference, and unsupported-to-negative conversion are outside "
            "this module."
        ),
    ),
)


class M2106AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize challenge execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2106ReplayError(ValueError):
    """Raised when a robustness result fails canonical replay verification."""


class M2106Engine:
    """Build and replay one deterministic metadata-only robustness surface."""

    __slots__ = ()

    def generate(self, request: object) -> ComplexActivityRobustnessChallengeResult:
        preflight_m2106_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        if _requires_abstention(canonical):
            payload = _abstained_payload(canonical, request_digest)
        else:
            surface = _surface(canonical)
            payload = {
                "output_type": "complex_activity_robustness_challenge",
                "result_id": result_identifier(canonical),
                "result_version": M2106_CONTRACT_VERSION,
                "request_digest": request_digest,
                "result_digest": "sha256:" + ("0" * 64),
                "request": canonical,
                "status": RobustnessStatus.EVALUATED,
                "robustness_surface": surface,
                "safe_failure_report": None,
                "findings": _findings(canonical),
                "abstention_reason": None,
                "parent_target": "complex activity",
                "emits_parent": False,
                "support_decision": _support(),
                "uncertainty": _uncertainty(),
                "provenance": _provenance(canonical, request_digest),
                "evidence": _evidence(canonical),
                "limitations": _LIMITATIONS,
                "human_review_required": any(
                    scenario.expected_disposition is ChallengeDisposition.REVIEW_REQUIRED
                    for scenario in canonical.scenarios
                ),
            }
        provisional = ComplexActivityRobustnessChallengeResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ComplexActivityRobustnessChallengeResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ComplexActivityRobustnessChallengeResult,
    ) -> ComplexActivityRobustnessChallengeResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2106ReplayError("M21-06 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2106ReplayError("M21-06 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2106ReplayError("M21-06 result payload digest mismatch")  # noqa: TRY003
        return ComplexActivityRobustnessChallengeResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def run_complex_activity_robustness_challenge(
    request: object,
) -> ComplexActivityRobustnessChallengeResult:
    """Public stateless M21-06 robustness challenge entry point."""

    return M2106Engine().generate(request)


def preflight_m2106_authorization(candidate: object) -> None:
    """Reject denied controls before reading challenge declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, ChallengeComplexActivityRobustnessRequest)
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
        raise M2106AuthorizationError from None
    if not authorized:
        raise M2106AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _requires_abstention(request: ChallengeComplexActivityRobustnessRequest) -> bool:
    return any(
        scenario.expected_disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED
        for scenario in request.scenarios
    )


def _surface(request: ChallengeComplexActivityRobustnessRequest) -> RobustnessSurface:
    observations = tuple(
        _observation(request, index, scenario) for index, scenario in enumerate(request.scenarios)
    )
    return RobustnessSurface(
        surface_id="m2106.surface." + canonical_request_digest(request).removeprefix("sha256:"),
        version=M2106_CONTRACT_VERSION,
        scenarios=request.scenarios,
        observations=observations,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _observation(
    request: ChallengeComplexActivityRobustnessRequest,
    index: int,
    scenario: ChallengeScenario,
) -> RobustnessObservation:
    within = scenario.expected_disposition is ChallengeDisposition.WITHIN_ENVELOPE
    return RobustnessObservation(
        observation_id=f"m2106.observation.{index}",
        scenario_id=scenario.scenario_id,
        metric="declared_robustness_score",
        baseline_value=1.0,
        challenged_value=0.9 if within else 0.6,
        envelope_lower=0.0,
        envelope_upper=1.0,
        within_envelope=within,
        ood_score=0.1 if within else 0.75,
        ood_band=OODBand.IN_DOMAIN if within else OODBand.BORDERLINE,
        disposition=scenario.expected_disposition,
        evidence=scenario.evidence or _evidence(request),
    )


def _abstained_payload(
    request: ChallengeComplexActivityRobustnessRequest,
    request_digest: str,
) -> dict[str, Any]:
    return {
        "output_type": "complex_activity_robustness_challenge",
        "result_id": result_identifier(request),
        "result_version": M2106_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": RobustnessStatus.ABSTAINED,
        "robustness_surface": None,
        "safe_failure_report": SafeFailureReport(
            report_id="m2106.safe-failure." + request_digest.removeprefix("sha256:"),
            version=M2106_CONTRACT_VERSION,
            trigger="unsupported or novel challenge declaration",
            action="abstain without converting unsupported evidence to a negative finding",
            recovery_note="Provide a reviewed supported challenge declaration before evaluation.",
            evidence=_evidence(request),
        ),
        "findings": (
            ChallengeFinding(
                finding_id="m2106.finding.unsupported",
                code=ChallengeFindingCode.UNSUPPORTED_PERTURBATION,
                message="At least one declared perturbation is outside the supported surface.",
                evidence=_evidence(request),
            ),
        ),
        "abstention_reason": (
            "At least one declared challenge is unsupported by the provisional ABI."
        ),
        "parent_target": "complex activity",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="unsupported_challenge",
            rationale=(
                "Unsupported perturbations are explicitly abstained and are not negative findings."
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": _LIMITATIONS,
        "human_review_required": True,
    }


def _findings(request: ChallengeComplexActivityRobustnessRequest) -> tuple[ChallengeFinding, ...]:
    return tuple(
        ChallengeFinding(
            finding_id="m2106.finding." + scenario.scenario_id,
            code=ChallengeFindingCode.OOD_STATE,
            message="Declared challenge requires review within the provisional support envelope.",
            evidence=scenario.evidence or _evidence(request),
        )
        for scenario in request.scenarios
        if scenario.expected_disposition is ChallengeDisposition.REVIEW_REQUIRED
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="deterministic_robustness_surface_completed",
        rationale=(
            "All eight caller-declared challenge kinds are represented by a deterministic "
            "metadata-only robustness surface."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M21-06 does not estimate {dimension} uncertainty from metadata-only inputs."
            ),
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
            "A declared OOD score is not a calibrated probability or primary-error estimate.",
        ),
    )


def _evidence(
    request: ChallengeComplexActivityRobustnessRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M21-06 robustness challenge artifact; issuer authority is not "
                "authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: ChallengeComplexActivityRobustnessRequest,
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
        activity_id="m2106.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2106_MODULE_ID,
        module_version=M2106_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2106AuthorizationError",
    "M2106Engine",
    "M2106ReplayError",
    "preflight_m2106_authorization",
    "run_complex_activity_robustness_challenge",
]
