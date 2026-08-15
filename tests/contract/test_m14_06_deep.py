"""Contract, runtime, adapter, and adversarial coverage for M14-06."""

# The matrix intentionally uses hostile wire inputs and literal protocol states.
# ruff: noqa: E501, ARG005, PLR2004, PT011, PT007, TC003, TRY003

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from evals.m14_06.run import (
    _artifact,
    _perturbation,
    build_scenario_request,
    run_evaluator,
)
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_06_perturbation_sensitivity_simulator.engine as engine_module
from glio_proteogen.adapters.m1406 import app, m1406_app
from glio_proteogen.contracts.m14_06 import (
    M1406_OUTPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    ProteinSubtypeSensitivitySimulationResult,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateProteinSubtypePerturbationsRequest,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m14_06.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_06_perturbation_sensitivity_simulator import (
    M1406Plugin,
    M1406ReplayVerificationError,
    M1406SensitivityAuthorizationError,
    M1406SensitivityEngine,
    M1406Service,
    ValidatedM1406Request,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "surface",
        "perturbation",
        "response",
        "configuration",
        "diagnostic",
    }
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"]
        for item in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["outputMediaType"]
        == M1406_OUTPUT_MEDIA_TYPE
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_perturbation_shape_requires_distinct_values_and_artifacts() -> None:
    with pytest.raises(ValueError, match="must differ"):
        _perturbation("scenario.same", baseline="1", perturbed="1")
    with pytest.raises(ValueError, match="prior artifact"):
        PerturbationSpecification(
            perturbation_id="scenario.prior",
            kind=PerturbationKind.ALTERNATIVE_PRIOR,
            target_ids=("protein.target",),
            parameter="abundance",
            baseline_value="1",
            perturbed_value="2",
            rationale="prior",
        )
    with pytest.raises(ValueError, match="assay artifact"):
        PerturbationSpecification(
            perturbation_id="scenario.assay",
            kind=PerturbationKind.ASSAY_PERTURBATION,
            target_ids=("protein.target",),
            parameter="abundance",
            baseline_value="1",
            perturbed_value="2",
            rationale="assay",
        )


def test_response_bounds_require_counter_evidence_and_are_closed() -> None:
    with pytest.raises(ValueError, match="counter-evidence"):
        SensitivityResponse(
            scenario_id="scenario.invalid",
            status=PerturbationResponseStatus.BOUNDED,
            response_value=0.5,
            lower_bound=0.1,
            upper_bound=0.9,
            assumptions=("assumption",),
        )
    result = M1406SensitivityEngine().infer(build_scenario_request())
    response = result.surface.responses[0] if result.surface is not None else None
    assert response is not None
    assert response.lower_bound is not None
    assert response.response_value is not None
    assert response.upper_bound is not None
    assert response.lower_bound <= response.response_value <= response.upper_bound
    assert response.counter_evidence
    with pytest.raises(ValueError, match="ordered bounds"):
        SensitivityResponse(
            scenario_id="scenario.invalid-bounds",
            status=PerturbationResponseStatus.BOUNDED,
            response_value=0.5,
            lower_bound=0.9,
            upper_bound=0.1,
            assumptions=("assumption",),
            counter_evidence=response.counter_evidence,
        )
    with pytest.raises(ValueError, match="non-bounded"):
        SensitivityResponse(
            scenario_id="scenario.invalid-status",
            status=PerturbationResponseStatus.NOT_EVALUABLE,
            response_value=0.1,
            assumptions=("assumption",),
        )


def test_uncertainty_is_explicit_on_supported_and_abstained_paths() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 2


def test_simulation_has_surface_provenance_and_parent_boundary() -> None:
    result = M1406SensitivityEngine().infer(build_scenario_request())
    assert result.status is SensitivitySimulationStatus.SIMULATED
    assert result.surface is not None
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M14-06"
    assert result.parent_target == "protein_subtype"
    assert result.emits_parent is False
    assert result.surface.responses[0].counter_evidence


def test_result_closure_rejects_forged_payloads() -> None:
    request = build_scenario_request()
    engine = M1406SensitivityEngine()
    result = engine.infer(request)
    forged = request.model_dump(mode="python")
    forged["upstream_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M14-05"):
        type(request).model_validate(forged, strict=True)
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ProteinSubtypeSensitivitySimulationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["surface"] = None
    payload["status"] = SensitivitySimulationStatus.SIMULATED
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="simulated result"):
        ProteinSubtypeSensitivitySimulationResult.model_validate(payload, strict=True)
    abstained = engine.infer(build_scenario_request(model_family="unregistered_model"))
    no_review = abstained.model_dump(mode="python")
    no_review["human_review_required"] = False
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ProteinSubtypeSensitivitySimulationResult.model_validate(no_review, strict=True)
    with_surface = abstained.model_dump(mode="python")
    with_surface["surface"] = result.surface.model_dump(mode="python") if result.surface else None
    with_surface["result_digest"] = result_payload_digest(with_surface)
    with pytest.raises(ValueError, match="abstained result"):
        ProteinSubtypeSensitivitySimulationResult.model_validate(with_surface, strict=True)


