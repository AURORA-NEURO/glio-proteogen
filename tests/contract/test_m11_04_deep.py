"""Contract, runtime, adapter, and adversarial coverage for M11-04."""

# The matrix intentionally uses literal protocol status codes and broad ValueError
# assertions at the contract boundary to exercise hostile wire inputs.
# ruff: noqa: E501, ARG005, PLR2004, PT011, PT007, TC003, TRY003

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evals.m11_04.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c11_protein_native_subtype.m11_04_network_state_mechanism_inference.engine as engine_module
from glio_proteogen.adapters.m1104 import app, m1104_app
from glio_proteogen.contracts.m11_04 import (
    M1104_OUTPUT_MEDIA_TYPE,
    InferVariantPeptideMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismInferenceStatus,
    VariantPeptideMechanismInferenceResult,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m11_04.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c11_protein_native_subtype.m11_04_network_state_mechanism_inference import (
    M1104MechanismAuthorizationError,
    M1104MechanismEngine,
    M1104Plugin,
    M1104ReplayVerificationError,
    M1104Service,
    ValidatedM1104Request,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {"request", "output", "estimate", "configuration", "finding"}
    assert all(item["x-glio-contract"]["provisionalAbi"] for item in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1104_OUTPUT_MEDIA_TYPE
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_estimate_invariants_reject_invalid_posterior_and_state() -> None:
    counter = M1104MechanismEngine().infer(build_scenario_request()).estimates[0].counter_evidence
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
    result = M1104MechanismEngine().infer(build_scenario_request())
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[0].counter_evidence
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M11-04"
    assert result.parent_target == "variant_peptide"
    assert result.emits_parent is False


def test_request_and_result_closure_reject_forged_payloads() -> None:
    request = build_scenario_request()
    forged_request = request.model_dump(mode="python")
    forged_request["hypothesis_registry_result"]["media_type"] = "application/octet-stream"  # type: ignore[index]
    with pytest.raises(ValueError, match="provisional M11-01"):
        InferVariantPeptideMechanismRequest.model_validate(forged_request, strict=True)
    engine = M1104MechanismEngine()
    result = engine.infer(request)

    def resigned(**updates: object) -> dict[str, object]:
        payload = result.model_dump(mode="python")
        payload.update(updates)
        payload["result_digest"] = result_payload_digest(payload)
        return payload

    with pytest.raises(ValueError, match="request digest"):
        VariantPeptideMechanismInferenceResult.model_validate(
            resigned(request_digest="sha256:" + "0" * 64), strict=True
        )
    with pytest.raises(ValueError, match="estimate ids"):
        VariantPeptideMechanismInferenceResult.model_validate(
            resigned(estimates=result.estimates + result.estimates), strict=True
        )
    abstained = engine.infer(build_scenario_request("abstain:review"))
    duplicated_findings = {
        **abstained.model_dump(mode="python"),
        "findings": abstained.findings + abstained.findings,
    }
    duplicated_findings["result_digest"] = result_payload_digest(duplicated_findings)
    with pytest.raises(ValueError, match="finding ids"):
        VariantPeptideMechanismInferenceResult.model_validate(duplicated_findings, strict=True)
    with pytest.raises(ValueError, match="inferred result"):
        VariantPeptideMechanismInferenceResult.model_validate(resigned(estimates=()), strict=True)
    invalid_abstention = {
        **abstained.model_dump(mode="python"),
        "estimates": result.estimates,
    }
    invalid_abstention["result_digest"] = result_payload_digest(invalid_abstention)
    with pytest.raises(ValueError, match="abstained result"):
        VariantPeptideMechanismInferenceResult.model_validate(invalid_abstention, strict=True)
    no_review = {**abstained.model_dump(mode="python"), "human_review_required": False}
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        VariantPeptideMechanismInferenceResult.model_validate(no_review, strict=True)


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
    result = M1104MechanismEngine().infer(build_scenario_request(method))
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
    normal = M1104MechanismEngine().infer(build_scenario_request())
    request = build_scenario_request().model_copy(update={"source_artifacts": ()})
    monkeypatch.setattr(
        engine_module,
        "_parse_method",
        lambda method, *, counter_evidence, evidence: (normal.estimates[0], None, None),
    )
    with pytest.raises(ValueError):
        M1104MechanismEngine()._result(request)


def test_authorization_runs_before_typed_traversal() -> None:
    with pytest.raises(M1104MechanismAuthorizationError):
        M1104MechanismEngine().infer(build_scenario_request(accepted=False))
    with pytest.raises(M1104MechanismAuthorizationError):
        M1104MechanismEngine().infer({"context": {"references": {}}})

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1104MechanismAuthorizationError):
        M1104MechanismEngine().infer(Exploding())


def test_replay_and_tamper_detection() -> None:
    engine = M1104MechanismEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1104ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))

    original_digest = engine_module.result_payload_digest
    try:
        engine_module.result_payload_digest = lambda value: "sha256:" + "e" * 64  # type: ignore[assignment]
        with pytest.raises(M1104ReplayVerificationError):
            engine.verify(result)
    finally:
        engine_module.result_payload_digest = original_digest

    assert (
        engine_module.infer_variant_peptide_mechanism(build_scenario_request()).status
        is MechanismInferenceStatus.INFERRED
    )
    with pytest.raises(ValueError):
        engine_module._decimal("not-a-number")


