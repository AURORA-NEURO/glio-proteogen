"""Adversarial closure for provisional M21-06 contract and replay semantics."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m21_06 import (
    M2106_M2105_INPUT_MEDIA_TYPE,
    M2106_MODULE_ID,
    ChallengeComplexActivityRobustnessRequest,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
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
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106Engine,
    M2106ReplayError,
    run_complex_activity_robustness_challenge,
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
    payload: Any = {
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


def _supported_request() -> ChallengeComplexActivityRobustnessRequest:
    payload = _request().model_dump(mode="python")
    for scenario in payload["scenarios"]:
        scenario["expected_disposition"] = (
            ChallengeDisposition.WITHIN_ENVELOPE
            if scenario["kind"] is ChallengeKind.LOW_INPUT
            else ChallengeDisposition.REVIEW_REQUIRED
        )
    return ChallengeComplexActivityRobustnessRequest(**payload)


def _self_rehashed(
    result: ComplexActivityRobustnessChallengeResult, updates: dict[str, Any]
) -> ComplexActivityRobustnessChallengeResult:
    forged = result.model_copy(update=updates)
    return type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
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


def test_observation_and_configuration_bounds_are_fail_closed() -> None:
    request = _request()
    observation = _surface(request).observations[0].model_dump(mode="python")
    observation["envelope_lower"] = 1.0
    observation["envelope_upper"] = 0.0
    with pytest.raises(ValidationError, match="bounds must be ordered"):
        RobustnessObservation(**observation)

    observation = _surface(request).observations[1].model_dump(mode="python")
    observation["disposition"] = ChallengeDisposition.WITHIN_ENVELOPE
    observation["within_envelope"] = False
    with pytest.raises(ValidationError, match="requires an in-envelope"):
        RobustnessObservation(**observation)

    configuration = _configuration().model_dump(mode="python")
    configuration["required_challenge_kinds"] = (
        ChallengeKind.MISSING_DATA,
        ChallengeKind.MISSING_DATA,
        *tuple(ChallengeKind)[2:],
    )
    with pytest.raises(ValidationError, match="must be unique"):
        RobustnessConfiguration(**configuration)


def test_surface_and_request_identity_sets_cannot_be_repeated_or_dropped() -> None:
    request = _request()
    surface = _surface(request).model_dump(mode="python")
    surface["scenarios"][1]["scenario_id"] = surface["scenarios"][0]["scenario_id"]
    with pytest.raises(ValidationError, match="scenario ids must be unique"):
        RobustnessSurface(**surface)

    surface = _surface(request).model_dump(mode="python")
    surface["observations"][1]["observation_id"] = surface["observations"][0]["observation_id"]
    with pytest.raises(ValidationError, match="observation ids must be unique"):
        RobustnessSurface(**surface)

    surface = _surface(request).model_dump(mode="python")
    surface["scenarios"][0]["expected_disposition"] = ChallengeDisposition.REVIEW_REQUIRED
    with pytest.raises(ValidationError, match="must match scenario expectation"):
        RobustnessSurface(**surface)

    supported_surface = _surface(request).model_dump(mode="python")
    supported_surface["scenarios"][0]["expected_disposition"] = ChallengeDisposition.WITHIN_ENVELOPE
    supported_surface["observations"][0]["disposition"] = ChallengeDisposition.WITHIN_ENVELOPE
    supported_surface["observations"][0]["within_envelope"] = True
    supported_surface["observations"][0]["ood_band"] = OODBand.OUT_OF_DOMAIN
    with pytest.raises(ValidationError, match="supported OOD bands"):
        RobustnessSurface(**supported_surface)

    payload = request.model_dump(mode="python")
    payload["context"]["request_id"] = "wrong-request-id"
    with pytest.raises(ValidationError, match="context request id"):
        ChallengeComplexActivityRobustnessRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["scenarios"][1]["scenario_id"] = payload["scenarios"][0]["scenario_id"]
    with pytest.raises(ValidationError, match="scenario ids must be unique"):
        ChallengeComplexActivityRobustnessRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["scenarios"] = payload["scenarios"][:-1]
    with pytest.raises(ValidationError, match="cover the locked"):
        ChallengeComplexActivityRobustnessRequest(**payload)

    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = payload["source_artifacts"] + (payload["source_artifacts"][0],)
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        ChallengeComplexActivityRobustnessRequest(**payload)


def test_result_digest_and_provenance_identity_are_closed() -> None:
    request = _request()
    result = _result(request)
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "a" * 64
    with pytest.raises(ValidationError, match="request digest"):
        ComplexActivityRobustnessChallengeResult(**payload)

    payload = result.model_dump(mode="python")
    payload["provenance"]["module_id"] = "GLIO-PROTEOGEN-M21-05"
    with pytest.raises(ValidationError, match="provenance module id"):
        ComplexActivityRobustnessChallengeResult(**payload)

    finding = ChallengeFinding(
        finding_id="duplicate-finding",
        code=ChallengeFindingCode.OOD_STATE,
        message="Duplicate finding for adversarial closure.",
    ).model_dump(mode="python")
    payload = result.model_dump(mode="python")
    payload["findings"] = (finding, finding)
    with pytest.raises(ValidationError, match="finding ids must be unique"):
        ComplexActivityRobustnessChallengeResult(**payload)


@pytest.mark.parametrize(
    "region",
    ["surface", "finding", "support", "provenance", "evidence", "limitations", "review"],
)
def test_self_rehashed_output_mutations_are_rejected_by_regeneration(region: str) -> None:
    result = run_complex_activity_robustness_challenge(_supported_request())
    assert result.robustness_surface is not None
    updates: dict[str, Any]
    if region == "surface":
        observation = result.robustness_surface.observations[0].model_copy(
            update={"challenged_value": 0.81}
        )
        updates = {
            "robustness_surface": result.robustness_surface.model_copy(
                update={"observations": (observation, *result.robustness_surface.observations[1:])}
            )
        }
    elif region == "finding":
        assert result.findings
        finding = result.findings[0].model_copy(update={"message": "forged OOD rationale"})
        updates = {"findings": (finding, *result.findings[1:])}
    elif region == "support":
        updates = {
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "forged support rationale"}
            )
        }
    elif region == "provenance":
        updates = {"provenance": result.provenance.model_copy(update={"actor_id": "forged-actor"})}
    elif region == "evidence":
        evidence = result.evidence[0].model_copy(update={"claim": "forged evidence claim"})
        updates = {"evidence": (evidence, *result.evidence[1:])}
    elif region == "limitations":
        limitation = result.limitations[0].model_copy(update={"statement": "forged limitation"})
        updates = {"limitations": (limitation, *result.limitations[1:])}
    else:
        updates = {"human_review_required": False}
    forged = _self_rehashed(result, updates)
    with pytest.raises(M2106ReplayError, match="replay verification failed"):
        M2106Engine().replay(forged)


def test_self_rehashed_request_is_rejected_after_full_regeneration() -> None:
    request = _supported_request()
    result = run_complex_activity_robustness_challenge(request)
    changed_request = request.model_copy(
        update={"configuration": request.configuration.model_copy(update={"ood_threshold": 0.7})}
    )
    forged = result.model_copy(
        update={
            "request": changed_request,
            "request_digest": canonical_request_digest(changed_request),
            "result_id": result_identifier(changed_request),
        }
    )
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )
    with pytest.raises(M2106ReplayError, match="replay verification failed"):
        M2106Engine().replay(forged)


def test_canonical_dict_projection_and_entrypoint_are_deterministic() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    result = run_complex_activity_robustness_challenge(request)
    assert result.result_id == result_identifier(request)
