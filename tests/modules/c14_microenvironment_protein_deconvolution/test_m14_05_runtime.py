"""Runtime and adversarial tests for provisional M14-05 replay."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m14_05 import (
    M1405_M1404_RESULT_MEDIA_TYPE,
    ChangePointStatus,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    GliomaTrajectoryProgram,
    LongitudinalEvidenceState,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    result_payload_digest,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_05_protein_subtype_evolution as m1405,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_05_protein_subtype_evolution.engine import (  # noqa: E501
    _initial_temporal_values,
    _TypedTerm,
)

_FOLLOW_UP_SEQUENCE = 2
_LEFT_CENSORED_BOUND = 0.6


def _typed_request() -> ModelProteinSubtypeLongitudinalEvolutionRequest:
    payload = _request().model_dump(mode="json")
    observations = list(payload["observations"])
    effects = (0.15, 0.8, 1.15)
    for observation, effect in zip(observations, effects, strict=True):
        observation.update(
            {
                "program": GliomaTrajectoryProgram.RTK_PI3K_AKT_MTOR.value,
                "evidence_state": LongitudinalEvidenceState.OBSERVED.value,
                "standardized_effect": effect,
                "standard_error": 0.12,
                "quality_weight": 0.9,
            }
        )
    payload["observations"] = observations
    configuration = dict(payload["policy"]["configuration"])
    configuration["bootstrap_replicates"] = 16
    payload["policy"]["configuration"] = configuration
    return ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate_json(
        json.dumps(payload), strict=True
    )


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    digest = (name.encode().hex() * 64)[:64]
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{digest}",
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M14-05 replay evidence.",
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    decision_artifact = _artifact("control")
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=decision_artifact,
        )

    return ExecutionContext(
        request_id="request.m1405",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=(
                    IdentityLineageState.RESOLVED
                    if accepted
                    else IdentityLineageState.CONFLICTED
                ),
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=decision_artifact,
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED if accepted else ConsentState.WITHHELD,
                policy_version="1.0.0",
                evidence=decision_artifact,
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended_use"),
        ),
    )


def _request(*, accepted: bool = True) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
    model_artifact = _artifact("model")
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration.m1405",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective="Caller-declared temporal replay",
        model_reference=model_artifact,
        evidence=(_evidence(model_artifact),),
    )
    policy = TrajectoryPolicy(
        dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TREATMENT_ERA),
        minimum_observations=2,
        configuration=configuration,
    )
    observations = tuple(
        TimePointObservation(
            observation_id=f"observation.{sequence}",
            sequence=sequence,
            observed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=sequence),
            territory=f"territory.{sequence}",
            treatment_era=(
                "era.baseline" if sequence < _FOLLOW_UP_SEQUENCE else "era.follow-up"
            ),
            feature_artifact=_artifact(f"feature_{sequence}"),
            evidence=(_evidence(_artifact(f"observation_{sequence}")),),
        )
        for sequence in range(3)
    )
    return ModelProteinSubtypeLongitudinalEvolutionRequest(
        request_id="request.m1405",
        context=_context(accepted=accepted),
        network_state_result=_artifact("network", M1405_M1404_RESULT_MEDIA_TYPE),
        policy=policy,
        observations=observations,
        source_artifacts=(_artifact("proteome"),),
    )


def test_constructs_ordered_metadata_trajectory_and_replays() -> None:
    service = m1405.M1405Service()
    result = service.construct(_request())

    assert result.status.value == "modeled"
    assert tuple(state.sequence for state in result.trajectory) == (0, 1, 2)
    assert len(result.change_points) == len(result.trajectory) - 1
    assert all(point.status is ChangePointStatus.NOT_EVALUABLE for point in result.change_points)
    assert result.temporal_order_verified is True
    assert result.future_leakage_checked is True
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert service.verify(result) == result


def test_typed_glioma_temporal_fit_emits_intervals_change_points_and_trace() -> None:
    service = m1405.M1405Service()
    request = _typed_request()
    result = service.construct(request)

    assert result.status.value == "modeled"
    assert all(state.standardized_state is not None for state in result.trajectory)
    assert all(
        state.lower_bound is not None and state.upper_bound is not None
        for state in result.trajectory
    )
    assert any(point.effect_delta is not None for point in result.change_points)
    assert any("trace_digest=" in diagnostic.message for diagnostic in result.diagnostics)
    assert result.uncertainty.measurement.state.value == "estimated"
    assert any(item.code == "typed_glioma_temporal_fit" for item in result.limitations)
    assert service.verify(result) == result


def test_typed_initialization_keeps_left_censored_limits_feasible() -> None:
    """Temporal starts use observed centers and feasible censor bounds."""

    grouped = {
        0: [
            _TypedTerm(
                sequence=0,
                program=GliomaTrajectoryProgram.RTK_PI3K_AKT_MTOR,
                state=LongitudinalEvidenceState.LEFT_CENSORED,
                value=-0.3,
                standard_error=0.2,
                quality_weight=1.0,
            )
        ],
        1: [
            _TypedTerm(
                sequence=1,
                program=GliomaTrajectoryProgram.RTK_PI3K_AKT_MTOR,
                state=LongitudinalEvidenceState.OBSERVED,
                value=1.2,
                standard_error=0.2,
                quality_weight=1.0,
            ),
            _TypedTerm(
                sequence=1,
                program=GliomaTrajectoryProgram.RTK_PI3K_AKT_MTOR,
                state=LongitudinalEvidenceState.LEFT_CENSORED,
                value=0.4,
                standard_error=0.2,
                quality_weight=1.0,
            ),
        ],
    }

    values = _initial_temporal_values(grouped, 2)
    assert values == [-0.3, 0.4]


def test_typed_temporal_missing_and_unsupported_evidence_abstain_safely() -> None:
    request = _typed_request().model_dump(mode="json")
    request["observations"][0].update(
        {
            "program": GliomaTrajectoryProgram.RTK_PI3K_AKT_MTOR.value,
            "evidence_state": LongitudinalEvidenceState.MISSING.value,
            "standardized_effect": None,
            "standard_error": None,
            "quality_weight": 0.0,
        }
    )
    request["observations"][1].update(
        {
            "program": GliomaTrajectoryProgram.P53_CELL_CYCLE.value,
            "evidence_state": LongitudinalEvidenceState.UNSUPPORTED.value,
            "standardized_effect": None,
            "standard_error": None,
            "quality_weight": 0.0,
        }
    )
    request["observations"][2].update(
        {
            "program": GliomaTrajectoryProgram.IDH_HIF1A.value,
            "evidence_state": LongitudinalEvidenceState.MISSING.value,
            "standardized_effect": None,
            "standard_error": None,
            "quality_weight": 0.0,
        }
    )
    typed = ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate_json(
        json.dumps(request), strict=True
    )
    result = m1405.M1405Service().construct(typed)

    assert result.status.value == "abstained"
    assert not result.trajectory
    assert "no supported observations" in " ".join(
        diagnostic.message for diagnostic in result.diagnostics
    )


def test_typed_left_censored_effect_is_one_sided_and_replay_stable() -> None:
    payload = _typed_request().model_dump(mode="json")
    payload["observations"][1]["evidence_state"] = LongitudinalEvidenceState.LEFT_CENSORED.value
    payload["observations"][1]["standardized_effect"] = _LEFT_CENSORED_BOUND
    typed = ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate_json(
        json.dumps(payload), strict=True
    )
    service = m1405.M1405Service()
    result = service.construct(typed)

    assert result.status.value == "modeled"
    assert result.trajectory[1].standardized_state is not None
    assert result.trajectory[1].standardized_state >= _LEFT_CENSORED_BOUND
    assert service.verify(result) == result


def test_plugin_json_boundary_and_descriptor() -> None:
    request = _request()
    plugin = m1405.M1405Plugin(m1405.M1405Service())
    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)

    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-05"
    assert result.result_digest.startswith("sha256:")


def test_denied_controls_fail_closed_before_execution() -> None:
    with pytest.raises(m1405.M1405AuthorizationError):
        m1405.M1405Service().construct(_request(accepted=False))


def test_out_of_order_observations_are_rejected() -> None:
    values = _request().model_dump(mode="python")
    values["observations"] = tuple(reversed(values["observations"]))
    with pytest.raises(ValidationError, match="strictly ordered"):
        ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate(values, strict=True)


def test_tampered_result_fails_replay_verification() -> None:
    result = m1405.M1405EvolutionEngine().construct(_request())
    altered = result.model_copy(update={"human_review_required": False})
    altered = altered.model_copy(update={"result_digest": result_payload_digest(altered)})
    with pytest.raises(m1405.M1405ReplayVerificationError):
        m1405.M1405EvolutionEngine().verify(altered)


def test_mapping_service_validation_and_replay_without_execution() -> None:
    request = _request()
    service = m1405.M1405Service()
    result = service.construct(request.model_dump(mode="python"))

    assert service.validate_request(request) == request
    assert service.validate_request(request.model_dump(mode="python")) == request
    assert service.verify(result, replay=False) == result
    with pytest.raises(TypeError, match="strict request"):
        service.validate_request(object())


def test_authorization_and_request_boundaries_fail_closed() -> None:
    class ContextAccessError(RuntimeError):
        pass

    class ExplodingContext:
        @property
        def context(self) -> object:
            raise ContextAccessError

    class ContextWrapper:
        context = _request().context

    with pytest.raises(m1405.M1405AuthorizationError):
        m1405.M1405Service().construct(ExplodingContext())
    with pytest.raises(TypeError, match="strict request"):
        m1405.M1405Service().construct(ContextWrapper())


def test_plugin_object_validation_and_token_seal() -> None:
    request = _request()
    plugin = m1405.M1405Plugin(m1405.M1405Service())
    token = plugin.validate(request)
    result = plugin.run(token)

    assert plugin.verify(result) == result
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
