"""Contract, runtime, adapter, and adversarial coverage for M13-04."""

# The matrix intentionally uses literal protocol status codes and broad ValueError
# assertions at the contract boundary to exercise hostile wire inputs.
# ruff: noqa: E501, ARG005, PLR2004, PT011, PT007, TC003, TRY003

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from evals.m13_04.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c11_protein_native_subtype.m13_04_network_state_mechanism_inference.engine as engine_module
from glio_proteogen.adapters.m1304 import app, m1304_app
from glio_proteogen.contracts.m13_04 import (
    M1304_GLIOMA_MODEL_FAMILY,
    M1304_OUTPUT_MEDIA_TYPE,
    InferProteotypeMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismInferenceStatus,
    MechanismObservation,
    MechanismObservationState,
    MechanismRelation,
    MechanismRelationKind,
    ProteotypeMechanismInferenceResult,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m13_04.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c11_protein_native_subtype.m13_04_network_state_mechanism_inference import (
    M1304MechanismAuthorizationError,
    M1304MechanismEngine,
    M1304Plugin,
    M1304ReplayVerificationError,
    M1304Service,
    ValidatedM1304Request,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {"request", "output", "estimate", "configuration", "finding"}
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"]
        for item in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["outputMediaType"]
        == M1304_OUTPUT_MEDIA_TYPE
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_estimate_invariants_reject_invalid_posterior_and_state() -> None:
    counter = M1304MechanismEngine().infer(build_scenario_request()).estimates[0].counter_evidence
    with pytest.raises(ValueError):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Invalid",
            kind=MechanismEstimateKind.POSTERIOR,
            posterior_probability=0.1,
            lower_bound=0.2,
            upper_bound=0.3,
            assumptions=("assumption",),
            alternatives=("alternative",),
            counter_evidence=counter,
        )
    with pytest.raises(ValueError):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Invalid",
            kind=MechanismEstimateKind.STATE,
            state_value="active",
            posterior_probability=0.2,
            assumptions=("assumption",),
            alternatives=("alternative",),
            counter_evidence=counter,
        )
    with pytest.raises(ValueError, match="posterior estimate"):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Invalid",
            kind=MechanismEstimateKind.POSTERIOR,
            assumptions=("assumption",),
            alternatives=("alternative",),
            counter_evidence=counter,
        )
    with pytest.raises(ValueError, match="state estimate"):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Invalid",
            kind=MechanismEstimateKind.STATE,
            state_value="active",
            lower_bound=0.1,
            assumptions=("assumption",),
            alternatives=("alternative",),
            counter_evidence=counter,
        )


def test_uncertainty_is_explicit_on_supported_and_abstained_paths() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 2


def test_posterior_result_has_counter_evidence_and_provenance() -> None:
    result = M1304MechanismEngine().infer(build_scenario_request())
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[0].counter_evidence
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M13-04"
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False


def test_typed_glioma_proteotype_graph_fits_signed_evidence_and_replays() -> None:
    base = build_scenario_request()
    configuration = base.configuration.model_copy(
        update={"model_family": M1304_GLIOMA_MODEL_FAMILY, "bootstrap_replicates": 16}
    )
    observations = (
        MechanismObservation(
            observation_id="obs.egfr",
            mechanism_id="egfr",
            label="EGFR RTK drive",
            standardized_effect=0.8,
            standard_error=0.2,
        ),
        MechanismObservation(
            observation_id="obs.pten",
            mechanism_id="pten",
            label="PTEN brake",
            standardized_effect=-0.6,
            standard_error=0.2,
        ),
        MechanismObservation(
            observation_id="obs.akt",
            mechanism_id="akt",
            label="AKT effector",
            standardized_effect=0.7,
            standard_error=0.25,
        ),
        MechanismObservation(
            observation_id="obs.missing",
            mechanism_id="unmeasured",
            label="Unmeasured marker",
            state=MechanismObservationState.MISSING,
        ),
    )
    relations = (
        MechanismRelation(
            relation_id="rel.egfr-akt",
            source_mechanism_id="egfr",
            target_mechanism_id="akt",
            kind=MechanismRelationKind.ACTIVATES,
            weight=0.8,
        ),
        MechanismRelation(
            relation_id="rel.egfr-pten",
            source_mechanism_id="egfr",
            target_mechanism_id="pten",
            kind=MechanismRelationKind.INHIBITS,
            weight=0.7,
        ),
    )
    request = base.model_copy(
        update={
            "configuration": configuration,
            "typed_observations": observations,
            "typed_relations": relations,
        }
    )
    engine = M1304MechanismEngine()
    result = engine.infer(request)
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.typed_model is True
    assert result.model_profile == M1304_GLIOMA_MODEL_FAMILY
    assert result.solver_iterations > 0
    assert result.solver_objective is not None
    assert {item.mechanism_id for item in result.estimates} == {"akt", "egfr", "pten"}
    assert engine.verify(result) == result


