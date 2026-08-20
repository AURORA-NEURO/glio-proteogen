"""Adversarial request and robustness-surface closure coverage for M24-06."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from glio_proteogen.contracts.m24_06 import (
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    OODBand,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
)
from glio_proteogen.contracts.m24_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
        artifact_id=f"artifact.m2406.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2406:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name), role="evidence", claim="M24-06 caller evidence."
    )


def _context(request_id: str = "request.m2406.robustness") -> ExecutionContext:
    control = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2406.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=control,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2406.robustness",
        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2406.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2406.identity"),
                evidence=control,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2406.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=control,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M24-06 robustness fixture does not estimate uncertainty.",
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


def _configuration() -> RobustnessConfiguration:
    return RobustnessConfiguration(
        configuration_id="configuration.m2406.robustness",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.8,
        evidence=(_evidence("configuration"),),
    )


def _scenario() -> ChallengeScenario:
    return ChallengeScenario(
        scenario_id="scenario.m2406.site-shift",
        kind=ChallengeKind.SITE_SHIFT,
        severity=ChallengeSeverity.ROUTINE,
        perturbation="bounded site shift",
        expected_disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        source_artifacts=(_artifact("scenario-source"),),
        evidence=(_evidence("scenario"),),
    )


def _surface() -> RobustnessSurface:
    scenario = _scenario()
    return RobustnessSurface(
        surface_id="surface.m2406.robustness",
        version="1.0.0",
        scenarios=(scenario,),
        observations=(
            RobustnessObservation(
                observation_id="observation.m2406.site-shift",
                scenario_id=scenario.scenario_id,
                metric="site calibration",
                baseline_value=0.8,
                challenged_value=0.79,
                envelope_lower=0.7,
                envelope_upper=0.9,
                within_envelope=True,
                ood_score=0.1,
                ood_band=OODBand.IN_DOMAIN,
                disposition=ChallengeDisposition.WITHIN_ENVELOPE,
                evidence=(_evidence("observation"),),
            ),
        ),
        configuration=_configuration(),
        evidence=(_evidence("surface"),),
    )


def _request() -> ChallengeBiomarkerPanelRobustnessRequest:
    upstream = _artifact("upstream", "application/vnd.glio-proteogen.m24-05+json")
    return ChallengeBiomarkerPanelRobustnessRequest(
        request_id="request.m2406.robustness",
        context=_context(),
        upstream_result=upstream,
        scenarios=(_scenario(),),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("scenario-source")),
    )


def _result() -> BiomarkerPanelRobustnessChallengeResult:
    request = _request()
    payload: dict[str, Any] = {
        "output_type": "biomarker_panel_robustness_challenge",
        "result_id": "result.m2406.robustness",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": RobustnessStatus.EVALUATED,
        "robustness_surface": _surface(),
        "safe_failure_report": None,
        "findings": (),
        "abstention_reason": None,
        "parent_target": "biomarker panel",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m2406_robustness_supported",
            rationale="The locked robustness fixture is supported.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": ProvenanceRecord(
            activity_id="activity.m2406.robustness",
            actor_id=request.context.actor_id,
            module_id="GLIO-PROTEOGEN-M24-06",
            module_version="0.1.0-provisional",
            generated_at=request.context.occurred_at,
            input_digests=(
                request.upstream_result.digest,
                _artifact("scenario-source").digest,
            ),
            configuration_digest=_artifact("configuration").digest,
            consent_decision_id=request.context.references.consent.decision_id,
            consent_state=request.context.references.consent.state,
            consent_policy_version=request.context.references.consent.policy_version,
            consent_evidence_digest=request.context.references.consent.evidence.digest,
            control_decisions=tuple(
                ControlDecisionRecord(
                    role=role,
                    decision_id=f"decision.m2406.{role.value}",
                    state=(
                        IdentityLineageState.RESOLVED.value
                        if role is ControlRole.IDENTITY_LINEAGE
                        else (
                            ConsentState.GRANTED.value
                            if role is ControlRole.CONSENT
                            else UpstreamDecisionState.ACCEPTED.value
                        )
                    ),
                    policy_version="1.0.0",
                    evidence_digest=_artifact("control").digest,
                    subject_digest=(
                        sha256_digest("m2406.identity")
                        if role is ControlRole.IDENTITY_LINEAGE
                        else None
                    ),
                )
                for role in ControlRole
            ),
        ),
        "evidence": (_evidence("result"),),
        "limitations": (
            Limitation(code="m2406_provisional", statement="The M24-06 ABI is provisional."),
        ),
        "human_review_required": False,
    }
    constructed = BiomarkerPanelRobustnessChallengeResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(constructed)
    return BiomarkerPanelRobustnessChallengeResult.model_validate(payload)


def test_request_context_identity_is_closed() -> None:
    request = _request()
    changed = request.model_dump(mode="python")
    changed["context"] = _context("request.m2406.other")
    with pytest.raises(ValueError, match="context must bind"):
        ChallengeBiomarkerPanelRobustnessRequest.model_validate(changed)


def test_evaluated_result_rejects_self_rehashed_scenario_mutation() -> None:
    result = _result()
    assert result.robustness_surface is not None
    forged_scenario = result.robustness_surface.scenarios[0].model_copy(
        update={"perturbation": "forged site shift"}
    )
    forged_surface = result.robustness_surface.model_copy(
        update={"scenarios": (forged_scenario, *result.robustness_surface.scenarios[1:])}
    )
    forged = result.model_copy(update={"robustness_surface": forged_surface})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request challenges"):
        BiomarkerPanelRobustnessChallengeResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )
