"""Frozen caller-declared M24-06 challenge request."""

from __future__ import annotations

from evals.m24_07.fixture import artifact, context
from glio_proteogen.contracts.m24_06 import (
    M2406_M2405_INPUT_MEDIA_TYPE,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    RobustnessConfiguration,
)
from glio_proteogen.kernel.models import ArtifactReference


def request() -> ChallengeBiomarkerPanelRobustnessRequest:
    scenarios = tuple(
        ChallengeScenario(
            scenario_id=f"m2406.scenario.{kind.value}",
            kind=kind,
            severity=ChallengeSeverity.ROUTINE,
            perturbation=f"locked {kind.value} perturbation",
            expected_disposition=ChallengeDisposition.WITHIN_ENVELOPE,
            source_artifacts=(artifact(kind.value[0]),),
        )
        for kind in ChallengeKind
    )
    return ChallengeBiomarkerPanelRobustnessRequest(
        request_id="m2406.eval.request",
        context=context(),
        upstream_result=ArtifactReference(
            artifact_id="m2405.eval.result",
            version="0.1.0-provisional",
            digest="sha256:" + "1" * 64,
            media_type=M2406_M2405_INPUT_MEDIA_TYPE,
        ),
        scenarios=scenarios,
        configuration=RobustnessConfiguration(
            configuration_id="m2406.eval.configuration",
            version="1.0.0",
            required_challenge_kinds=tuple(ChallengeKind),
            ood_threshold=0.95,
        ),
        source_artifacts=(artifact("s"),),
    )
