from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m25_06 import (
    M2506_CONTRACT_VERSION,
    M2506_M2505_INPUT_MEDIA_TYPE,
    M2506_MODULE_ID,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeProteotypeRobustnessRequest,
    ChallengeScenario,
    ChallengeSeverity,
    OODBand,
    ProteotypeRobustnessChallengeResult,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
)
from glio_proteogen.contracts.m25_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_DIGEST = "sha256:" + ("a" * 64)
_VERSION = "1.0.0"
_ZERO_DIGEST = "sha256:" + ("0" * 64)


def _artifact(artifact_id: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=_VERSION,
        digest=_DIGEST,
        media_type=media_type,
    )


def _context(request_id: str, evidence: ArtifactReference) -> ExecutionContext:
    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=_VERSION,
            evidence=evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2506.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=_VERSION,
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="consent",
                state=ConsentState.GRANTED,
                policy_version=_VERSION,
                evidence=evidence,
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _evidence(artifact: ArtifactReference) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M25-06 robustness evidence.",
        ),
    )


def _request() -> ChallengeProteotypeRobustnessRequest:
    upstream = _artifact("m2505-result", M2506_M2505_INPUT_MEDIA_TYPE)
    scenario = ChallengeScenario(
        scenario_id="m2506.scenario.missing-data",
        kind=ChallengeKind.MISSING_DATA,
        severity=ChallengeSeverity.ROUTINE,
        perturbation="remove one caller-declared input",
        expected_disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        source_artifacts=(upstream,),
        evidence=_evidence(upstream),
    )
    configuration = RobustnessConfiguration(
        configuration_id="m2506.configuration.locked",
        version=_VERSION,
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.5,
        evidence=_evidence(upstream),
    )
    return ChallengeProteotypeRobustnessRequest(
        request_id="m2506.request.robustness",
        context=_context("m2506.request.robustness", upstream),
        upstream_result=upstream,
        scenarios=(scenario,),
        configuration=configuration,
        source_artifacts=(upstream,),
    )


def _result(request: ChallengeProteotypeRobustnessRequest) -> ProteotypeRobustnessChallengeResult:
    evidence = _evidence(request.upstream_result)
    observation = RobustnessObservation(
        observation_id="m2506.observation.missing-data",
        scenario_id=request.scenarios[0].scenario_id,
        metric="operational_score",
        baseline_value=1.0,
        challenged_value=0.9,
        envelope_lower=0.0,
        envelope_upper=1.0,
        within_envelope=True,
        ood_score=0.1,
        ood_band=OODBand.IN_DOMAIN,
        disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        evidence=evidence,
    )
    surface = RobustnessSurface(
        surface_id="m2506.surface.robustness",
        version=M2506_CONTRACT_VERSION,
        scenarios=request.scenarios,
        observations=(observation,),
        configuration=request.configuration,
        evidence=evidence,
    )
    controls = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=f"m2506.decision.{role.value}",
            state=(
                IdentityLineageState.RESOLVED.value
                if role is ControlRole.IDENTITY_LINEAGE
                else ConsentState.GRANTED.value
                if role is ControlRole.CONSENT
                else UpstreamDecisionState.ACCEPTED.value
            ),
            policy_version=_VERSION,
            evidence_digest=_DIGEST,
            subject_digest=_DIGEST if role is ControlRole.IDENTITY_LINEAGE else None,
        )
        for role in ControlRole
    )
    provenance = ProvenanceRecord(
        activity_id="m2506.activity",
        actor_id=request.context.actor_id,
        module_id=M2506_MODULE_ID,
        module_version=M2506_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request.upstream_result.digest,),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=_VERSION,
        consent_evidence_digest=_DIGEST,
        control_decisions=controls,
    )
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M25-06 does not estimate biological uncertainty.",
    )
    uncertainty = UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
    )
    provisional = ProteotypeRobustnessChallengeResult.model_construct(
        result_id="m2506.result.robustness",
        result_version=M2506_CONTRACT_VERSION,
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=RobustnessStatus.EVALUATED,
        robustness_surface=surface,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="robustness_supported",
            rationale="Caller-declared challenge is structurally supported.",
        ),
        uncertainty=uncertainty,
        provenance=provenance,
        evidence=evidence,
        limitations=(
            Limitation(
                code="operational_only",
                statement="This result does not infer proteotype biology.",
            ),
        ),
    )
    return provisional.model_copy(update={"result_digest": result_payload_digest(provisional)})


def test_evaluated_result_rejects_self_rehashed_surface_mutations() -> None:
    request = _request()
    result = _result(request)
    assert (
        ProteotypeRobustnessChallengeResult.model_validate(
            result.model_dump(mode="python"), strict=True
        )
        == result
    )

    forged_scenario = request.scenarios[0].model_copy(
        update={"perturbation": "forged caller-declared perturbation"}
    )
    forged_surface = result.robustness_surface.model_copy(update={"scenarios": (forged_scenario,)})
    forged = result.model_copy(update={"robustness_surface": forged_surface})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request scenarios"):
        ProteotypeRobustnessChallengeResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )

    forged_surface = result.robustness_surface.model_copy(
        update={"configuration": request.configuration.model_copy(update={"ood_threshold": 0.9})}
    )
    forged = result.model_copy(update={"robustness_surface": forged_surface})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request configuration"):
        ProteotypeRobustnessChallengeResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )
