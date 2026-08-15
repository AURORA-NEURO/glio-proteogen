"""Contract, runtime, adapter, evaluator, and adversarial coverage for M15-06."""

# ruff: noqa: E501, ARG005, PLR2004, PT007, TC003, TRY003

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from evals.m15_06.run import _artifact, _evidence, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_06_perturbation_sensitivity_simulator.engine as engine_module
from glio_proteogen.adapters.m1506 import app, m1506_app
from glio_proteogen.contracts.m15_06 import (
    M1506_M1505_INPUT_MEDIA_TYPE,
    ComplexActivitySensitivitySimulationResult,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivityResponse,
    SensitivitySimulationStatus,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_06_perturbation_sensitivity_simulator import (
    M1506AuthorizationError,
    M1506Plugin,
    M1506ReplayVerificationError,
    M1506SensitivitySimulatorEngine,
    M1506Service,
    ValidatedM1506Request,
    preflight_m1506_authorization,
    simulate_complex_activity_perturbations,
)


def _perturbation(**updates: object) -> PerturbationSpecification:
    values: dict[str, object] = {
        "perturbation_id": "scenario.test",
        "kind": PerturbationKind.IN_SILICO,
        "target_ids": ("target.complex",),
        "parameter": "activity",
        "baseline_value": "1.0",
        "perturbed_value": "1.2",
        "rationale": "test perturbation",
        "evidence": _evidence("test-perturbation"),
    }
    values.update(updates)
    return PerturbationSpecification.model_validate(values, strict=True)


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
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["boundedResponsesRequired"]
        is True
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_contract_shapes_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="must differ"):
        _perturbation(baseline_value="1.0", perturbed_value="1.0")
    with pytest.raises(ValueError, match="prior artifact"):
        _perturbation(kind=PerturbationKind.ALTERNATIVE_PRIOR, evidence=())
    with pytest.raises(ValueError, match="assay artifact"):
        _perturbation(kind=PerturbationKind.ASSAY_PERTURBATION)
    with pytest.raises(ValueError, match="requires evidence"):
        _perturbation(
            kind=PerturbationKind.ALTERNATIVE_PRIOR,
            alternative_prior=_artifact("prior"),
            evidence=(),
        )
    with pytest.raises(ValueError, match="finite"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.BOUNDED,
            response_value=float("nan"),
            lower_bound=0.0,
            upper_bound=1.0,
            assumptions=("x",),
            evidence=_evidence("bad"),
        )
    with pytest.raises(ValueError, match="requires evidence"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.BOUNDED,
            response_value=0.1,
            lower_bound=0.0,
            upper_bound=1.0,
            assumptions=("x",),
        )
    with pytest.raises(ValueError, match="non-bounded"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.ABSTAINED,
            response_value=0.1,
            assumptions=("x",),
        )
    with pytest.raises(ValueError, match="non-bounded"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.OUT_OF_ENVELOPE,
            lower_bound=0.0,
            assumptions=("x",),
        )


def test_request_and_surface_closures_reject_tampering() -> None:
    request = build_scenario_request()
    duplicate = request.model_dump(mode="python")
    duplicate["perturbations"] = duplicate["perturbations"] * 2
    with pytest.raises(ValueError, match="identifiers"):
        type(request).model_validate(duplicate, strict=True)
    forged = request.model_dump(mode="python")
    forged["upstream_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M15-05"):
        type(request).model_validate(forged, strict=True)
    result = M1506SensitivitySimulatorEngine().infer(request)
    assert result.surface is not None
    bad_surface = result.surface.model_dump(mode="python")
    bad_surface["responses"] = (*bad_surface["responses"], bad_surface["responses"][0])
    with pytest.raises(ValueError, match="identifiers"):
        type(result.surface).model_validate(bad_surface, strict=True)
    mismatched = result.surface.model_dump(mode="python")
    mismatched["responses"] = (
        result.surface.responses[0]
        .model_copy(update={"scenario_id": "scenario.other"})
        .model_dump(mode="python"),
    )
    with pytest.raises(ValueError, match="exactly one"):
        type(result.surface).model_validate(mismatched, strict=True)
    wrong_media = result.surface.model_copy(
        update={"baseline_result": _artifact("wrong", "application/octet-stream")}
    )
    with pytest.raises(ValueError, match="M15-05"):
        type(result.surface).model_validate(wrong_media.model_dump(mode="python"), strict=True)
    too_many = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(update={"maximum_scenarios": 1}),
            "perturbations": (_perturbation(), _perturbation(perturbation_id="scenario.two")),
        }
    )
    with pytest.raises(ValueError, match="scenario limit"):
        type(request).model_validate(too_many.model_dump(mode="python"), strict=True)


def test_supported_result_has_bounds_parent_and_all_uncertainty_dimensions() -> None:
    result = M1506SensitivitySimulatorEngine().infer(build_scenario_request())
    assert result.status is SensitivitySimulationStatus.SIMULATED
    assert result.surface is not None
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M15-06"
    assert all(
        item.status is PerturbationResponseStatus.BOUNDED for item in result.surface.responses
    )
    profile = expected_uncertainty(supported=True)
    assert profile.measurement.probability == 0.9
    assert len(profile.sensitivity_notes) == 2


