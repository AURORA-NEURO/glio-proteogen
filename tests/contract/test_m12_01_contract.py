from __future__ import annotations

import copy
import json
from importlib import import_module
from pathlib import Path  # noqa: TC003 - pytest injects a concrete temporary path.
from typing import Any, Final, cast

import pytest
from evals.m12_01.benchmark import run_benchmark
from evals.m12_01.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters import m1201 as m1201_adapter
from glio_proteogen.adapters.m1201 import app, m1201_app
from glio_proteogen.contracts.m12_01 import (
    M1201_OUTPUT_MEDIA_TYPE,
    BiologicalHypothesis,
    BiomarkerPanelHypothesisRegistryResult,
    HypothesisRegistry,
    HypothesisStatus,
    RegisterBiomarkerPanelHypothesesRequest,
    canonical_request_digest,
    contract_json_schemas,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_01_biological_hypothesis_registry as m1201_runtime,
)

SCHEMA_COUNT: Final = 10
CONTROL_COUNT: Final = 7
SUPPORTED_PROBABILITY: Final = 0.9
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
CLI_USAGE_ERROR: Final = 2
EVALUATOR_CASE_COUNT: Final = 7
BENCHMARK_ITERATIONS: Final = 2


def test_all_provisional_schemas_have_strict_metadata_and_unique_ids() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == SCHEMA_COUNT
    assert len({str(schema["$id"]) for schema in schemas.values()}) == SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert metadata["outputMediaType"] == M1201_OUTPUT_MEDIA_TYPE
        assert metadata["strict"] is True
        assert metadata["provisionalAbi"] is True
        assert metadata["competingExplanationsRequired"] is True
        assert metadata["falsificationRulesRequired"] is True


def test_supported_registry_is_replay_bound_and_preserves_controls() -> None:
    request = build_scenario_request()
    result = m1201_runtime.M1201HypothesisEngine().register(request)
    assert result.status is HypothesisStatus.SUPPORTED
    assert result.registry is not None
    assert result.registry.hypotheses[0].competing_explanations
    assert result.registry.hypotheses[0].falsification_rules
    assert len(result.provenance.control_decisions) == CONTROL_COUNT
    assert result.uncertainty.measurement.probability == SUPPORTED_PROBABILITY
    assert result.human_review_required is False
    assert m1201_runtime.M1201HypothesisEngine().verify(result) == result


@pytest.mark.parametrize(
    "case_id",
    ["refuted_hypothesis", "unknown_hypothesis", "failed_falsification", "unknown_falsification"],
)
def test_unsafe_or_unknown_paths_abstain_without_registry(case_id: str) -> None:
    result = m1201_runtime.M1201HypothesisEngine().register(build_scenario_request(case_id))
    assert result.status is HypothesisStatus.ABSTAINED
    assert result.registry is None
    assert result.human_review_required is True
    assert result.abstention_reason
    assert result.uncertainty.measurement.probability is None


def test_denied_control_preflight_happens_before_hypothesis_evaluation() -> None:
    request = build_scenario_request()
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(m1201_runtime.M1201HypothesisAuthorizationError):
        m1201_runtime.M1201HypothesisEngine().register(denied)


def test_request_unknown_fields_and_duplicate_hypotheses_are_rejected() -> None:
    payload = json.loads(canonical_json_bytes(build_scenario_request()).decode("utf-8"))
    payload["unknown"] = "canary"
    with pytest.raises(ValidationError):
        RegisterBiomarkerPanelHypothesesRequest.model_validate(payload, strict=True)
    duplicate = build_scenario_request()
    duplicate_payload = duplicate.model_dump(mode="json")
    duplicate_payload["hypotheses"].append(copy.deepcopy(duplicate_payload["hypotheses"][0]))
    with pytest.raises(ValidationError):
        RegisterBiomarkerPanelHypothesesRequest.model_validate(duplicate_payload, strict=True)


@pytest.mark.parametrize(
    "field",
    ["request_digest", "result_id", "evidence", "evaluations", "falsification_evaluations"],
)
def test_result_contract_rejects_replay_closure_break(field: str) -> None:
    result = m1201_runtime.M1201HypothesisEngine().register(build_scenario_request())
    if field == "request_digest":
        forged = result.model_copy(update={"request_digest": "sha256:" + "a" * 64})
    elif field == "result_id":
        forged = result.model_copy(update={"result_id": "result.attacker"})
    elif field == "evidence":
        forged = result.model_copy(
            update={
                "evidence": (result.evidence[0].model_copy(update={"role": "counter_evidence"}),)
            }
        )
    elif field == "evaluations":
        forged = result.model_copy(update={"evaluations": ()})
    else:
        forged = result.model_copy(update={"falsification_evaluations": ()})
    with pytest.raises(ValidationError):
        BiomarkerPanelHypothesisRegistryResult.model_validate(forged, strict=True)