def test_surface_and_request_identity_closures_reject_duplicates_and_wrong_media() -> None:
    request = build_scenario_request()
    result = M1406SensitivityEngine().infer(request)
    assert result.surface is not None
    surface = result.surface
    duplicate_perturbations = surface.model_dump(mode="python")
    duplicate_perturbations["perturbations"] = duplicate_perturbations["perturbations"] * 2
    with pytest.raises(ValueError, match="perturbation identifiers"):
        SensitivitySurface.model_validate(duplicate_perturbations, strict=True)
    duplicate_responses = surface.model_dump(mode="python")
    duplicate_responses["responses"] = duplicate_responses["responses"] * 2
    with pytest.raises(ValueError, match="response identifiers"):
        SensitivitySurface.model_validate(duplicate_responses, strict=True)
    mismatched = surface.model_dump(mode="python")
    mismatched["responses"][0]["scenario_id"] = "scenario.mismatch"
    with pytest.raises(ValueError, match="exactly one"):
        SensitivitySurface.model_validate(mismatched, strict=True)
    wrong_media = surface.model_dump(mode="python")
    wrong_media["baseline_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M14-05"):
        SensitivitySurface.model_validate(wrong_media, strict=True)
    duplicate_request = request.model_dump(mode="python")
    duplicate_request["perturbations"] = duplicate_request["perturbations"] * 2
    with pytest.raises(ValueError, match="request perturbation"):
        SimulateProteinSubtypePerturbationsRequest.model_validate(duplicate_request, strict=True)


@pytest.mark.parametrize(
    ("model_family", "baseline"),
    (("unregistered_model", "1.0"), ("curated_rule", "N/A"), ("curated_rule", "nan")),
)
def test_unsupported_or_nonfinite_inputs_abstain(model_family: str, baseline: str) -> None:
    request = build_scenario_request(
        model_family=model_family,
        perturbations=(_perturbation("scenario.invalid", baseline=baseline),),
    )
    result = M1406SensitivityEngine().infer(request)
    assert result.status is SensitivitySimulationStatus.ABSTAINED
    assert result.surface is None
    assert result.human_review_required


def test_all_declared_perturbation_kinds_are_supported() -> None:
    perturbations = (
        *(
            _perturbation(f"scenario.{kind.value}", kind=kind)
            for kind in PerturbationKind
            if kind is not PerturbationKind.ALTERNATIVE_PRIOR
            and kind is not PerturbationKind.ASSAY_PERTURBATION
        ),
        _perturbation(
            "scenario.prior",
            kind=PerturbationKind.ALTERNATIVE_PRIOR,
            alternative_prior=_artifact("prior"),
        ),
        _perturbation(
            "scenario.assay",
            kind=PerturbationKind.ASSAY_PERTURBATION,
            assay_artifact=_artifact("assay"),
        ),
    )
    result = M1406SensitivityEngine().infer(build_scenario_request(perturbations=perturbations))
    assert result.status is SensitivitySimulationStatus.SIMULATED
    assert result.surface is not None
    assert len(result.surface.responses) == 5


def test_authorization_runs_before_typed_traversal() -> None:
    with pytest.raises(M1406SensitivityAuthorizationError):
        M1406SensitivityEngine().infer(build_scenario_request(accepted=False))
    with pytest.raises(M1406SensitivityAuthorizationError):
        M1406SensitivityEngine().infer({"context": {"references": {}}})

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1406SensitivityAuthorizationError):
        M1406SensitivityEngine().infer(Exploding())


