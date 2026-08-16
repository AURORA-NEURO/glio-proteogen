"""Direct validator edge closure for the provisional M25-06 contract."""

from __future__ import annotations

import pytest
from evals.m25_06.fixture import artifact, build_request

from glio_proteogen.contracts.m25_06 import (
    M2506_REQUIRED_CHALLENGE_KINDS,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeKind,
    OODBand,
    RobustnessObservation,
    RobustnessSurface,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import EvidenceReference
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    M2506RobustnessEngine,
)


def _observation(request: object, scenario_id: str) -> RobustnessObservation:
    scenario = request.scenarios[0]  # type: ignore[attr-defined]
    return RobustnessObservation(
        observation_id=f"observation.{scenario_id}",
        scenario_id=scenario_id,
        metric="metric",
        baseline_value=1.0,
        challenged_value=0.5,
        envelope_lower=0.0,
        envelope_upper=1.0,
        within_envelope=True,
        ood_score=0.1,
        ood_band=OODBand.IN_DOMAIN,
        disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        evidence=scenario.evidence,
    )


def _surface(
    request: object, scenarios: tuple[object, ...], observations: tuple[object, ...]
) -> RobustnessSurface:
    return RobustnessSurface.model_construct(
        surface_id="surface.edge",
        version="1.0.0",
        scenarios=scenarios,
        observations=observations,
        configuration=request.configuration,  # type: ignore[attr-defined]
        evidence=request.scenarios[0].evidence,  # type: ignore[attr-defined]
    )


def test_observation_bounds_and_disposition_edges() -> None:
    request = build_request()
    scenario = request.scenarios[0]
    common = {
        "observation_id": "observation.edge",
        "scenario_id": scenario.scenario_id,
        "metric": "metric",
        "baseline_value": 1.0,
        "challenged_value": 0.5,
        "ood_score": 0.1,
        "ood_band": OODBand.IN_DOMAIN,
        "evidence": scenario.evidence,
    }
    with pytest.raises(ValueError):
        RobustnessObservation(
            **common,
            envelope_lower=1.0,
            envelope_upper=0.0,
            within_envelope=False,
            disposition=ChallengeDisposition.REVIEW_REQUIRED,
        )
    with pytest.raises(ValueError):
        RobustnessObservation(
            **common,
            envelope_lower=0.0,
            envelope_upper=1.0,
            within_envelope=False,
            disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        )


def test_configuration_and_surface_closure_edges() -> None:
    request = build_request()
    config = request.configuration
    duplicate_config = config.model_construct(
        configuration_id=config.configuration_id,
        version=config.version,
        required_challenge_kinds=(ChallengeKind.MISSING_DATA,) * 8,
        ood_threshold=config.ood_threshold,
        unsupported_abstention_required=True,
        locked=True,
        evidence=config.evidence,
    )
    with pytest.raises(ValueError):
        duplicate_config.challenge_kinds_are_unique()
    incomplete_config = config.model_construct(
        configuration_id=config.configuration_id,
        version=config.version,
        required_challenge_kinds=tuple(ChallengeKind)[:-1],
        ood_threshold=config.ood_threshold,
        unsupported_abstention_required=True,
        locked=True,
        evidence=config.evidence,
    )
    with pytest.raises(ValueError):
        incomplete_config.challenge_kinds_are_unique()
    assert set(config.required_challenge_kinds) == M2506_REQUIRED_CHALLENGE_KINDS

    scenarios = request.scenarios
    observations = tuple(_observation(request, item.scenario_id) for item in scenarios)
    with pytest.raises(ValueError):
        _surface(request, (scenarios[0], scenarios[0]), (observations[0],)).surface_is_closed()
    with pytest.raises(ValueError):
        _surface(request, scenarios, (observations[0],)).surface_is_closed()
    with pytest.raises(ValueError):
        _surface(request, scenarios[:2], (observations[0], observations[0])).surface_is_closed()
    with pytest.raises(ValueError):
        _surface(request, (scenarios[0],), (observations[0],)).surface_is_closed()
    unknown = _observation(request, "scenario.unknown")
    with pytest.raises(ValueError):
        _surface(request, scenarios, (*observations[:-1], unknown)).surface_is_closed()