def test_typed_glioma_proteotype_graph_is_order_invariant_and_abstains_without_support() -> None:
    base = build_scenario_request()
    configuration = base.configuration.model_copy(
        update={"model_family": M1304_GLIOMA_MODEL_FAMILY, "bootstrap_replicates": 16}
    )
    observations = (
        MechanismObservation(
            observation_id="obs.a",
            mechanism_id="a",
            label="A",
            standardized_effect=0.6,
            standard_error=0.2,
        ),
        MechanismObservation(
            observation_id="obs.b",
            mechanism_id="b",
            label="B",
            standardized_effect=0.4,
            standard_error=0.2,
        ),
    )
    relation = MechanismRelation(
        relation_id="rel.a-b",
        source_mechanism_id="a",
        target_mechanism_id="b",
        kind=MechanismRelationKind.COUPLES,
        weight=0.5,
    )
    request = base.model_copy(
        update={
            "configuration": configuration,
            "typed_observations": observations,
            "typed_relations": (relation,),
        }
    )
    reversed_request = request.model_copy(
        update={"typed_observations": tuple(reversed(observations))}
    )
    engine = M1304MechanismEngine()
    first = engine.infer(request)
    second = engine.infer(reversed_request)
    assert first.request_digest == second.request_digest
    assert first.estimates == second.estimates
    insufficient = base.model_copy(
        update={"configuration": configuration, "typed_observations": (observations[0],)}
    )
    abstained = engine.infer(insufficient)
    assert abstained.status is MechanismInferenceStatus.ABSTAINED
    assert not abstained.estimates
    assert "requires two supported" in (abstained.abstention_reason or "")


def test_typed_observation_and_relation_closure_rejects_hostile_shapes() -> None:
    base = build_scenario_request()
    with pytest.raises(ValueError, match="requires effect and error"):
        MechanismObservation(
            observation_id="obs.invalid",
            mechanism_id="a",
            label="A",
            standardized_effect=0.2,
        )
    with pytest.raises(ValueError, match="cannot carry a value"):
        MechanismObservation(
            observation_id="obs.missing-value",
            mechanism_id="a",
            label="A",
            standardized_effect=0.2,
            standard_error=0.1,
            state=MechanismObservationState.MISSING,
        )
    with pytest.raises(ValueError, match="self-loop"):
        MechanismRelation(
            relation_id="rel.loop",
            source_mechanism_id="a",
            target_mechanism_id="a",
            kind=MechanismRelationKind.COUPLES,
        )
    observation = MechanismObservation(
        observation_id="obs.a",
        mechanism_id="a",
        label="A",
        standardized_effect=0.2,
        standard_error=0.1,
    )
    duplicate = base.model_copy(update={"typed_observations": (observation, observation)})
    with pytest.raises(ValueError, match="observation ids"):
        InferProteotypeMechanismRequest.model_validate(duplicate.model_dump(), strict=False)
    relation = MechanismRelation(
        relation_id="rel.a-b",
        source_mechanism_id="a",
        target_mechanism_id="b",
        kind=MechanismRelationKind.ACTIVATES,
    )
    unknown = base.model_copy(
        update={"typed_observations": (observation,), "typed_relations": (relation,)}
    )
    with pytest.raises(ValueError, match="unknown mechanism"):
        InferProteotypeMechanismRequest.model_validate(unknown.model_dump(), strict=False)
    observation_b = observation.model_copy(
        update={"observation_id": "obs.b", "mechanism_id": "b", "label": "B"}
    )
    duplicate_relation = base.model_copy(
        update={
            "typed_observations": (observation, observation_b),
            "typed_relations": (relation.model_copy(update={"target_mechanism_id": "b"}),) * 2,
        }
    )
    with pytest.raises(ValueError, match="relation ids"):
        InferProteotypeMechanismRequest.model_validate(
            duplicate_relation.model_dump(), strict=False
        )


def test_typed_graph_handles_censored_and_outlier_effects() -> None:
    base = build_scenario_request()
    configuration = base.configuration.model_copy(
        update={"model_family": M1304_GLIOMA_MODEL_FAMILY, "bootstrap_replicates": 16}
    )
    observations = (
        MechanismObservation(
            observation_id="obs.outlier",
            mechanism_id="outlier",
            label="Outlier RTK",
            standardized_effect=8.0,
            standard_error=0.1,
        ),
        MechanismObservation(
            observation_id="obs.censored",
            mechanism_id="censored",
            label="Left censored brake",
            standardized_effect=1.0,
            standard_error=0.2,
            state=MechanismObservationState.LEFT_CENSORED,
        ),
    )
    relation = MechanismRelation(
        relation_id="rel.outlier-censored",
        source_mechanism_id="outlier",
        target_mechanism_id="censored",
        kind=MechanismRelationKind.INHIBITS,
        weight=0.4,
    )
    request = base.model_copy(
        update={
            "configuration": configuration,
            "typed_observations": observations,
            "typed_relations": (relation,),
        }
    )
    result = M1304MechanismEngine().infer(request)
    assert result.status is MechanismInferenceStatus.INFERRED
    assert all(
        item.lower_bound <= item.posterior_probability <= item.upper_bound
        for item in result.estimates
    )


