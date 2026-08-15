"""Contract, runtime, replay, safety, and adapter tests for M12-05."""

# The adversarial matrix intentionally exercises fail-closed boundary behavior.
# ruff: noqa: E501, ARG005, PLR2004, PT018, TRY003

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import glio_proteogen.modules.c12_driver_to_protein_consequence.m12_05_longitudinal_evolution.engine as engine_module
from glio_proteogen.adapters.m1205 import app
from glio_proteogen.contracts.m12_05 import (
    M1205_M1204_RESULT_MEDIA_TYPE,
    M1205_MODULE_ID,
    BiomarkerPanelLongitudinalEvolutionResult,
    ChangePoint,
    ChangePointStatus,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelBiomarkerPanelLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    TrajectoryStatus,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m12_05.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_05_longitudinal_evolution import (
    M1205AuthorizationError,
    M1205LongitudinalEngine,
    M1205Plugin,
    M1205ReplayVerificationError,
    M1205Service,
    ValidatedM1205Request,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1205": label}),
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
    objective: str = "stable", *, accepted: bool = True
) -> ModelBiomarkerPanelLongitudinalEvolutionRequest:
    observations = tuple(
        TimePointObservation(
            observation_id=f"observation.{index}",
            sequence=index,
            observed_at=_WHEN + timedelta(days=index),
            territory="core" if index < 2 else "rim",
            treatment_era="pre" if index < 2 else "post",
            feature_artifact=_artifact(f"feature.{index}"),
            evidence=(
                EvidenceReference(
                    reference=_artifact(f"obs-evidence.{index}"),
                    role="evidence",
                    claim="Caller-declared observation evidence.",
                ),
            ),
        )
        for index in range(3)
    )
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration.m1205",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective=objective,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration.evidence"),
                role="evidence",
                claim="Locked temporal model manifest.",
            ),
        ),
    )
    return ModelBiomarkerPanelLongitudinalEvolutionRequest(
        request_id="request.m1205",
        context=ExecutionContext(
            request_id="request.m1205",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        network_state_result=_artifact("m1204-result", M1205_M1204_RESULT_MEDIA_TYPE),
        policy=TrajectoryPolicy(
            dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.STATE_TRANSITION),
            minimum_observations=2,
            configuration=configuration,
        ),
        observations=observations,
        source_artifacts=(_artifact("source"),),
    )


def test_supported_trajectory_is_typed_ordered_and_replayable() -> None:
    engine = M1205LongitudinalEngine()
    result = engine.infer(_request())
    assert result.status is TrajectoryStatus.MODELED
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == M1205_MODULE_ID
    assert tuple(state.sequence for state in result.trajectory) == (0, 1, 2)
    assert result.temporal_order_verified and result.future_leakage_checked
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


@pytest.mark.parametrize(
    "objective", ["alternating", "territory", "treatment_era", "time_course", "trajectory:stable"]
)
def test_closed_objectives_produce_deterministic_labels(objective: str) -> None:
    result = M1205LongitudinalEngine().infer(_request(objective))
    assert result.status is TrajectoryStatus.MODELED
    assert len(result.trajectory) == 3
    assert all(state.evidence for state in result.trajectory)


def test_change_point_is_explicit_and_replayable() -> None:
    result = M1205LongitudinalEngine().infer(_request("change_point:2:before:after"))
    assert result.status is TrajectoryStatus.MODELED
    assert len(result.change_points) == 1
    assert result.change_points[0].status is ChangePointStatus.DETECTED
    assert result.change_points[0].before_state_id != result.change_points[0].after_state_id


