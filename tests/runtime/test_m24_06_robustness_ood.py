"""Runtime, replay and safe-failure tests for provisional M24-06."""

from __future__ import annotations

import json

import pytest
from evals.m24_07.fixture import artifact, context

from glio_proteogen.contracts.m24_06 import (
    M2406_M2405_INPUT_MEDIA_TYPE,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    RobustnessConfiguration,
    RobustnessStatus,
)
from glio_proteogen.kernel.models import ArtifactReference, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_06_robustness_ood_challenge as m2406,
)

_CHALLENGE_KIND_COUNT = 8


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
        request_id="m2406.test.request",
        context=context(),
        upstream_result=ArtifactReference(
            artifact_id="m2405.test.result",
            version="0.1.0-provisional",
            digest="sha256:" + "1" * 64,
            media_type=M2406_M2405_INPUT_MEDIA_TYPE,
        ),
        scenarios=scenarios,
        configuration=RobustnessConfiguration(
            configuration_id="m2406.test.configuration",
            version="1.0.0",
            required_challenge_kinds=tuple(ChallengeKind),
            ood_threshold=0.95,
        ),
        source_artifacts=(artifact("s"),),
    )


def test_supported_challenge_surface_replays_deterministically() -> None:
    service = m2406.M2406Service()
    first = service.evaluate(request())
    second = service.evaluate(json.dumps(request().model_dump(mode="json"), sort_keys=True))
    assert first.status is RobustnessStatus.EVALUATED
    assert first.robustness_surface is not None
    assert len(first.robustness_surface.observations) == _CHALLENGE_KIND_COUNT
    assert first.result_digest == second.result_digest
    assert service.verify_replay(first).result_digest == first.result_digest


def test_unsupported_challenge_abstains_with_safe_failure() -> None:
    typed = request()
    scenario = typed.scenarios[0].model_copy(
        update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
    )
    changed = typed.model_copy(update={"scenarios": (scenario, *typed.scenarios[1:])})
    result = m2406.M2406Service().evaluate(changed)
    assert result.status is RobustnessStatus.ABSTAINED
    assert result.robustness_surface is None
    assert result.safe_failure_report is not None
    assert result.safe_failure_report.abstained is True
    assert result.findings


def test_replay_rejects_self_rehashed_safe_failure_and_denied_control() -> None:
    service = m2406.M2406Service()
    result = service.evaluate(request())
    assert result.robustness_surface is not None
    changed = result.robustness_surface.observations[0].model_copy(update={"ood_score": 0.2})
    surface = result.robustness_surface.model_copy(
        update={"observations": (changed, *result.robustness_surface.observations[1:])}
    )
    forged = result.model_copy(update={"robustness_surface": surface})
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result.result_digest}
    )
    with pytest.raises(m2406.M2406ReplayError):
        service.verify_replay(forged)
    denied_support = request().context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_context = request().context.model_copy(
        update={
            "references": request().context.references.model_copy(
                update={"support": denied_support}
            )
        }
    )
    with pytest.raises(m2406.AuthorizationError):
        service.evaluate(request().model_copy(update={"context": denied_context}))


def test_plugin_tokens_are_instance_bound_and_snapshot_bound() -> None:
    first = m2406.M2406Plugin(m2406.M2406Service())
    second = m2406.M2406Plugin(m2406.M2406Service())
    token = first.validate(m2406.RobustnessSubmission(request()))

    assert first.run(token).status is RobustnessStatus.EVALUATED
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)

    forged = m2406.ValidatedM2406Request(token.request, object())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(forged)

    mutated = first.validate(m2406.RobustnessSubmission(request()))
    object.__setattr__(mutated.request, "request_id", "m2406.forged.request")
    with pytest.raises(TypeError, match="validated request token"):
        first.run(mutated)

    replaced = first.validate(m2406.RobustnessSubmission(request()))
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(replaced)
