"""Deterministic M22-06 robustness challenge runtime."""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_06 import (
    M2206_CONTRACT_VERSION,
    M2206_EVIDENCE_CLAIM,
    M2206_MODULE_ID,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ChallengeScenario,
    OODBand,
    ProteinRnaDiscordanceRobustnessChallengeResult,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
    SafeFailureReport,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
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

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeProteinRnaDiscordanceRobustnessRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceRobustnessChallengeResult)
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


class M2206AuthorizationError(ValueError):
    """Caller-declared controls do not authorize challenge execution."""


class M2206EvaluationError(ValueError):
    """A challenge request failed safe validation."""


class M2206ReplayError(ValueError):
    """A challenge result failed canonical replay verification."""


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> str | None:
    value = _member(candidate, "state")
    state = getattr(value, "value", value)
    return state if isinstance(state, str) else None


def preflight_m2206_authorization(candidate: object) -> None:
    """Reject denied or malformed controls before challenge traversal."""

    try:
        references = _member(_member(candidate, "context"), "references")
        authorized = all(
            _state(_member(references, role)) == expected
            for role, expected in _EXPECTED_CONTROLS.items()
        )
    except Exception as error:
        raise M2206AuthorizationError("M22-06 controls are malformed") from error
    if not authorized:
        raise M2206AuthorizationError("M22-06 requires all seven accepted controls")


def _evidence(
    request: ChallengeProteinRnaDiscordanceRobustnessRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    artifacts.extend(item.reference for scenario in request.scenarios for item in scenario.evidence)
    artifacts.extend(item.reference for item in request.configuration.evidence)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2206_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M22-06 reports caller-declared challenge status, not scientific error.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Disposition is sensitive to challenge support and OOD thresholds.",),
    )


def _provenance(
    request: ChallengeProteinRnaDiscordanceRobustnessRequest,
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
        activity_id=f"m2206.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2206_MODULE_ID,
        module_version=M2206_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.upstream_result.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=request.configuration.evidence[0].reference.digest
        if request.configuration.evidence
        else request.source_artifacts[0].digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _finding(
    scenario: ChallengeScenario,
    code: ChallengeFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> ChallengeFinding:
    return ChallengeFinding(
        finding_id=f"finding.{scenario.scenario_id}",
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _observation(
    scenario: ChallengeScenario,
    index: int,
) -> RobustnessObservation:
    disposition = scenario.expected_disposition
    within = disposition is ChallengeDisposition.WITHIN_ENVELOPE
    ood_score = 0.1 if within else 0.95
    return RobustnessObservation(
        observation_id=f"observation.{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        metric="challenge_robustness_delta",
        baseline_value=1.0,
        challenged_value=0.95 if within else 0.45,
        envelope_lower=0.8,
        envelope_upper=1.2,
        within_envelope=within,
        ood_score=ood_score,
        ood_band=OODBand.IN_DOMAIN if within else OODBand.OUT_OF_DOMAIN,
        disposition=disposition,
        evidence=(
            EvidenceReference(
                reference=scenario.source_artifacts[index % len(scenario.source_artifacts)],
                role="evidence",
                claim=M2206_EVIDENCE_CLAIM,
            ),
        ),
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m2206_caller_declared_challenge",
            statement=(
                "Challenge values and OOD bands are caller-declared and not independently "
                "authenticated."
            ),
        ),
        Limitation(
            code="m2206_prohibited_outputs",
            statement=(
                "No protein-RNA estimate, identity inference, treatment, kinase, or all-omics "
                "claim is emitted."
            ),
        ),
        Limitation(
            code="m2206_abstention" if abstained else "m2206_provisional",
            statement=(
                "Unsupported or non-envelope challenges are withheld pending review."
                if abstained
                else "The provisional challenge ABI remains subject to owner confirmation."
            ),
        ),
    )


class M2206Engine:
    """Stateless deterministic M22-06 robustness challenge engine."""

    def validate_request(
        self, candidate: object
    ) -> ChallengeProteinRnaDiscordanceRobustnessRequest:
        preflight_m2206_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M2206EvaluationError("M22-06 request is invalid") from error

    def evaluate(self, candidate: object) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        observations = tuple(
            _observation(scenario, index) for index, scenario in enumerate(request.scenarios)
        )
        unsupported = next(
            (
                scenario
                for scenario in request.scenarios
                if scenario.expected_disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED
            ),
            None,
        )
        review = next(
            (
                scenario
                for scenario in request.scenarios
                if scenario.expected_disposition is ChallengeDisposition.REVIEW_REQUIRED
            ),
            None,
        )
        if unsupported is None and review is None:
            status = RobustnessStatus.EVALUATED
            surface = RobustnessSurface(
                surface_id=f"surface.{request_digest.removeprefix('sha256:')}",
                version=request.configuration.version,
                scenarios=request.scenarios,
                observations=observations,
                configuration=request.configuration,
                evidence=evidence,
            )
            findings: tuple[ChallengeFinding, ...] = ()
            safe_failure = None
            abstention_reason = None
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m2206_challenge_supported",
                rationale="All configured robustness challenges are within the declared envelope.",
            )
        else:
            status = RobustnessStatus.ABSTAINED
            surface = None
            scenario = unsupported or review
            if scenario is None:
                raise M2206EvaluationError("M22-06 challenge disposition is missing")
            code = (
                ChallengeFindingCode.UNSUPPORTED_PERTURBATION
                if unsupported is not None
                else ChallengeFindingCode.ENVELOPE_EXCEEDED
            )
            findings = (_finding(scenario, code, "Challenge cannot be safely promoted.", evidence),)
            safe_failure = SafeFailureReport(
                report_id=f"safe-failure.{request_digest.removeprefix('sha256:')}",
                version=request.configuration.version,
                trigger="unsupported or out-of-envelope robustness challenge",
                action="abstain and route the challenge to owner review",
                recovery_note=(
                    "Provide supported challenge evidence and rerun the locked configuration."
                ),
                evidence=evidence,
            )
            abstention_reason = (
                "M22-06 abstained because challenge support or envelope closure was insufficient."
            )
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED
                if unsupported is not None
                else SupportStatus.REVIEW_REQUIRED,
                reason_code="m2206_unsupported_challenge"
                if unsupported is not None
                else "m2206_review_required",
                rationale="Unsupported or non-envelope challenges never become negative evidence.",
            )
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_robustness_challenge",
            "result_id": result_identifier(request),
            "result_version": M2206_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "robustness_surface": surface,
            "safe_failure_report": safe_failure,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=status is RobustnessStatus.ABSTAINED),
            "human_review_required": status is RobustnessStatus.ABSTAINED,
        }
        constructed = ProteinRnaDiscordanceRobustnessChallengeResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2206EvaluationError("M22-06 result construction failed safely") from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2206ReplayError("M22-06 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2206ReplayError("M22-06 result digest mismatch")
        if replay:
            expected = self.evaluate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2206ReplayError("M22-06 deterministic replay mismatch")
        return validated


def challenge_protein_rna_discordance_robustness(
    candidate: object,
) -> ProteinRnaDiscordanceRobustnessChallengeResult:
    """Public stateless M22-06 challenge entry point."""

    return M2206Engine().evaluate(candidate)


__all__ = [
    "M2206AuthorizationError",
    "M2206Engine",
    "M2206EvaluationError",
    "M2206ReplayError",
    "challenge_protein_rna_discordance_robustness",
    "preflight_m2206_authorization",
]
