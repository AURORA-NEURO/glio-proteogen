"""Adversarial and replay coverage for M15-05."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from glio_proteogen.contracts.m15_05 import (
    M1505_M1504_RESULT_MEDIA_TYPE,
    ChangePointStatus,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    GliomaEvolutionProgram,
    LongitudinalEvidenceState,
    ModelComplexActivityLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    TrajectoryStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_05_longitudinal_evolution.engine import (  # noqa: E501
    _initial_typed_values,
    _TypedTerm,
)

_OBSERVATION_COUNT = 2
_TYPED_OBSERVATION_COUNT = 4


def _digest(label: str) -> str:
    return sha256_digest({"m1505-test": label})


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1505.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="caller-declared M15-05 test evidence",
    )


def _context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m1505",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _observation(sequence: int, label: str) -> TimePointObservation:
    return TimePointObservation(
        observation_id=f"observation.{label}",
        sequence=sequence,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=sequence * 30),
        territory="caller_declared_territory",
        treatment_era="caller_declared_era",
        feature_artifact=_artifact(f"feature-{label}"),
        evidence=(_evidence(f"observation-{label}"),),
    )


def _request() -> ModelComplexActivityLongitudinalEvolutionRequest:
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration.m1505",
        version="1.0.0",
        model_family=EvolutionModelFamily.LATENT_CLASS_PROTEOTYPE,
        objective="caller-declared longitudinal trajectory replay",
        model_reference=_artifact("model-reference"),
        evidence=(_evidence("model-evidence"),),
    )
    policy = TrajectoryPolicy(
        dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TERRITORY),
        minimum_observations=2,
        configuration=configuration,
    )
    return ModelComplexActivityLongitudinalEvolutionRequest(
        request_id="request.m1505",
        context=_context(),
        network_state_result=ArtifactReference(
            artifact_id="upstream.m1504",
            version="0.1.0-provisional",
            digest=_digest("upstream"),
            media_type=M1505_M1504_RESULT_MEDIA_TYPE,
        ),
        policy=policy,
        observations=(_observation(0, "baseline"), _observation(1, "recurrence")),
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
    )


def _typed_request() -> ModelComplexActivityLongitudinalEvolutionRequest:
    request = _request()
    configuration = request.policy.configuration.model_copy(
        update={
            "model_family": EvolutionModelFamily.GLIOMA_TYPED_GRAPH,
            "bootstrap_replicates": 16,
        }
    )
    observations = tuple(
        _observation(sequence, label).model_copy(
            update={
                "program": program,
                "standardized_effect": effect,
                "standard_error": 0.2,
                "quality_weight": 0.9,
                "evidence_state": LongitudinalEvidenceState.OBSERVED,
            }
        )
        for sequence, label, program, effect in (
            (0, "baseline-rtk", GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR, 4.0),
            (1, "baseline-p53", GliomaEvolutionProgram.P53_CELL_CYCLE, -4.0),
            (2, "recurrence-rtk", GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR, 4.0),
            (3, "recurrence-p53", GliomaEvolutionProgram.P53_CELL_CYCLE, -4.0),
        )
    )
    return request.model_copy(
        update={
            "policy": request.policy.model_copy(update={"configuration": configuration}),
            "observations": observations,
        }
    )


def test_supported_replay_preserves_order_and_explicit_change_points() -> None:
    service = m1505.M1505Service()
    result = service.execute(_request())
    assert result.status is TrajectoryStatus.MODELED
    assert len(result.trajectory) == _OBSERVATION_COUNT
    assert result.change_points[0].status is ChangePointStatus.NOT_EVALUABLE
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.temporal_order_verified is True
    assert result.future_leakage_checked is True
    assert service.verify(result).result_digest == result.result_digest


def test_typed_glioma_temporal_graph_infers_intervals_and_change_points() -> None:
    service = m1505.M1505Service()
    result = service.execute(_typed_request())
    assert result.status is TrajectoryStatus.MODELED
    assert result.typed_model
    assert result.solver_iterations is not None
    assert result.objective_trace_digest is not None
    assert len(result.trajectory) == _TYPED_OBSERVATION_COUNT
    assert all(0.0 <= state.posterior_probability <= 1.0 for state in result.trajectory)
    assert any(item.status is ChangePointStatus.DETECTED for item in result.change_points)
    assert service.verify(result) == result


def test_typed_initialization_keeps_left_censored_limits_feasible() -> None:
    """Censor limits constrain the start but are never averaged as observations."""

    grouped = {
        (GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR, 0): [
            _TypedTerm(
                sequence=0,
                observation_id="censored",
                program=GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR,
                state=LongitudinalEvidenceState.LEFT_CENSORED,
                value=-0.3,
                standard_error=0.2,
                quality_weight=1.0,
            )
        ],
        (GliomaEvolutionProgram.P53_CELL_CYCLE, 0): [
            _TypedTerm(
                sequence=0,
                observation_id="mixed-observed",
                program=GliomaEvolutionProgram.P53_CELL_CYCLE,
                state=LongitudinalEvidenceState.OBSERVED,
                value=1.2,
                standard_error=0.2,
                quality_weight=1.0,
            ),
            _TypedTerm(
                sequence=0,
                observation_id="mixed-censored",
                program=GliomaEvolutionProgram.P53_CELL_CYCLE,
                state=LongitudinalEvidenceState.LEFT_CENSORED,
                value=0.4,
                standard_error=0.2,
                quality_weight=1.0,
            ),
        ],
    }

    values = _initial_typed_values(grouped, (0,))
    order = list(GliomaEvolutionProgram)
    left_censor_limit = -0.3
    mixed_censor_limit = 0.4
    assert values[order.index(GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR)][0] == left_censor_limit
    assert values[order.index(GliomaEvolutionProgram.P53_CELL_CYCLE)][0] == mixed_censor_limit


def test_typed_missing_evidence_abstains_without_negative_state() -> None:
    request = _typed_request()
    missing = request.observations[0].model_copy(
        update={
            "program": None,
            "standardized_effect": None,
            "standard_error": None,
            "evidence_state": LongitudinalEvidenceState.MISSING,
        }
    )
    result = m1505.M1505Service().execute(
        request.model_copy(update={"observations": (missing, *request.observations[1:])})
    )
    assert result.status is TrajectoryStatus.MODELED
    assert "indeterminate" in result.trajectory[0].label
    insufficient = request.model_copy(
        update={"observations": tuple(item.model_copy(update={
            "program": None,
            "standardized_effect": None,
            "standard_error": None,
            "evidence_state": LongitudinalEvidenceState.UNSUPPORTED,
        }) for item in request.observations)}
    )
    abstained = m1505.M1505Service().execute(insufficient)
    assert abstained.status is TrajectoryStatus.ABSTAINED
    assert abstained.human_review_required


def test_denied_control_fails_closed() -> None:
    request = _request()
    denied = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    with pytest.raises(m1505.M1505AuthorizationError):
        m1505.M1505Service().execute(request.model_copy(update={"context": denied}))


def test_temporal_and_upstream_boundaries_reject() -> None:
    request = _request()
    with pytest.raises(ValueError, match="strictly ordered"):
        m1505.M1505Service().construct(
            request.model_copy(update={"observations": tuple(reversed(request.observations))})
        )
    wrong_upstream = request.model_copy(
        update={
            "network_state_result": request.network_state_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValueError, match="M15-04"):
        m1505.M1505Service().construct(wrong_upstream)


def test_insufficient_history_is_rejected_by_request_contract() -> None:
    request = _request()
    with pytest.raises(ValueError, match="minimum"):
        m1505.M1505Service().construct(
            request.model_copy(
                update={"policy": request.policy.model_copy(update={"minimum_observations": 3})}
            )
        )


def test_tampered_result_fails_replay_verification() -> None:
    result = m1505.M1505Service().execute(_request())
    tampered = result.model_copy(update={"human_review_required": False})
    with pytest.raises(m1505.M1505ReplayVerificationError):
        m1505.M1505Service().verify(tampered)


def test_plugin_token_and_json_paths() -> None:
    plugin = m1505.M1505Plugin(m1505.M1505Service())
    validated = plugin.validate(_request().model_dump_json())
    result = plugin.run(validated)
    assert plugin.verify(result).result_id == result.result_id
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_mapping_service_and_plugin_descriptor_paths() -> None:
    request = _request()
    service = m1505.M1505Service()
    mapping = request.model_dump(mode="python")
    assert service.validate_request(mapping).request_id == request.request_id
    assert service.construct(mapping).status is TrajectoryStatus.MODELED
    result = service.execute(request)
    assert service.verify(result, replay=False).result_id == result.result_id
    assert service.construct(request).result_digest == result.result_digest
    plugin = m1505.M1505Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-05"
    with pytest.raises(TypeError, match="strict request"):
        service.validate_request(object())


def test_invalid_engine_candidate_and_authorization_shape_fail_closed() -> None:
    request = _request()

    class Candidate:
        context = request.context

    with pytest.raises(TypeError, match="strict request"):
        m1505.M1505EvolutionEngine().construct(Candidate())

    class Broken:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(m1505.M1505AuthorizationError):
        m1505.preflight_m1505_authorization(Broken())


def test_duplicate_evidence_is_canonicalized() -> None:
    original = _request()
    duplicate = original.source_artifacts[0]
    request = original.model_copy(update={"source_artifacts": (duplicate, duplicate)})
    result = m1505.M1505EvolutionEngine().construct(request)
    keys = [
        (
            item.reference.artifact_id,
            item.reference.version,
            item.reference.digest,
            item.reference.media_type,
        )
        for item in result.evidence
    ]
    assert len(keys) == len(set(keys))


def test_replay_mismatch_is_distinguished_from_digest_tamper() -> None:
    result = m1505.M1505Service().execute(_request())
    changed = result.model_copy(update={"human_review_required": False})
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(m1505.M1505ReplayVerificationError):
        m1505.M1505Service().verify(changed)