def test_typed_initialization_keeps_left_censored_limits_feasible() -> None:
    """Mechanism starts use observed centers and feasible censor bounds."""

    observations = (
        (0, 1.2, 0.2, 1.0, MechanismObservationState.OBSERVED),
        (0, 0.4, 0.2, 1.0, MechanismObservationState.LEFT_CENSORED),
        (1, -0.3, 0.2, 1.0, MechanismObservationState.LEFT_CENSORED),
    )

    values = engine_module._initial_typed_values(observations, 2)
    assert values == [0.4, -0.3]


def test_request_and_result_closure_reject_forged_payloads() -> None:
    request = build_scenario_request()
    forged_request = request.model_dump(mode="python")
    forged_request["hypothesis_registry_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="provisional M13-01"):
        InferProteotypeMechanismRequest.model_validate(forged_request, strict=True)
    engine = M1304MechanismEngine()
    result = engine.infer(request)

    def resigned(**updates: object) -> dict[str, object]:
        payload = result.model_dump(mode="python")
        payload.update(updates)
        payload["result_digest"] = result_payload_digest(payload)
        return payload

    with pytest.raises(ValueError, match="request digest"):
        ProteotypeMechanismInferenceResult.model_validate(
            resigned(request_digest="sha256:" + "0" * 64), strict=True
        )
    with pytest.raises(ValueError, match="estimate ids"):
        ProteotypeMechanismInferenceResult.model_validate(
            resigned(estimates=result.estimates + result.estimates), strict=True
        )
    abstained = engine.infer(build_scenario_request("abstain:review"))
    duplicated_findings = {
        **abstained.model_dump(mode="python"),
        "findings": abstained.findings + abstained.findings,
    }
    duplicated_findings["result_digest"] = result_payload_digest(duplicated_findings)
    with pytest.raises(ValueError, match="finding ids"):
        ProteotypeMechanismInferenceResult.model_validate(duplicated_findings, strict=True)
    with pytest.raises(ValueError, match="inferred result"):
        ProteotypeMechanismInferenceResult.model_validate(resigned(estimates=()), strict=True)
    invalid_abstention = {
        **abstained.model_dump(mode="python"),
        "estimates": result.estimates,
    }
    invalid_abstention["result_digest"] = result_payload_digest(invalid_abstention)
    with pytest.raises(ValueError, match="abstained result"):
        ProteotypeMechanismInferenceResult.model_validate(invalid_abstention, strict=True)
    no_review = {**abstained.model_dump(mode="python"), "human_review_required": False}
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ProteotypeMechanismInferenceResult.model_validate(no_review, strict=True)


@pytest.mark.parametrize(
    "method",
    (
        "state:mechanism-b:State mechanism:active",
        "abstain:review",
        "bayesian_graph:mechanism:label",
        "posterior:mechanism-a:Candidate:bad:0.1:0.2",
        "posterior:mechanism-a:Candidate:0.9:0.1:0.2",
        "posterior:mechanism-a:Candidate:0.8:0.9:0.7",
        "posterior:mechanism-a",
        "state:mechanism-a",
        "state:mechanism-a:Label:unknown",
    ),
)
def test_method_matrix_is_deterministic_and_safe(method: str) -> None:
    result = M1304MechanismEngine().infer(build_scenario_request(method))
    if method == "state:mechanism-b:State mechanism:active":
        assert result.status is MechanismInferenceStatus.INFERRED
        assert result.estimates[0].state_value == "active"
    else:
        assert result.status is MechanismInferenceStatus.ABSTAINED
        assert not result.estimates
        assert result.human_review_required


def test_counter_evidence_gate_abstains_when_source_refs_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = M1304MechanismEngine().infer(build_scenario_request())
    request = build_scenario_request().model_copy(update={"source_artifacts": ()})
    monkeypatch.setattr(
        engine_module,
        "_parse_method",
        lambda method, *, counter_evidence, evidence: (normal.estimates[0], None, None),
    )
    with pytest.raises(ValueError):
        M1304MechanismEngine()._result(request)


def test_authorization_runs_before_typed_traversal() -> None:
    with pytest.raises(M1304MechanismAuthorizationError):
        M1304MechanismEngine().infer(build_scenario_request(accepted=False))
    with pytest.raises(M1304MechanismAuthorizationError):
        M1304MechanismEngine().infer({"context": {"references": {}}})

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1304MechanismAuthorizationError):
        M1304MechanismEngine().infer(Exploding())


