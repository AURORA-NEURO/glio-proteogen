"""Contract, runtime, adapter, and adversarial coverage for M15-03."""

# The matrix intentionally uses hostile wire inputs and literal protocol states.
# ruff: noqa: E501, ARG005, PLR2004, PT007, TC003, TRY003

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from evals.m15_03.run import _artifact, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_03_mechanistic_feature_constructor.engine as engine_module
from glio_proteogen.adapters.m1503 import app, m1503_app
from glio_proteogen.contracts.m15_03 import (
    M1503_OUTPUT_MEDIA_TYPE,
    ComplexActivityMechanisticFeatureResult,
    FeatureConstructorConfiguration,
    FeatureFindingCode,
    FeatureKind,
    FeatureSupportStatus,
    MechanisticFeature,
    MechanisticFeatureObject,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m15_03.v1 import (
    _require_feature_parent,
    _require_feature_unit,
    _require_finite_value,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_03_mechanistic_feature_constructor import (
    M1503AuthorizationError,
    M1503FeatureConstructorEngine,
    M1503Plugin,
    M1503ReplayVerificationError,
    M1503Service,
    ValidatedM1503Request,
    construct_complex_activity_mechanistic_features,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "feature",
        "feature-object",
        "configuration",
        "policy",
        "finding",
    }
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"]
        for item in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["outputMediaType"]
        == M1503_OUTPUT_MEDIA_TYPE
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_supported_feature_requires_evidence_and_units_are_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        _require_finite_value(float("nan"))
    with pytest.raises(ValueError, match="requires evidence"):
        MechanisticFeature(
            feature_id="feature.invalid",
            kind=FeatureKind.PATHWAY,
            label="Missing evidence",
            value="0.2",
            numeric_value=0.2,
            unit="activity",
            support_status=FeatureSupportStatus.SUPPORTED,
            source_artifacts=(_artifact("feature.invalid"),),
        )
    with pytest.raises(ValueError, match="finite"):
        MechanisticFeature(
            feature_id="feature.nan",
            kind=FeatureKind.PATHWAY,
            label="Non-finite",
            value="nan",
            numeric_value=float("nan"),
            unit="activity",
            support_status=FeatureSupportStatus.LIMITED,
            source_artifacts=(_artifact("feature.nan"),),
        )
    feature_payload = build_scenario_request().candidate_features[0].model_dump(mode="python")
    feature_payload["unit"] = ""
    feature_payload["support_status"] = FeatureSupportStatus.LIMITED
    invalid_unit = MechanisticFeature.model_construct(**feature_payload)
    with pytest.raises(ValueError, match="requires a unit"):
        _require_feature_unit(invalid_unit)


def test_request_feature_and_upstream_closures_reject_tampering() -> None:
    request = build_scenario_request()
    duplicate = request.model_dump(mode="python")
    duplicate["candidate_features"] = duplicate["candidate_features"] * 2
    with pytest.raises(ValueError, match="feature ids"):
        type(request).model_validate(duplicate, strict=True)
    forged = request.model_dump(mode="python")
    forged["longitudinal_recurrence_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M15-02"):
        type(request).model_validate(forged, strict=True)
    duplicate_object = MechanisticFeatureObject(
        feature_object_id="feature-object.invalid",
        version="1.0.0",
        features=(request.candidate_features[0],),
        material_assumptions=("test",),
        locked_reference=_artifact("locked"),
        evidence=request.candidate_features[0].evidence,
    ).model_copy(update={"features": request.candidate_features * 2})
    with pytest.raises(ValueError, match="feature ids"):
        MechanisticFeatureObject.model_validate(
            duplicate_object.model_dump(mode="python"), strict=True
        )
    feature_payload = request.candidate_features[0].model_dump(mode="python")
    feature_payload["parent_component"] = "wrong_parent"
    wrong_parent = MechanisticFeature.model_construct(**feature_payload)
    with pytest.raises(ValueError, match="complex_activity"):
        _require_feature_parent((wrong_parent,))
    second = request.candidate_features[0].model_copy(update={"feature_id": "feature.beta"})
    limited_policy = request.policy.model_copy(update={"maximum_features": 1})
    too_many = request.model_copy(
        update={
            "candidate_features": (request.candidate_features[0], second),
            "policy": limited_policy,
        }
    )
    with pytest.raises(ValueError, match="feature limit"):
        type(request).model_validate(too_many.model_dump(mode="python"), strict=True)


def test_uncertainty_is_explicit_on_supported_and_abstained_paths() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 2


def test_constructed_result_has_parent_provenance_and_invariants() -> None:
    result = M1503FeatureConstructorEngine().infer(build_scenario_request())
    assert result.feature_object is not None
    assert result.status.value == "constructed"
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M15-03"
    assert result.feature_object.topology_invariant_verified
    assert result.feature_object.perturbation_invariant_verified
    assert (
        construct_complex_activity_mechanistic_features(build_scenario_request()).feature_object
        is not None
    )


@pytest.mark.parametrize(
    "scenario_request",
    (
        build_scenario_request(unit="kelvin"),
        build_scenario_request(support_status=FeatureSupportStatus.CONFLICTED),
        build_scenario_request(method="unregistered_method"),
    ),
)
def test_unsafe_feature_states_abstain(scenario_request: object) -> None:
    result = M1503FeatureConstructorEngine().infer(scenario_request)
    assert result.feature_object is None
    assert result.human_review_required
    assert result.findings


def test_invariant_requirements_fail_closed() -> None:
    request = build_scenario_request()
    topology_configuration = request.policy.configuration.model_copy(
        update={"topology_invariants_required": False}
    )
    topology_request = request.model_copy(
        update={
            "policy": request.policy.model_copy(update={"configuration": topology_configuration})
        }
    )
    assert (
        engine_module._evaluate_features(topology_request)[1]
        is FeatureFindingCode.TOPOLOGY_INVARIANT_FAILED
    )
    perturbation_configuration = request.policy.configuration.model_copy(
        update={"perturbation_invariants_required": False}
    )
    perturbation_request = request.model_copy(
        update={
            "policy": request.policy.model_copy(
                update={"configuration": perturbation_configuration}
            )
        }
    )
    assert (
        engine_module._evaluate_features(perturbation_request)[1]
        is FeatureFindingCode.PERTURBATION_INVARIANT_FAILED
    )


def test_result_closure_rejects_forged_digest_id_evidence_and_review() -> None:
    engine = M1503FeatureConstructorEngine()
    result = engine.infer(build_scenario_request())
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ComplexActivityMechanisticFeatureResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="identifier"):
        ComplexActivityMechanisticFeatureResult.model_validate(payload, strict=True)
    abstained = engine.infer(build_scenario_request(unit="kelvin"))
    no_review = abstained.model_dump(mode="python")
    no_review["human_review_required"] = False
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ComplexActivityMechanisticFeatureResult.model_validate(no_review, strict=True)
    no_evidence = result.model_dump(mode="python")
    no_evidence["evidence"] = ()
    no_evidence["result_digest"] = result_payload_digest(no_evidence)
    with pytest.raises(ValueError, match="result evidence"):
        ComplexActivityMechanisticFeatureResult.model_validate(no_evidence, strict=True)
    invalid_constructed = result.model_dump(mode="python")
    invalid_constructed["feature_object"] = None
    invalid_constructed["result_digest"] = result_payload_digest(invalid_constructed)
    with pytest.raises(ValueError, match="constructed result"):
        ComplexActivityMechanisticFeatureResult.model_validate(invalid_constructed, strict=True)
    invalid_abstained = abstained.model_dump(mode="python")
    invalid_abstained["feature_object"] = (
        result.feature_object.model_dump(mode="python") if result.feature_object else None
    )
    invalid_abstained["result_digest"] = result_payload_digest(invalid_abstained)
    with pytest.raises(ValueError, match="abstained result"):
        ComplexActivityMechanisticFeatureResult.model_validate(invalid_abstained, strict=True)


def test_authorization_runs_before_typed_traversal() -> None:
    with pytest.raises(M1503AuthorizationError):
        M1503FeatureConstructorEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1503AuthorizationError):
        M1503FeatureConstructorEngine().infer(Exploding())