def test_plugin_is_parse_once_and_token_bound() -> None:
    service = M1104Service()
    plugin = M1104Plugin(service)
    request = build_scenario_request()
    token = plugin.validate(canonical_json_bytes(request))
    assert isinstance(token, ValidatedM1104Request)
    assert plugin.run(token).status is MechanismInferenceStatus.INFERRED
    with pytest.raises(TypeError):
        plugin.run(ValidatedM1104Request(request=request, _seal=object()))
    with pytest.raises(TypeError):
        plugin.run({})  # type: ignore[arg-type]
    assert plugin.verify(plugin.run(token)).status is MechanismInferenceStatus.INFERRED
    with pytest.raises(ValueError):
        plugin.validate("{")
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M11-04"


def test_service_validation_and_evaluator() -> None:
    service = M1104Service()
    request = service.validate_request(build_scenario_request().model_dump(mode="json"))
    assert service.execute(request).status is MechanismInferenceStatus.INFERRED
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == 7


def test_http_schema_infer_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    assert client.get("/v1/m11-04/schema/request").status_code == 200
    assert client.get("/v1/m11-04/schema/nope").status_code == 404
    response = client.post("/v1/modules/M11-04/mechanism", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    verified = client.post("/v1/modules/M11-04/verify", json=result_payload)
    assert verified.status_code == 200
    assert (
        client.post(
            "/v1/modules/M11-04/mechanism", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M11-04/mechanism",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )


def test_http_denies_controls_and_rejects_tamper() -> None:
    client = TestClient(app)
    denied = build_scenario_request(accepted=False)
    assert (
        client.post("/v1/modules/M11-04/mechanism", json=denied.model_dump(mode="json")).status_code
        == 403
    )
    result = M1104MechanismEngine().infer(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M11-04/verify", json=result).status_code == 422
    assert (
        client.post(
            "/v1/modules/M11-04/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_cli_export_infer_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1104_app, ["export-schema", "request"]).exit_code == 0
    inferred = runner.invoke(m1104_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    assert (
        runner.invoke(
            m1104_app, ["infer", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1104_app, ["verify", str(result_path)]).exit_code == 0
    assert runner.invoke(m1104_app, ["export-schema", "bad"]).exit_code == 2


def test_strict_json_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "duplicate.json"
    request_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    result = runner.invoke(m1104_app, ["infer", str(request_path)])
    assert result.exit_code != 0


def test_result_payload_is_canonical_json() -> None:
    result = M1104MechanismEngine().infer(build_scenario_request())
    first = canonical_json_bytes(result)
    second = canonical_json_bytes(result)
    assert first == second
    assert json.loads(first)["result_digest"] == result.result_digest
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}
