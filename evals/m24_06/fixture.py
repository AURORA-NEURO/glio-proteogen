"""Frozen caller-declared fixtures for the provisional M24-06 evaluator."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m24_06 import (
    M2406_M2405_INPUT_MEDIA_TYPE,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    RobustnessConfiguration,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

CHALLENGE_KINDS = tuple(ChallengeKind)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared M24-06 robustness challenge evidence.",
    )


def _context(request_id: str = "m2406.fixture.request") -> ExecutionContext:
    evidence = _artifact("m2406.fixture.control")
    accepted = UpstreamDecisionReference(
        decision_id="m2406.fixture.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2406.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2406.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2406.fixture.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> RobustnessConfiguration:
    return RobustnessConfiguration(
        configuration_id="m2406.fixture.configuration",
        version="1.0.0",
        required_challenge_kinds=CHALLENGE_KINDS,
        ood_threshold=0.8,
        evidence=(_evidence("m2406.fixture.configuration.evidence"),),
    )


def _scenario(kind: ChallengeKind, disposition: ChallengeDisposition) -> ChallengeScenario:
    return ChallengeScenario(
        scenario_id=f"m2406.fixture.scenario.{kind.value}",
        kind=kind,
        severity=(
            ChallengeSeverity.ROUTINE
            if disposition is ChallengeDisposition.WITHIN_ENVELOPE
            else ChallengeSeverity.CRITICAL
        ),
        perturbation=f"caller-declared {kind.value} challenge",
        expected_disposition=disposition,
        source_artifacts=(_artifact(f"m2406.fixture.{kind.value}"),),
        evidence=(_evidence(f"m2406.fixture.{kind.value}.evidence"),),
    )


def build_request() -> ChallengeBiomarkerPanelRobustnessRequest:
    upstream = _artifact("m2406.fixture.m2405-panel", M2406_M2405_INPUT_MEDIA_TYPE)
    scenarios = tuple(
        _scenario(kind, ChallengeDisposition.WITHIN_ENVELOPE) for kind in CHALLENGE_KINDS
    )
    return ChallengeBiomarkerPanelRobustnessRequest(
        request_id="m2406.fixture.request",
        context=_context(),
        upstream_result=upstream,
        scenarios=scenarios,
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("m2406.fixture.policy")),
    )


def denied_request() -> ChallengeBiomarkerPanelRobustnessRequest:
    request = build_request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


def review_request() -> ChallengeBiomarkerPanelRobustnessRequest:
    request = build_request()
    scenario = request.scenarios[0].model_copy(
        update={"expected_disposition": ChallengeDisposition.REVIEW_REQUIRED}
    )
    return request.model_copy(update={"scenarios": (scenario, *request.scenarios[1:])})


def unsupported_request() -> ChallengeBiomarkerPanelRobustnessRequest:
    request = build_request()
    scenario = request.scenarios[1].model_copy(
        update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
    )
    return request.model_copy(
        update={"scenarios": (*request.scenarios[:1], scenario, *request.scenarios[2:])}
    )


__all__ = ["build_request", "denied_request", "review_request", "unsupported_request"]