def test_replay_and_tamper_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1503FeatureConstructorEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1503ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    monkeypatch.setattr(engine_module, "result_payload_digest", lambda value: "sha256:" + "e" * 64)
    with pytest.raises(M1503ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    original_infer = engine_module.M1503FeatureConstructorEngine.infer
    monkeypatch.setattr(
        engine_module.M1503FeatureConstructorEngine,
        "infer",
        lambda self, request: original_infer(self, build_scenario_request(unit="kelvin")),
    )
    with pytest.raises(M1503ReplayVerificationError):
        engine.verify(result)


def test_plugin_token_boundary_and_service_parity() -> None:
    service = M1503Service()
    plugin = M1503Plugin(service)
    token = plugin.validate(build_scenario_request())
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(
        mode="json"
    )
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1503Request", build_scenario_request()))
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1503Request", []))
    json_token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert plugin.run(json_token).status.value == "constructed"
    assert plugin.verify(plugin.run(token)).status.value == "constructed"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-03"


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 7


def test_fastapi_interfaces_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m15-03/schema/request").status_code == 200
    assert client.get("/v1/m15-03/schema/unknown").status_code == 404
    request_payload = build_scenario_request().model_dump(mode="json")
    response = client.post("/v1/modules/M15-03/features", json=request_payload)
    assert response.status_code == 200
    result = response.json()
    verified = client.post("/v1/modules/M15-03/verify", json=result)
    assert verified.status_code == 200
    assert (
        client.post(
            "/v1/modules/M15-03/features",
            json=build_scenario_request(accepted=False).model_dump(mode="json"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/modules/M15-03/features", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M15-03/features",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    invalid_payload = dict(request_payload)
    invalid_payload.pop("candidate_features")
    assert client.post("/v1/modules/M15-03/features", json=invalid_payload).status_code == 422
    assert client.post("/v1/modules/M15-03/features", json={}).status_code == 403
    assert (
        client.post(
            "/v1/modules/M15-03/verify", content=b"{}", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/modules/M15-03/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_cli_construct_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1503_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1503_app, ["export-schema", "unknown"]).exit_code != 0
    first = runner.invoke(m1503_app, ["construct", str(request_path), "--output", str(output_path)])
    assert first.exit_code == 0
    assert runner.invoke(m1503_app, ["construct", str(request_path)]).exit_code == 0
    second = runner.invoke(
        m1503_app, ["construct", str(request_path), "--output", str(output_path)]
    )
    assert second.exit_code != 0
    verified = runner.invoke(m1503_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1503_app, ["verify", str(bad_result)]).exit_code != 0


def test_cli_duplicate_json_is_rejected(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "duplicate.json"
    request_path.write_text(
        '{"request_id":"request.m1503","request_id":"request.other"}', encoding="utf-8"
    )
    result = runner.invoke(m1503_app, ["construct", str(request_path)])
    assert result.exit_code != 0


def test_canonical_json_is_stable_and_configuration_is_typed() -> None:
    request = build_scenario_request()
    assert canonical_json_bytes(request) == canonical_json_bytes(request.model_copy())
    assert isinstance(request.policy.configuration, FeatureConstructorConfiguration)
