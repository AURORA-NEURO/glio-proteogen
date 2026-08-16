"""Adversarial closure for provisional M21-06 contract and replay semantics."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m21_06 import (
    M2106_M2105_INPUT_MEDIA_TYPE,
    M2106_MODULE_ID,
    ChallengeComplexActivityRobustnessRequest,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    ComplexActivityRobustnessChallengeResult,
    OODBand,
    RobustnessConfiguration,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared robustness challenge evidence.",
    )


def _context(request_id: str = "challenge-request-1") -> ExecutionContext:
    artifact = _artifact("control-evidence")
    accepted = UpstreamDecisionReference(
        decision_id="accepted-control",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    identity = IdentityLineageReference(
        decision_id="resolved-identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest="sha256:" + "b" * 64,
        evidence=artifact,
    )
    consent = ConsentReference(
        decision_id="granted-consent",
        state=ConsentState.GRANTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="challenge-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=identity,
            provenance=accepted,
            consent=consent,
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> RobustnessConfiguration:
    return RobustnessConfiguration(
        configuration_id="robustness-config-1",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.8,
        evidence=(_evidence("configuration-evidence"),),
    )


def _scenarios() -> tuple[ChallengeScenario, ...]:
    dispositions = {
        ChallengeKind.MISSING_DATA: ChallengeDisposition.ABSTAIN_UNSUPPORTED,
        ChallengeKind.LOW_INPUT: ChallengeDisposition.WITHIN_ENVELOPE,
        ChallengeKind.CORRUPTION: ChallengeDisposition.REVIEW_REQUIRED,
        ChallengeKind.BATCH_SHIFT: ChallengeDisposition.REVIEW_REQUIRED,
        ChallengeKind.PLATFORM_SHIFT: ChallengeDisposition.REVIEW_REQUIRED,
        ChallengeKind.SITE_SHIFT: ChallengeDisposition.REVIEW_REQUIRED,
        ChallengeKind.ARTIFACT: ChallengeDisposition.ABSTAIN_UNSUPPORTED,
        ChallengeKind.NOVEL_STATE: ChallengeDisposition.ABSTAIN_UNSUPPORTED,
    }
    return tuple(
        ChallengeScenario(
            scenario_id=f"scenario-{kind.value}",
            kind=kind,
            severity=ChallengeSeverity.MATERIAL,
            perturbation=f"declared-{kind.value}-perturbation",
            expected_disposition=dispositions[kind],
            source_artifacts=(_artifact(f"source-{kind.value}"),),
            evidence=(_evidence(f"scenario-{kind.value}-evidence"),),
        )
        for kind in ChallengeKind
    )


def _request() -> ChallengeComplexActivityRobustnessRequest:
    upstream = _artifact("m2105-estimator-result", M2106_M2105_INPUT_MEDIA_TYPE)
    return ChallengeComplexActivityRobustnessRequest(
        request_id="challenge-request-1",
        context=_context(),
        upstream_result=upstream,
        scenarios=_scenarios(),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("challenge-material")),
    )


def _surface(request: ChallengeComplexActivityRobustnessRequest) -> RobustnessSurface:
    observations = []
    for index, scenario in enumerate(request.scenarios):
        unsupported = scenario.expected_disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED
        within = scenario.expected_disposition is ChallengeDisposition.WITHIN_ENVELOPE
        observations.append(
            RobustnessObservation(
                observation_id=f"observation-{index}",
                scenario_id=scenario.scenario_id,
                metric="challenge_score",
                baseline_value=0.8,
                challenged_value=0.7 if within else 0.2,
                envelope_lower=0.0,
                envelope_upper=1.0,
                within_envelope=within,
                ood_score=0.95 if unsupported else (0.1 if within else 0.75),
                ood_band=OODBand.OUT_OF_DOMAIN
                if unsupported
                else (OODBand.IN_DOMAIN if within else OODBand.BORDERLINE),
                disposition=scenario.expected_disposition,
                evidence=(_evidence(f"observation-{index}-evidence"),),
            )
        )
    return RobustnessSurface(
        surface_id="surface-1",
        version="1.0.0",
        scenarios=request.scenarios,
        observations=tuple(observations),
        configuration=request.configuration,
        evidence=(_evidence("surface-evidence"),),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="No calibrated robustness uncertainty is claimed by this provisional contract.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _provenance(request: ChallengeComplexActivityRobustnessRequest) -> ProvenanceRecord:
    artifact = _artifact("control-evidence")
    decisions = []
    for role in ControlRole:
        state = (
            "resolved"
            if role is ControlRole.IDENTITY_LINEAGE
            else "granted"
            if role is ControlRole.CONSENT
            else "accepted"
        )
        decisions.append(
            ControlDecisionRecord(
                role=role,
                decision_id=f"decision-{role.value}",
                state=state,
                policy_version="1.0.0",
                evidence_digest=artifact.digest,
                subject_digest=("sha256:" + "b" * 64)
                if role is ControlRole.IDENTITY_LINEAGE
                else None,
            )
        )
    return ProvenanceRecord(
        activity_id="activity-1",
        actor_id=request.context.actor_id,
        module_id=M2106_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
        input_digests=(request.upstream_result.digest,),
        configuration_digest=_artifact("configuration").digest,
        consent_decision_id="granted-consent",
        consent_state=ConsentState.GRANTED,
        consent_policy_version="1.0.0",
        consent_evidence_digest=artifact.digest,
        control_decisions=tuple(decisions),
    )


def _result(
    request: ChallengeComplexActivityRobustnessRequest,
) -> ComplexActivityRobustnessChallengeResult:
    surface = _surface(request)
    payload = {
        "output_type": "complex_activity_robustness_challenge",
        "result_id": result_identifier(request),
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "request": request,
        "status": RobustnessStatus.EVALUATED,
        "robustness_surface": surface,
        "safe_failure_report": None,
        "findings": (),
        "abstention_reason": None,
        "parent_target": "complex activity",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported_surface",
            rationale="All eight locked challenge kinds are represented.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": (),
        "limitations": (
            Limitation(
                code="provisional_no_primary_error_claim",
                statement="This surface does not estimate primary scientific error.",
            ),
        ),
        "human_review_required": True,
    }
    candidate = ComplexActivityRobustnessChallengeResult.model_construct(
        **payload,
        result_digest="sha256:" + "0" * 64,
    )
    return ComplexActivityRobustnessChallengeResult(
        **payload,
        result_digest=result_payload_digest(candidate),
    )


def test_request_requires_all_challenge_kinds_and_upstream_source() -> None:
    request = _request()
    assert {scenario.kind for scenario in request.scenarios} == set(ChallengeKind)
    missing_upstream = request.model_dump(mode="python")
    missing_upstream["source_artifacts"] = (_artifact("other-material"),)
    with pytest.raises(ValidationError, match="include the M21-05 result"):
        ChallengeComplexActivityRobustnessRequest(**missing_upstream)


def test_surface_rejects_unknown_or_mismatched_observation_closure() -> None:
    request = _request()
    surface = _surface(request).model_dump(mode="python")
    surface["observations"] = surface["observations"][:-1]
    with pytest.raises(ValidationError, match="one observation for every scenario"):
        RobustnessSurface(**surface)

    surface = _surface(request).model_dump(mode="python")
    surface["observations"][0]["scenario_id"] = "unknown-scenario"
    with pytest.raises(ValidationError, match="unknown scenario"):
        RobustnessSurface(**surface)


def test_unsupported_observation_cannot_claim_supported_in_envelope() -> None:
    request = _request()
    surface = _surface(request).model_dump(mode="python")
    surface["observations"][0]["within_envelope"] = True
    surface["observations"][0]["ood_band"] = OODBand.IN_DOMAIN
    with pytest.raises(ValidationError, match="unsupported observations"):
        RobustnessSurface(**surface)


def test_result_identity_provenance_and_replay_are_closed() -> None:
    request = _request()
    result = _result(request)
    assert result.result_id == result_identifier(request)
    assert result.request_digest == canonical_request_digest(request)
    assert result.result_digest == result_payload_digest(result)

    tampered = result.model_dump(mode="python")
    tampered["result_id"] = "m2106.result.tampered"
    with pytest.raises(ValidationError, match="deterministically bound"):
        ComplexActivityRobustnessChallengeResult(**tampered)

    tampered = result.model_dump(mode="python")
    tampered["provenance"]["input_digests"] = ("sha256:" + "c" * 64,)
    with pytest.raises(ValidationError, match="upstream result digest"):
        ComplexActivityRobustnessChallengeResult(**tampered)


def test_evaluated_result_cannot_drop_surface_or_change_configuration() -> None:
    request = _request()
    result = _result(request)
    tampered = result.model_dump(mode="python")
    tampered["robustness_surface"] = None
    with pytest.raises(ValidationError, match="supported robustness surface"):
        ComplexActivityRobustnessChallengeResult(**tampered)

    tampered = result.model_dump(mode="python")
    tampered["robustness_surface"]["configuration"]["ood_threshold"] = 0.2
    with pytest.raises(ValidationError, match="configuration must equal"):
        ComplexActivityRobustnessChallengeResult(**tampered)


def test_strict_models_reject_extra_fields_and_wrong_upstream_media() -> None:
    scenario = _scenarios()[0].model_dump(mode="python")
    scenario["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        ChallengeScenario(**scenario)

    request = _request().model_dump(mode="python")
    request["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="provisional M21-05"):
        ChallengeComplexActivityRobustnessRequest(**request)


def test_abstention_requires_safe_failure_and_safe_support_status() -> None:
    request = _request()
    base = _result(request).model_dump(mode="python")
    base["status"] = RobustnessStatus.ABSTAINED
    base["robustness_surface"] = None
    base["abstention_reason"] = "Novel state is outside the declared support envelope."
    base["support_decision"] = SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="unsupported_novel_state",
        rationale="The provisional contract does not evaluate novel states.",
    )
    base["safe_failure_report"] = SafeFailureReport(
        report_id="safe-failure-1",
        version="1.0.0",
        trigger="novel state",
        action="abstain",
        recovery_note="Supply a reviewed supported challenge declaration.",
        evidence=(_evidence("safe-failure-evidence"),),
    )
    base.pop("result_digest")
    candidate = ComplexActivityRobustnessChallengeResult.model_construct(
        **base,
        result_digest="sha256:" + "0" * 64,
    )
    base["result_digest"] = result_payload_digest(candidate)
    abstained = ComplexActivityRobustnessChallengeResult(**base)
    assert abstained.status is RobustnessStatus.ABSTAINED
    assert abstained.safe_failure_report is not None