def test_request_source_and_context_closure_edges() -> None:
    request = build_request()
    with pytest.raises(ValueError):
        request.model_construct(
            request_id=request.request_id,
            context=request.context,
            upstream_result=request.upstream_result,
            scenarios=request.scenarios,
            configuration=request.configuration,
            source_artifacts=(request.upstream_result, request.upstream_result),
        ).request_is_bound()
    with pytest.raises(ValueError):
        request.model_construct(
            request_id=request.request_id,
            context=request.context,
            upstream_result=request.upstream_result,
            scenarios=(request.scenarios[0], request.scenarios[0]),
            configuration=request.configuration,
            source_artifacts=request.source_artifacts,
        ).request_is_bound()
    with pytest.raises(ValueError):
        request.model_construct(
            request_id=request.request_id,
            context=request.context,
            upstream_result=request.upstream_result,
            scenarios=(request.scenarios[0],),
            configuration=request.configuration,
            source_artifacts=request.source_artifacts,
        ).request_is_bound()
    other = artifact("other-source")
    with pytest.raises(ValueError):
        request.model_construct(
            request_id=request.request_id,
            context=request.context,
            upstream_result=request.upstream_result,
            scenarios=request.scenarios,
            configuration=request.configuration,
            source_artifacts=(other,),
        ).request_is_bound()
    mismatch_context = request.context.model_copy(update={"request_id": "other.request"})
    with pytest.raises(ValueError):
        request.model_construct(
            request_id=request.request_id,
            context=mismatch_context,
            upstream_result=request.upstream_result,
            scenarios=request.scenarios,
            configuration=request.configuration,
            source_artifacts=request.source_artifacts,
        ).request_is_bound()


def test_result_validator_closes_digest_provenance_and_findings() -> None:
    request = build_request()
    result = M2506RobustnessEngine().challenge(request)
    with pytest.raises(ValueError):
        result.model_construct(
            **{**result.model_dump(mode="python"), "request_digest": "sha256:" + "f" * 64}
        ).result_is_closed()

    mismatched_request = request.model_construct(
        request_id=request.request_id,
        context=request.context.model_copy(update={"request_id": "other.request"}),
        upstream_result=request.upstream_result,
        scenarios=request.scenarios,
        configuration=request.configuration,
        source_artifacts=request.source_artifacts,
    )
    context_mismatch = result.model_copy(
        update={
            "request": mismatched_request,
            "request_digest": canonical_request_digest(mismatched_request),
        }
    )
    context_mismatch = context_mismatch.model_copy(
        update={"result_digest": result_payload_digest(context_mismatch)}
    )
    with pytest.raises(ValueError):
        context_mismatch.result_is_closed()

    evaluated_without_surface = result.model_copy(update={"robustness_surface": None})
    evaluated_without_surface = evaluated_without_surface.model_copy(
        update={"result_digest": result_payload_digest(evaluated_without_surface)}
    )
    with pytest.raises(ValueError):
        evaluated_without_surface.result_is_closed()

    abstained = M2506RobustnessEngine().challenge(
        build_request(disposition=ChallengeDisposition.ABSTAIN_UNSUPPORTED)
    )
    abstained_with_surface = abstained.model_copy(
        update={
            "robustness_surface": result.robustness_surface,
            "result_digest": "sha256:" + "0" * 64,
        }
    )
    abstained_with_surface = abstained_with_surface.model_copy(
        update={"result_digest": result_payload_digest(abstained_with_surface)}
    )
    with pytest.raises(ValueError):
        abstained_with_surface.result_is_closed()

    wrong_provenance = result.model_copy(
        update={
            "provenance": result.provenance.model_copy(
                update={"module_id": "GLIO-PROTEOGEN-M25-05"}
            )
        }
    )
    wrong_provenance = wrong_provenance.model_copy(
        update={"result_digest": result_payload_digest(wrong_provenance)}
    )
    with pytest.raises(ValueError):
        wrong_provenance.result_is_closed()

    wrong_id = result.model_copy(update={"result_id": "result.wrong"})
    wrong_id = wrong_id.model_copy(update={"result_digest": result_payload_digest(wrong_id)})
    with pytest.raises(ValueError):
        wrong_id.result_is_closed()

    evidence = EvidenceReference(
        reference=artifact("finding-evidence"), role="evidence", claim="edge finding"
    )
    finding = ChallengeFinding(
        finding_id="finding.duplicate",
        code=ChallengeFindingCode.ENVELOPE_EXCEEDED,
        message="duplicate edge finding",
        evidence=(evidence,),
    )
    duplicate_findings = result.model_copy(update={"findings": (finding, finding)})
    duplicate_findings = duplicate_findings.model_copy(
        update={"result_digest": result_payload_digest(duplicate_findings)}
    )
    with pytest.raises(ValueError):
        duplicate_findings.result_is_closed()
