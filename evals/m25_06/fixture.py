"""Frozen, caller-declared M25-06 challenge scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m25_06 import (
    M2506_M2504_INPUT_MEDIA_TYPE,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeProteotypeRobustnessRequest,
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

_DIGEST = "sha256:" + "a" * 64


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def controls() -> ContextReferences:
    evidence = artifact("control-evidence")
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=evidence,
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
    )


def build_request(
    *,
    disposition: ChallengeDisposition = ChallengeDisposition.WITHIN_ENVELOPE,
    request_id: str = "request.m2506.fixture",
) -> ChallengeProteotypeRobustnessRequest:
    upstream = artifact("m2504-transport", M2506_M2504_INPUT_MEDIA_TYPE)
    scenarios = tuple(
        ChallengeScenario(
            scenario_id=f"scenario.{kind.value}",
            kind=kind,
            severity=ChallengeSeverity.ROUTINE,
            perturbation=f"locked perturbation for {kind.value}",
            expected_disposition=(
                disposition
                if kind is ChallengeKind.NOVEL_STATE
                else ChallengeDisposition.WITHIN_ENVELOPE
            ),
            source_artifacts=(upstream,),
            evidence=(
                EvidenceReference(
                    reference=upstream,
                    role="evidence",
                    claim="Frozen caller-declared challenge evidence.",
                ),
            ),
        )
        for kind in ChallengeKind
    )
    configuration = RobustnessConfiguration(
        configuration_id="configuration.m2506.fixture",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.5,
        evidence=(
            EvidenceReference(
                reference=upstream,
                role="evidence",
                claim="Frozen challenge configuration.",
            ),
        ),
    )
    return ChallengeProteotypeRobustnessRequest(
        request_id=request_id,
        context=ExecutionContext(
            request_id=request_id,
            actor_id="actor.m2506.evaluator",
            occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
            references=controls(),
        ),
        upstream_result=upstream,
        scenarios=scenarios,
        configuration=configuration,
        source_artifacts=(upstream,),
    )


__all__ = ["artifact", "build_request", "controls"]