@pytest.mark.parametrize(
    "objective",
    [
        "abstain:review",
        "bayesian_graph:state",
        "change_point:0:before:after",
        "change_point:9:before:after",
    ],
)
def test_unknown_or_unsupported_objective_abstains_safely(objective: str) -> None:
    result = M1205LongitudinalEngine().infer(_request(objective))
    assert result.status is TrajectoryStatus.NOT_EVALUABLE
    assert result.trajectory == () and result.change_points == ()
    assert result.abstention_reason
    assert result.human_review_required
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_control_denial_and_hostile_candidate_fail_before_materialization() -> None:
    with pytest.raises(M1205AuthorizationError):
        M1205LongitudinalEngine().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse hostile payload")

    with pytest.raises(M1205AuthorizationError):
        M1205LongitudinalEngine().infer(Hostile())


def test_tampered_digest_is_rejected_and_replay_can_be_disabled() -> None:
    engine = M1205LongitudinalEngine()
    result = engine.infer(_request())
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    with pytest.raises(M1205ReplayVerificationError):
        engine.verify(tampered)
    monkeypatch = pytest.MonkeyPatch()
    original_infer = engine_module.M1205LongitudinalEngine.infer
    try:
        monkeypatch.setattr(
            engine_module.M1205LongitudinalEngine,
            "infer",
            lambda self, request: original_infer(self, _request("territory")),
        )
        with pytest.raises(M1205ReplayVerificationError):
            engine.verify(result)
    finally:
        monkeypatch.undo()
    assert engine.verify(result, replay=False) == result

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            engine_module, "result_payload_digest", lambda value: sha256_digest("other")
        )
        with pytest.raises(M1205ReplayVerificationError):
            engine.verify(result)
    finally:
        monkeypatch.undo()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            engine_module.M1205LongitudinalEngine,
            "infer",
            lambda self, request: (_ for _ in ()).throw(ValueError("replay")),
        )
        with pytest.raises(M1205ReplayVerificationError):
            engine.verify(result)
    finally:
        monkeypatch.undo()


def test_plugin_requires_issued_parse_once_token_and_bytes_path() -> None:
    plugin = M1205Plugin(M1205Service())
    assert plugin.descriptor().module_id == M1205_MODULE_ID
    token = plugin.validate(_request())
    assert plugin.run(token).status is TrajectoryStatus.MODELED
    assert isinstance(token, ValidatedM1205Request)
    forged = ValidatedM1205Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status is TrajectoryStatus.MODELED
    with pytest.raises(StrictJsonError):
        plugin.validate('{"request_id":"x","request_id":"y"}')
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run({})  # type: ignore[arg-type]
    assert plugin.verify(plugin.run(token)).status is TrajectoryStatus.MODELED


def test_engine_internal_grammar_guards_are_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = _request().observations[0]
    with pytest.raises(engine_module.M1205InferenceError):
        engine_module._label_for("change_point", observation, 0)
    assert engine_module._objective_kind("change_point:not-a-number:before:after")[0] == ""
    engine = M1205LongitudinalEngine()
    monkeypatch.setattr(
        engine_module,
        "_objective_kind",
        lambda objective: ("change_point", None, "before", "after"),
    )
    with pytest.raises(engine_module.M1205InferenceError):
        engine.infer(_request())
    monkeypatch.setattr(
        engine_module, "_objective_kind", lambda objective: ("change_point", 2, None, None)
    )
    with pytest.raises(engine_module.M1205InferenceError):
        engine.infer(_request())


