"""Runtime and adversarial tests for provisional M14-05 replay."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m14_05 import (
    M1405_M1404_RESULT_MEDIA_TYPE,
    ChangePointStatus,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
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
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_05_protein_subtype_evolution as m1405,
)

_FOLLOW_UP_SEQUENCE = 2


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
    with pytest.raises(m1405.M1405ReplayVerificationError):
        m1405.M1405EvolutionEngine().verify(altered)