def test_nested_id_and_unsafe_state_closure_is_enforced() -> None:
    request = build_scenario_request()
    hypothesis = request.hypotheses[0]
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(
            hypothesis.model_copy(
                update={"falsification_rules": (hypothesis.falsification_rules[0],) * 2}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(
            hypothesis.model_copy(
                update={"competing_explanations": (hypothesis.competing_explanations[0],) * 2}
            ),
            strict=True,
        )
    result = m1201_runtime.M1201HypothesisEngine().register(request)
    assert result.registry is not None
    with pytest.raises(ValidationError):
        HypothesisRegistry.model_validate(
            result.registry.model_copy(update={"hypotheses": (result.registry.hypotheses[0],) * 2}),
            strict=True,
        )
    with pytest.raises(ValidationError):
        BiomarkerPanelHypothesisRegistryResult.model_validate(
            result.model_copy(update={"registry": None}), strict=True
        )
    abstained = m1201_runtime.M1201HypothesisEngine().register(
        build_scenario_request("unknown_hypothesis")
    )
    with pytest.raises(ValidationError):
        BiomarkerPanelHypothesisRegistryResult.model_validate(
            abstained.model_copy(update={"human_review_required": False}), strict=True
        )


def test_canonical_projection_service_and_plugin_seams() -> None:
    request = build_scenario_request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert normalized_request(request.model_dump(mode="json"))
    engine = m1201_runtime.M1201HypothesisEngine()
    result = engine.register(request)
    assert "result_digest" not in normalized_result_payload(result.model_dump(mode="json"))
    assert result_payload_digest(result) == result.result_digest
    assert engine.verify(result, replay=False) == result
    service = m1201_runtime.M1201Service()
    assert service.validate_request(request) == request
    assert service.execute(request).status is HypothesisStatus.SUPPORTED
    plugin = m1201_runtime.M1201Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-01"
    token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(token).status is HypothesisStatus.SUPPORTED
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_preflight_mapping_and_replay_mismatch_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_scenario_request()
    m1201_runtime.preflight_hypothesis_authorization({"context": request.context})

    class Explosive:
        @property
        def context(self) -> object:
            raise RuntimeError("canary")

    with pytest.raises(m1201_runtime.M1201HypothesisAuthorizationError):
        m1201_runtime.preflight_hypothesis_authorization(Explosive())
    engine = m1201_runtime.M1201HypothesisEngine()
    result = engine.register(request)
    changed = result.model_copy(
        update={
            "limitations": (
                *result.limitations,
                result.limitations[0].model_copy(update={"code": "extra"}),
            )
        }
    )
    module = cast(
        "Any",
        import_module(
            "glio_proteogen.modules.c12_driver_to_protein_consequence."
            "m12_01_biological_hypothesis_registry.engine"
        ),
    )
    resealed = changed.model_copy(update={"result_digest": module.result_payload_digest(changed)})
    with pytest.raises(m1201_runtime.M1201ReplayVerificationError):
        engine.verify(resealed)
    monkeypatch.setattr(module, "result_payload_digest", lambda _value: "sha256:" + "0" * 64)
    with pytest.raises(m1201_runtime.M1201ReplayVerificationError):
        engine.verify(result)


def test_plugin_rejects_copied_and_mutated_tokens() -> None:
    request = build_scenario_request()
    plugin = m1201_runtime.M1201Plugin(m1201_runtime.M1201Service())
    token = plugin.validate(request)
    assert plugin.run(token).status is HypothesisStatus.SUPPORTED
    with pytest.raises(TypeError):
        plugin.run(copy.copy(token))
    with pytest.raises(TypeError):
        plugin.run(token.__class__(request=token.request.model_copy(deep=True), _seal=token._seal))


def test_http_schema_registration_and_verification_paths() -> None:
    client = TestClient(app)
    assert client.get("/v1/m12-01/schema/request").status_code == HTTP_OK
    response = client.post(
        "/v1/modules/M12-01/hypotheses",
        content=canonical_json_bytes(build_scenario_request()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "supported"
    result = m1201_runtime.M1201HypothesisEngine().register(build_scenario_request())
    verified = client.post(
        "/v1/modules/M12-01/verify",
        content=canonical_json_bytes(result),
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == HTTP_OK
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    rejected = client.post(
        "/v1/modules/M12-01/verify",
        content=canonical_json_bytes(forged),
        headers={"content-type": "application/json"},
    )
    assert rejected.status_code == HTTP_UNPROCESSABLE


def test_http_rejects_media_schema_json_and_authorization_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m12-01/schema/not-real").status_code == HTTP_NOT_FOUND
    assert (
        client.post(
            "/v1/modules/M12-01/hypotheses", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA
    )
    assert (
        client.post(
            "/v1/modules/M12-01/hypotheses",
            content=b"{bad",
            headers={"content-type": "application/json"},
        ).status_code
        == HTTP_UNPROCESSABLE
    )
    request = build_scenario_request()
    denied_refs = request.context.references.model_copy(
        update={
            "consent": request.context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": denied_refs})}
    )
    denied_response = client.post(
        "/v1/modules/M12-01/hypotheses",
        content=canonical_json_bytes(denied),
        headers={"content-type": "application/json"},
    )
    assert denied_response.status_code == HTTP_FORBIDDEN


def test_http_execution_authentication_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    class DenyingService:
        def _execute_validated(self, _request: object) -> object:
            raise m1201_runtime.M1201HypothesisAuthorizationError

    monkeypatch.setattr(m1201_adapter, "_SERVICE", DenyingService())
    response = TestClient(app).post(
        "/v1/modules/M12-01/hypotheses",
        content=canonical_json_bytes(build_scenario_request()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_FORBIDDEN


def test_cli_register_verify_and_failure_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    result_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            m1201_app, ["register", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(m1201_app, ["verify", str(result_path)]).exit_code == 0
    assert runner.invoke(m1201_app, ["register", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1201_app, ["register", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    assert runner.invoke(m1201_app, ["register", str(invalid)]).exit_code != 0
    assert runner.invoke(m1201_app, ["verify", str(invalid)]).exit_code != 0
    assert runner.invoke(m1201_app, ["export-schema", "unknown"]).exit_code == CLI_USAGE_ERROR


def test_evaluator_fixture_and_benchmark_are_bound() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == EVALUATOR_CASE_COUNT
    benchmark = run_benchmark(BENCHMARK_ITERATIONS)
    assert benchmark["iterations"] == BENCHMARK_ITERATIONS
    assert isinstance(benchmark["max_ns"], int)
    assert benchmark["max_ns"] > 0