def test_request_and_result_contract_closure_rejects_forgery() -> None:  # noqa: PLR0915
    request = _request()
    forged_request = request.model_dump(mode="python")
    forged_request["network_state_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="provisional M12-04"):
        ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(forged_request, strict=True)
    result = M1205LongitudinalEngine().infer(request)

    def resigned(**updates: object) -> dict[str, object]:
        payload = result.model_dump(mode="python")
        payload.update(updates)
        payload["result_digest"] = result_payload_digest(payload)
        return payload

    with pytest.raises(ValueError, match="result identifier"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(
            resigned(result_id="result.bad"), strict=True
        )
    with pytest.raises(ValueError, match="request digest"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(
            resigned(request_digest=sha256_digest("request-tampered")), strict=True
        )
    with pytest.raises(ValueError, match="every result"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(resigned(evidence=()), strict=True)
    duplicated = result.model_dump(mode="python")
    duplicated["trajectory"] = duplicated["trajectory"] + duplicated["trajectory"][:1]
    duplicated["result_digest"] = result_payload_digest(duplicated)
    with pytest.raises(ValueError, match="state identifiers"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(duplicated, strict=True)
    bad_order = result.model_dump(mode="python")
    bad_order["trajectory"] = tuple(reversed(bad_order["trajectory"]))
    bad_order["result_digest"] = result_payload_digest(bad_order)
    with pytest.raises(ValueError, match="trajectory states"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(bad_order, strict=True)

    duplicate_change = M1205LongitudinalEngine().infer(_request("change_point:2:before:after"))
    change_payload = duplicate_change.model_dump(mode="python")
    change_payload["change_points"] = change_payload["change_points"] * 2
    change_payload["result_digest"] = result_payload_digest(change_payload)
    with pytest.raises(ValueError, match="change-point identifiers"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(change_payload, strict=True)
    duplicate_diagnostic = result.model_dump(mode="python")
    duplicate_diagnostic["diagnostics"] = duplicate_diagnostic["diagnostics"] * 2
    duplicate_diagnostic["result_digest"] = result_payload_digest(duplicate_diagnostic)
    with pytest.raises(ValueError, match="diagnostic identifiers"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(duplicate_diagnostic, strict=True)
    dangling_change = duplicate_change.model_dump(mode="python")
    dangling_change["change_points"][0]["before_state_id"] = "state.missing"
    dangling_change["result_digest"] = result_payload_digest(dangling_change)
    with pytest.raises(ValueError, match="reference trajectory"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(dangling_change, strict=True)
    extra_changes = duplicate_change.model_dump(mode="python")
    extra_changes["change_points"] = tuple(
        [item.model_dump(mode="python") for item in duplicate_change.change_points]
        + [
            {
                **duplicate_change.change_points[0].model_dump(mode="python"),
                "change_point_id": f"change-point.extra.{index}",
                "sequence": index + 2,
            }
            for index in range(3)
        ]
    )
    extra_changes["result_digest"] = result_payload_digest(extra_changes)
    with pytest.raises(ValueError, match="count exceeds"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(extra_changes, strict=True)
    unordered_changes = duplicate_change.model_dump(mode="python")
    unordered_changes["change_points"] = (
        duplicate_change.change_points[0]
        .model_copy(update={"change_point_id": "change-point.a", "sequence": 2})
        .model_dump(mode="python"),
        duplicate_change.change_points[0]
        .model_copy(update={"change_point_id": "change-point.b", "sequence": 1})
        .model_dump(mode="python"),
    )
    unordered_changes["result_digest"] = result_payload_digest(unordered_changes)
    with pytest.raises(ValueError, match="change points must be ordered"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(unordered_changes, strict=True)
    bad_modeled = result.model_dump(mode="python")
    bad_modeled["support_decision"]["status"] = SupportStatus.REVIEW_REQUIRED
    bad_modeled["result_digest"] = result_payload_digest(bad_modeled)
    with pytest.raises(ValueError, match="modeled result"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(bad_modeled, strict=True)
    bad_abstained = M1205LongitudinalEngine().infer(_request("unknown"))
    bad_abstained_payload = bad_abstained.model_dump(mode="python")
    bad_abstained_payload["trajectory"] = result.model_dump(mode="python")["trajectory"]
    bad_abstained_payload["result_digest"] = result_payload_digest(bad_abstained_payload)
    with pytest.raises(ValueError, match="abstained result"):
        BiomarkerPanelLongitudinalEvolutionResult.model_validate(bad_abstained_payload, strict=True)


def test_contract_temporal_and_shape_adversarial_matrix() -> None:
    request = _request()
    duplicate_dimensions = request.policy.model_copy(
        update={"dimensions": (TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TIME_COURSE)}
    )
    with pytest.raises(ValueError, match="dimensions must be unique"):
        TrajectoryPolicy.model_validate(duplicate_dimensions.model_dump(mode="python"), strict=True)
    duplicate_ids = request.model_copy(
        update={"observations": (request.observations[0], request.observations[0])}
    )
    with pytest.raises(ValueError, match="identifiers must be unique"):
        ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(
            duplicate_ids.model_dump(mode="python"), strict=True
        )
    duplicate_sequences = request.model_dump(mode="python")
    duplicate_sequences["observations"] = list(duplicate_sequences["observations"])
    duplicate_sequences["observations"][1]["sequence"] = 0
    duplicate_sequences["observations"] = tuple(duplicate_sequences["observations"])
    with pytest.raises(ValueError, match="ordered by sequence"):
        ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(
            duplicate_sequences, strict=True
        )
    duplicate_times = request.model_dump(mode="python")
    duplicate_times["observations"] = list(duplicate_times["observations"])
    duplicate_times["observations"][1]["observed_at"] = duplicate_times["observations"][0][
        "observed_at"
    ]
    duplicate_times["observations"] = tuple(duplicate_times["observations"])
    with pytest.raises(ValueError, match="ordered by observed_at"):
        ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(duplicate_times, strict=True)
    too_short = request.model_dump(mode="python")
    too_short["policy"]["minimum_observations"] = 4
    with pytest.raises(ValueError, match="minimum"):
        ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(too_short, strict=True)

    with pytest.raises(ValueError, match="detected change point"):
        ChangePoint(
            change_point_id="change-point.bad",
            sequence=1,
            status=ChangePointStatus.DETECTED,
            before_state_id="state.before",
            after_state_id="state.after",
            posterior_probability=0.9,
            rationale="A change was detected.",
        )
    with pytest.raises(ValueError, match="non-detected"):
        ChangePoint(
            change_point_id="change-point.bad",
            sequence=1,
            status=ChangePointStatus.NOT_DETECTED,
            before_state_id="state.before",
            rationale="No change point was detected.",
        )
    assert (
        ChangePoint(
            change_point_id="change-point.none",
            sequence=1,
            status=ChangePointStatus.NOT_DETECTED,
            rationale="No change point was detected.",
        ).status
        is ChangePointStatus.NOT_DETECTED
    )


def test_uncertainty_and_canonical_projection_are_explicit() -> None:
    assert expected_uncertainty(supported=True).measurement.probability == 0.9
    assert expected_uncertainty(supported=False).measurement.probability is None
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}


def test_service_api_success_error_and_verify_paths() -> None:
    client = TestClient(app)
    payload = _request().model_dump(mode="json")
    response = client.post("/v1/modules/M12-05/longitudinal", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    assert result_payload["status"] == "modeled"
    verified = client.post("/v1/modules/M12-05/verify", json=result_payload)
    assert verified.status_code == 200
    assert client.get("/v1/m12-05/schema/request").status_code == 200
    assert client.get("/v1/m12-05/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M12-05/longitudinal", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    denied = _request(accepted=False).model_dump(mode="json")
    assert client.post("/v1/modules/M12-05/longitudinal", json=denied).status_code == 403
    assert (
        client.post(
            "/v1/modules/M12-05/verify", content=b"{}", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )


def test_service_and_public_operation_paths() -> None:
    service = M1205Service()
    request = _request()
    assert service.validate_request(request) == request
    assert service.execute(request).status is TrajectoryStatus.MODELED
    assert service.verify(service.execute(request)).status is TrajectoryStatus.MODELED
    assert (
        engine_module.infer_biomarker_panel_longitudinal_evolution(request).status
        is TrajectoryStatus.MODELED
    )