def test_evidence_paths_include_prior_and_assay_artifacts() -> None:
    request = build_scenario_request(
        perturbations=(
            _perturbation(
                kind=PerturbationKind.ALTERNATIVE_PRIOR,
                alternative_prior=_artifact("prior"),
                evidence=_evidence("prior-evidence"),
            ),
            _perturbation(
                perturbation_id="scenario.assay",
                kind=PerturbationKind.ASSAY_PERTURBATION,
                assay_artifact=_artifact("assay"),
                evidence=_evidence("assay-evidence"),
            ),
        )
    )
    result = M1506SensitivitySimulatorEngine().infer(request)
    assert result.surface is not None
    assert len(result.evidence) >= 3


@pytest.mark.parametrize(
    "scenario",
    (
        _perturbation(baseline_value="missing"),
        _perturbation(kind=PerturbationKind.MECHANISM_STRESS, rationale="missing gate"),
        _perturbation(baseline_value="0", perturbed_value="11"),
    ),
)
def test_unsafe_perturbations_abstain(scenario: PerturbationSpecification) -> None:
    result = M1506SensitivitySimulatorEngine().infer(
        build_scenario_request(perturbations=(scenario,))
    )
    assert result.status is SensitivitySimulationStatus.ABSTAINED
    assert result.surface is None
    assert result.human_review_required
    assert result.findings


def test_unknown_model_family_abstains() -> None:
    result = M1506SensitivitySimulatorEngine().infer(build_scenario_request(model_family="unknown"))
    assert result.status is SensitivitySimulationStatus.ABSTAINED
    assert result.human_review_required


def test_result_closure_rejects_forged_digest_id_evidence_and_review() -> None:
    engine = M1506SensitivitySimulatorEngine()
    result = engine.infer(build_scenario_request())
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ComplexActivitySensitivitySimulationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="identifier"):
        ComplexActivitySensitivitySimulationResult.model_validate(payload, strict=True)
    abstained = engine.infer(
        build_scenario_request(perturbations=(_perturbation(baseline_value="bad"),))
    )
    no_review = abstained.model_dump(mode="python")
    no_review["human_review_required"] = False
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ComplexActivitySensitivitySimulationResult.model_validate(no_review, strict=True)
    no_evidence = result.model_dump(mode="python")
    no_evidence["evidence"] = ()
    no_evidence["result_digest"] = result_payload_digest(no_evidence)
    with pytest.raises(ValueError, match="result evidence"):
        ComplexActivitySensitivitySimulationResult.model_validate(no_evidence, strict=True)


def test_authorization_precedes_hostile_traversal() -> None:
    with pytest.raises(M1506AuthorizationError):
        M1506SensitivitySimulatorEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1506AuthorizationError):
        preflight_m1506_authorization(Exploding())


def test_replay_and_tamper_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1506SensitivitySimulatorEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1506ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    monkeypatch.setattr(engine_module, "result_payload_digest", lambda value: "sha256:" + "e" * 64)
    with pytest.raises(M1506ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    original_infer = engine_module.M1506SensitivitySimulatorEngine.infer
    monkeypatch.setattr(
        engine_module.M1506SensitivitySimulatorEngine,
        "infer",
        lambda self, request: original_infer(self, build_scenario_request(model_family="unknown")),
    )
    with pytest.raises(M1506ReplayVerificationError):
        engine.verify(result)


def test_plugin_token_boundary_and_service_parity() -> None:
    service = M1506Service()
    plugin = M1506Plugin(service)
    token = plugin.validate(build_scenario_request())
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(
        mode="json"
    )
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1506Request", build_scenario_request()))
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1506Request", []))
    json_token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert plugin.run(json_token).status is SensitivitySimulationStatus.SIMULATED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-06"


def test_public_operation_and_plugin_verify() -> None:
    result = simulate_complex_activity_perturbations(build_scenario_request())
    assert (
        M1506Plugin(M1506Service()).verify(result).status is SensitivitySimulationStatus.SIMULATED
    )


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 7


def test_fastapi_interfaces_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m15-06/schema/request").status_code == 200
    assert client.get("/v1/m15-06/schema/unknown").status_code == 404
    request_payload = build_scenario_request().model_dump(mode="json")
    response = client.post("/v1/modules/M15-06/simulate", json=request_payload)
    assert response.status_code == 200
    result = response.json()
    assert client.post("/v1/modules/M15-06/verify", json=result).status_code == 200
    assert (
        client.post(
            "/v1/modules/M15-06/simulate",
            json=build_scenario_request(accepted=False).model_dump(mode="json"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/modules/M15-06/simulate", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M15-06/simulate",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert client.post("/v1/modules/M15-06/simulate", json={}).status_code == 403
    assert client.post("/v1/modules/M15-06/verify", json={}).status_code == 422
    assert (
        client.post(
            "/v1/modules/M15-06/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_cli_simulate_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1506_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1506_app, ["export-schema", "unknown"]).exit_code != 0
    first = runner.invoke(m1506_app, ["simulate", str(request_path), "--output", str(output_path)])
    assert first.exit_code == 0
    assert runner.invoke(m1506_app, ["simulate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1506_app, ["simulate", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1506_app, ["verify", str(output_path)]).exit_code == 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1506_app, ["simulate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1506_app, ["verify", str(bad_result)]).exit_code != 0


def test_canonical_json_is_stable_and_upstream_media_type_is_frozen() -> None:
    request = build_scenario_request()
    assert canonical_json_bytes(request) == canonical_json_bytes(request.model_copy())
    assert request.upstream_result.media_type == M1506_M1505_INPUT_MEDIA_TYPE
