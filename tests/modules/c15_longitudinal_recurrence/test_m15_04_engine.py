"""M15-04 runtime, replay, authorization, and safety tests."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict, cast

import pytest

from glio_proteogen.contracts.m15_04 import (
    M1504_GLIOMA_MODEL_FAMILY,
    M1504_M1501_RESULT_MEDIA_TYPE,
    GliomaMechanismProgram,
    InferComplexActivityMechanismRequest,
    MechanismEstimateKind,
    MechanismEvidenceState,
    MechanismInferenceConfiguration,
    MechanismInferenceStatus,
    MechanismObservation,
    MechanismRelation,
    MechanismRelationKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_04_network_state_mechanism_inference import (
    M1504AuthorizationError,
    M1504InferenceError,
    M1504MechanismInference,
    M1504ReplayVerificationError,
    infer_complex_activity_mechanism,
    preflight_mechanism_authorization,
)
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_04_network_state_mechanism_inference.engine import (
    _hash_normal,
    _hash_uniform,
    _huber_loss,
    _quantile,
    _sigmoid,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


class RequestKwargs(TypedDict, total=False):
    accepted: bool
    method: str
    hypothesis_media_type: str


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1504": label}),
        media_type=media_type,
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _request(
    *,
    accepted: bool = True,
    method: str = "structure_aware_proteoform_model",
    hypothesis_media_type: str = M1504_M1501_RESULT_MEDIA_TYPE,
) -> InferComplexActivityMechanismRequest:
    return InferComplexActivityMechanismRequest(
        request_id="request.m1504",
        context=ExecutionContext(
            request_id="request.m1504",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        hypothesis_registry_result=_artifact("hypothesis.registry", hypothesis_media_type),
        configuration=MechanismInferenceConfiguration(
            configuration_id="configuration.m1504",
            version="1.0.0",
            method=method,
            model_reference=_artifact("model"),
            calibration_reference=_artifact("calibration"),
        ),
        source_artifacts=(
            _artifact("proteome"),
            _artifact("transcript-protein-discordance"),
            _artifact("ptm"),
        ),
    )


def _typed_request() -> InferComplexActivityMechanismRequest:
    request = _request()
    return request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={
                    "model_family": M1504_GLIOMA_MODEL_FAMILY,
                    "bootstrap_replicates": 16,
                }
            ),
            "observations": (
                MechanismObservation(
                    observation_id="observation.egfr",
                    program=GliomaMechanismProgram.RTK_PI3K_AKT_MTOR,
                    standardized_effect=1.2,
                    standard_error=0.2,
                    quality_weight=0.95,
                ),
                MechanismObservation(
                    observation_id="observation.p53",
                    program=GliomaMechanismProgram.P53_CELL_CYCLE,
                    standardized_effect=-0.8,
                    standard_error=0.25,
                    quality_weight=0.9,
                ),
            ),
            "relations": (
                MechanismRelation(
                    relation_id="relation.egfr-proliferation",
                    source_program=GliomaMechanismProgram.RTK_PI3K_AKT_MTOR,
                    target_program=GliomaMechanismProgram.PROLIFERATION,
                    kind=MechanismRelationKind.ACTIVATES,
                    weight=0.8,
                ),
                MechanismRelation(
                    relation_id="relation.p53-proliferation",
                    source_program=GliomaMechanismProgram.P53_CELL_CYCLE,
                    target_program=GliomaMechanismProgram.PROLIFERATION,
                    kind=MechanismRelationKind.INHIBITS,
                    weight=0.75,
                ),
            ),
        }
    )


def test_posterior_inference_is_deterministic_and_replayable() -> None:
    engine = M1504MechanismInference()
    result = engine.infer(_request())
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[0].kind is MechanismEstimateKind.POSTERIOR
    assert result.estimates[0].counter_evidence[0].role == "counter_evidence"
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.uncertainty.measurement.probability == 0.9
    assert len(result.provenance.control_decisions) == 7
    assert engine.verify(result) == result


def test_state_inference_and_public_operation_are_supported() -> None:
    request = _request(method="state_space_proteoform_model")
    result = M1504MechanismInference().infer(request)
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[0].kind is MechanismEstimateKind.STATE
    assert result.estimates[0].state_value == "complex_activity_supported"
    assert infer_complex_activity_mechanism(request) == result


def test_typed_glioma_mechanism_graph_is_robust_and_replayable() -> None:
    engine = M1504MechanismInference()
    result = engine.infer(_typed_request())
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.typed_model
    assert result.solver_iterations is not None
    assert result.objective_trace_digest is not None
    assert {item.mechanism_id for item in result.estimates} == {
        "mechanism.RTK_PI3K_AKT_MTOR",
        "mechanism.P53_CELL_CYCLE",
    }
    assert all(item.lower_bound <= item.posterior_probability <= item.upper_bound for item in result.estimates)
    assert all(item.evidence_count == 1 for item in result.estimates)
    assert engine.verify(result) == result


def test_typed_request_is_input_order_invariant_and_missing_is_not_negative() -> None:
    request = _typed_request()
    reordered = request.model_copy(
        update={
            "observations": tuple(reversed(request.observations)),
            "relations": tuple(reversed(request.relations)),
        }
    )
    first = M1504MechanismInference().infer(request)
    second = M1504MechanismInference().infer(reordered)
    assert first.request_digest == second.request_digest
    assert first.estimates == second.estimates
    missing = request.model_copy(
        update={
            "observations": (
                request.observations[0].model_copy(
                    update={
                        "evidence_state": MechanismEvidenceState.MISSING,
                        "standardized_effect": None,
                        "standard_error": None,
                    }
                ),
                request.observations[1],
            )
        }
    )
    abstained = M1504MechanismInference().infer(missing)
    assert abstained.status is MechanismInferenceStatus.ABSTAINED
    assert abstained.human_review_required


def test_typed_censoring_coupling_and_numeric_helpers_are_deterministic() -> None:
    request = _typed_request()
    censored = request.model_copy(
        update={
            "observations": (
                request.observations[0],
                request.observations[1].model_copy(
                    update={"evidence_state": MechanismEvidenceState.LEFT_CENSORED}
                ),
                MechanismObservation(
                    observation_id="observation.proliferation",
                    program=GliomaMechanismProgram.PROLIFERATION,
                    standardized_effect=0.6,
                    standard_error=0.3,
                ),
            ),
            "relations": (
                *request.relations,
                MechanismRelation(
                    relation_id="relation.egfr-p53-coupling",
                    source_program=GliomaMechanismProgram.RTK_PI3K_AKT_MTOR,
                    target_program=GliomaMechanismProgram.P53_CELL_CYCLE,
                    kind=MechanismRelationKind.COUPLES,
                ),
            ),
        }
    )
    result = M1504MechanismInference().infer(censored)
    assert result.typed_model
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[1].evidence_count == 1
    assert _hash_uniform("m1504") == _hash_uniform("m1504")
    assert _hash_normal("m1504") == _hash_normal("m1504")
    assert _quantile((), 0.5) == 0.0
    assert 0.0 < _sigmoid(-2.0) < 0.5 < _sigmoid(2.0) < 1.0
    assert _huber_loss(3.0) > _huber_loss(1.0)


@pytest.mark.parametrize(
    "candidate",
    [
        object(),
        {"context": None},
        {"context": {"references": None}},
        {"context": {"references": {"approved_configuration": {"state": 1}}}},
    ],
)
def test_mapping_authorization_fails_closed(candidate: object) -> None:
    with pytest.raises(M1504AuthorizationError):
        preflight_mechanism_authorization(candidate)


def test_typed_contract_rejects_duplicate_or_unresolved_graph_ids() -> None:
    request = _typed_request()
    with pytest.raises(ValueError, match="observation ids"):
        InferComplexActivityMechanismRequest.model_validate(
            request.model_dump(mode="python")
            | {"observations": (*request.observations, request.observations[0])}
        )
    with pytest.raises(ValueError, match="Input should be"):
        InferComplexActivityMechanismRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "relations": (
                    *request.relations,
                    {
                        "relation_id": "relation.unresolved",
                        "source_program": "UNRESOLVED",
                        "target_program": GliomaMechanismProgram.PROLIFERATION.value,
                        "kind": MechanismRelationKind.ACTIVATES.value,
                    },
                ),
            }
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "unsupported_baseline"},
        {"method": "negative_control_gate"},
        {"method": "kinase_activity_model"},
        {"method": "ood_proteoform_model"},
    ],
)
def test_unsupported_negative_and_prohibited_cases_abstain(
    kwargs: RequestKwargs,
) -> None:
    result = M1504MechanismInference().infer(_request(**kwargs))
    assert result.status is MechanismInferenceStatus.ABSTAINED
    assert not result.estimates
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert result.abstention_reason


def test_authorization_and_request_validation_fail_closed() -> None:
    engine = M1504MechanismInference()
    with pytest.raises(M1504AuthorizationError):
        engine.infer(_request(accepted=False))
    with pytest.raises(M1504InferenceError):
        engine.infer(cast("object", _request().model_copy(update={"source_artifacts": ()})))
    invalid_payload = _request().model_dump(mode="python")
    invalid_payload["hypothesis_registry_result"] = _artifact("bad", "application/json")
    with pytest.raises(ValueError, match="provisional M15-01"):
        InferComplexActivityMechanismRequest.model_validate(invalid_payload)


def test_replay_tamper_duplicate_json_and_hostile_controls_are_rejected() -> None:
    engine = M1504MechanismInference()
    result = engine.infer(_request())
    with pytest.raises(M1504ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1504AuthorizationError):
        preflight_mechanism_authorization(object())
    with pytest.raises(ValueError, match="duplicate"):
        strict_json_loads('{"request_id":"a","request_id":"b"}')
    token_payload = canonical_json_bytes(_request())
    assert token_payload.startswith(b"{")
