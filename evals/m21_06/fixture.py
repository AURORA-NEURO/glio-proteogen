"""Frozen caller-declared M21-06 robustness challenge fixtures."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m21_06 import (
    M2106_M2105_INPUT_MEDIA_TYPE,
    ChallengeComplexActivityRobustnessRequest,
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
        claim="Frozen M21-06 robustness challenge fixture evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    artifact = _artifact("m2106.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2106.accepted.control",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2106.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2106.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2106.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> RobustnessConfiguration:
    return RobustnessConfiguration(
        configuration_id="m2106.locked.configuration",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.8,
        evidence=(_evidence("m2106.configuration.evidence"),),
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
            scenario_id=f"m2106.scenario.{kind.value}",
            kind=kind,
            severity=ChallengeSeverity.MATERIAL,
            perturbation=f"declared-{kind.value}-perturbation",
            expected_disposition=dispositions[kind],
            source_artifacts=(_artifact(f"m2106.source.{kind.value}"),),
            evidence=(_evidence(f"m2106.scenario.{kind.value}.evidence"),),
        )
        for kind in ChallengeKind
    )


def build_request() -> ChallengeComplexActivityRobustnessRequest:
    """Return the frozen mixed-support challenge request."""

    upstream = _artifact("m2105.estimator.result", M2106_M2105_INPUT_MEDIA_TYPE)
    return ChallengeComplexActivityRobustnessRequest(
        request_id="m2106.fixture.request",
        context=_context("m2106.fixture.request"),
        upstream_result=upstream,
        scenarios=_scenarios(),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("m2106.challenge.material")),
    )


def supported_request() -> ChallengeComplexActivityRobustnessRequest:
    """Return a supported-only request for deterministic surface evaluation."""

    request = build_request()
    scenarios = tuple(
        scenario.model_copy(
            update={
                "expected_disposition": (
                    ChallengeDisposition.WITHIN_ENVELOPE
                    if scenario.kind is ChallengeKind.LOW_INPUT
                    else ChallengeDisposition.REVIEW_REQUIRED
                )
            }
        )
        for scenario in request.scenarios
    )
    return request.model_copy(update={"scenarios": scenarios})


__all__ = ["build_request", "supported_request"]