def test_replay_and_tamper_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1304MechanismEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1304ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))

    original_digest = engine_module.result_payload_digest
    try:
        engine_module.result_payload_digest = lambda value: "sha256:" + "e" * 64
        with pytest.raises(M1304ReplayVerificationError):
            engine.verify(result)
    finally:
        engine_module.result_payload_digest = original_digest

    original_infer = engine_module.M1304MechanismEngine.infer
    monkeypatch.setattr(
        engine_module.M1304MechanismEngine,
        "infer",
        lambda self, request: original_infer(self, build_scenario_request("state:a:Label:active")),
    )
    with pytest.raises(M1304ReplayVerificationError):
        engine.verify(result)

    assert (
        engine_module.infer_proteotype_mechanism(build_scenario_request()).status
        is MechanismInferenceStatus.INFERRED
    )
    with pytest.raises(ValueError):
        engine_module._decimal("not-a-number")
    with pytest.raises(ValueError):
        engine_module._decimal("2")


def test_plugin_is_parse_once_and_token_bound() -> None:
    service = M1304Service()
    plugin = M1304Plugin(service)
    request = build_scenario_request()
    token = plugin.validate(canonical_json_bytes(request))
    assert isinstance(token, ValidatedM1304Request)
    assert plugin.run(token).status is MechanismInferenceStatus.INFERRED
    with pytest.raises(TypeError):
        plugin.run(ValidatedM1304Request(request=request, _seal=object()))
    with pytest.raises(TypeError):
        plugin.run({})  # type: ignore[arg-type]
    assert plugin.verify(plugin.run(token)).status is MechanismInferenceStatus.INFERRED
    with pytest.raises(ValueError):
        plugin.validate("{")
    assert plugin.validate(request).request == request
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-04"


def test_service_validation_and_evaluator() -> None:
    service = M1304Service()
    request = service.validate_request(build_scenario_request().model_dump(mode="json"))
    assert service.execute(request).status is MechanismInferenceStatus.INFERRED
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == 8


def test_http_schema_infer_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    assert client.get("/v1/m13-04/schema/request").status_code == 200
    assert client.get("/v1/m13-04/schema/nope").status_code == 404
    response = client.post("/v1/modules/M13-04/mechanism", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    verified = client.post("/v1/modules/M13-04/verify", json=result_payload)
    assert verified.status_code == 200
    assert (
        client.post(
            "/v1/modules/M13-04/mechanism", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M13-04/mechanism",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    invalid = request.model_dump(mode="json")
    invalid["request_id"] = 1
    assert client.post("/v1/modules/M13-04/mechanism", json=invalid).status_code == 422


def test_http_denies_controls_and_rejects_tamper() -> None:
    client = TestClient(app)
    denied = build_scenario_request(accepted=False)
    assert (
        client.post("/v1/modules/M13-04/mechanism", json=denied.model_dump(mode="json")).status_code
        == 403
    )


def test_http_service_authorization_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(self: object, request: object) -> object:  # noqa: ARG001
        raise M1304MechanismAuthorizationError

    monkeypatch.setattr(M1304Service, "_execute_validated", denied)
    client = TestClient(app)
    response = client.post(
        "/v1/modules/M13-04/mechanism",
        json=build_scenario_request().model_dump(mode="json"),
    )
    assert response.status_code == 403
    result = M1304MechanismEngine().infer(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M13-04/verify", json=result).status_code == 422
    assert (
        client.post(
            "/v1/modules/M13-04/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_cli_export_infer_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1304_app, ["export-schema", "request"]).exit_code == 0
    inferred = runner.invoke(m1304_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    assert runner.invoke(m1304_app, ["infer", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1304_app, ["infer", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1304_app, ["verify", str(result_path)]).exit_code == 0
    result_path.write_text("{", encoding="utf-8")
    assert runner.invoke(m1304_app, ["verify", str(result_path)]).exit_code != 0
    assert runner.invoke(m1304_app, ["export-schema", "bad"]).exit_code == 2


def test_strict_json_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "duplicate.json"
    request_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    result = runner.invoke(m1304_app, ["infer", str(request_path)])
    assert result.exit_code != 0


def test_result_payload_is_canonical_json() -> None:
    result = M1304MechanismEngine().infer(build_scenario_request())
    first = canonical_json_bytes(result)
    second = canonical_json_bytes(result)
    assert first == second
    assert json.loads(first)["result_digest"] == result.result_digest
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}