def test_replay_and_tamper_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1406SensitivityEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1406ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    original_digest = engine_module.result_payload_digest
    try:
        engine_module.result_payload_digest = lambda value: "sha256:" + "e" * 64
        with pytest.raises(M1406ReplayVerificationError):
            engine.verify(result)
    finally:
        engine_module.result_payload_digest = original_digest
    original_infer = engine_module.M1406SensitivityEngine.infer
    monkeypatch.setattr(
        engine_module.M1406SensitivityEngine,
        "infer",
        lambda self, request: original_infer(
            self, build_scenario_request(model_family="unregistered_model")
        ),
    )
    with pytest.raises(M1406ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    assert (
        engine_module.simulate_protein_subtype_perturbations(result.request).status
        is SensitivitySimulationStatus.SIMULATED
    )
    assert engine_module._decimal("not-a-number") is None
    assert (
        engine_module._response(
            _perturbation("scenario.no-counter"), evidence=(), counter_evidence=()
        )
        is None
    )


def test_plugin_is_parse_once_and_token_bound() -> None:
    service = M1406Service()
    plugin = M1406Plugin(service)
    request = build_scenario_request()
    token = plugin.validate(canonical_json_bytes(request))
    assert isinstance(token, ValidatedM1406Request)
    assert plugin.run(token).status is SensitivitySimulationStatus.SIMULATED
    with pytest.raises(TypeError):
        plugin.run(ValidatedM1406Request(request=request, _seal=object()))
    with pytest.raises(TypeError):
        plugin.run({})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        plugin.validate("{")
    assert plugin.validate(request).request == request
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-06"


def test_service_validation_and_evaluator() -> None:
    service = M1406Service()
    request = service.validate_request(build_scenario_request().model_dump(mode="json"))
    assert service.execute(request).status is SensitivitySimulationStatus.SIMULATED
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == 7


def test_http_schema_simulate_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    assert client.get("/v1/m14-06/schema/request").status_code == 200
    assert client.get("/v1/m14-06/schema/nope").status_code == 404
    response = client.post("/v1/modules/M14-06/sensitivity", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    verified = client.post("/v1/modules/M14-06/verify", json=result_payload)
    assert verified.status_code == 200
    assert (
        client.post(
            "/v1/modules/M14-06/sensitivity",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M14-06/sensitivity",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    invalid = request.model_dump(mode="json")
    invalid["request_id"] = 1
    assert client.post("/v1/modules/M14-06/sensitivity", json=invalid).status_code == 422
    assert (
        client.post(
            "/v1/modules/M14-06/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )


def test_http_denies_controls_and_rejects_tamper(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    denied_request = build_scenario_request(accepted=False)
    assert (
        client.post(
            "/v1/modules/M14-06/sensitivity", json=denied_request.model_dump(mode="json")
        ).status_code
        == 403
    )
    result = M1406SensitivityEngine().infer(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M14-06/verify", json=result).status_code == 422
    def deny_execute(self: object, request: object) -> object:  # noqa: ARG001
        raise M1406SensitivityAuthorizationError
    monkeypatch.setattr(M1406Service, "_execute_validated", deny_execute)
    assert (
        client.post(
            "/v1/modules/M14-06/sensitivity",
            json=build_scenario_request().model_dump(mode="json"),
        ).status_code
        == 403
    )


def test_cli_export_infer_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1406_app, ["export-schema", "request"]).exit_code == 0
    inferred = runner.invoke(m1406_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    assert runner.invoke(m1406_app, ["infer", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1406_app, ["infer", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1406_app, ["verify", str(result_path)]).exit_code == 0
    result_path.write_text("{", encoding="utf-8")
    assert runner.invoke(m1406_app, ["verify", str(result_path)]).exit_code != 0
    assert runner.invoke(m1406_app, ["export-schema", "bad"]).exit_code == 2


def test_strict_json_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "duplicate.json"
    request_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    result = runner.invoke(m1406_app, ["infer", str(request_path)])
    assert result.exit_code != 0


def test_result_payload_is_canonical_json() -> None:
    result = M1406SensitivityEngine().infer(build_scenario_request())
    first = canonical_json_bytes(result)
    second = canonical_json_bytes(result)
    assert first == second
    assert json.loads(first)["result_digest"] == result.result_digest
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}
