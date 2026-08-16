from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from evals.m14_01.benchmark import run_benchmark
from evals.m14_01.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1401 import app, m1401_app
from glio_proteogen.contracts.m14_01 import (
    M1401_OUTPUT_MEDIA_TYPE,
    BiologicalHypothesis,
    HypothesisRegistry,
    HypothesisStatus,
    ProteinSubtypeHypothesisRegistryResult,
    RegisterProteinSubtypeHypothesesRequest,
    canonical_request_digest,
    contract_json_schema,
    contract_json_schemas,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_01_biological_hypothesis_registry as m1401_runtime,
)

SCHEMA_COUNT: Final = 10
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
EVALUATOR_CASE_COUNT: Final = 7
CLI_USAGE_ERROR: Final = 2
BENCHMARK_ITERATIONS: Final = 2


def test_all_provisional_schemas_have_strict_metadata_and_unique_ids() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == SCHEMA_COUNT
    ids = {str(schema["$id"]) for schema in schemas.values()}
    assert len(ids) == SCHEMA_COUNT
    assert all(
        schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        for schema in schemas.values()
    )
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["outputMediaType"] == M1401_OUTPUT_MEDIA_TYPE
        assert metadata["strict"] is True
        assert metadata["pendingOwnerConfirmation"] is True
    request_metadata = cast("dict[str, object]", contract_json_schema("request")["x-glio-contract"])
    assert cast("int", request_metadata["maxRequestBytes"]) > 0


def test_supported_registry_is_replay_bound_and_preserves_competing_evidence() -> None:
    request = build_scenario_request()
    engine = m1401_runtime.M1401HypothesisEngine()
    result = engine.register(request)
    assert result.status is HypothesisStatus.SUPPORTED
    assert result.registry is not None
    assert result.registry.hypotheses[0].competing_explanations
    assert result.registry.hypotheses[0].falsification_rules
    assert result.human_review_required is False
    assert engine.verify(result) == result


@pytest.mark.parametrize(
    "case_id",
    ["refuted_hypothesis", "unknown_hypothesis", "failed_falsification", "unknown_falsification"],
)
def test_unsafe_or_unknown_paths_abstain_without_registry(case_id: str) -> None:
    result = m1401_runtime.M1401HypothesisEngine().register(build_scenario_request(case_id))
    assert result.status is HypothesisStatus.ABSTAINED
    assert result.registry is None
    assert result.human_review_required is True
    assert result.abstention_reason
    assert result.support_decision.status.value == "unsupported"


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
    with pytest.raises(m1401_runtime.M1401HypothesisAuthorizationError):
        m1401_runtime.M1401HypothesisEngine().register(denied)


def test_unknown_fields_and_duplicate_hypotheses_are_rejected() -> None:
    payload = json.loads(canonical_json_bytes(build_scenario_request()).decode("utf-8"))
    payload["unknown"] = "canary"
    with pytest.raises(ValidationError):
        RegisterProteinSubtypeHypothesesRequest.model_validate(payload, strict=True)
    duplicate = build_scenario_request()
    duplicate_payload = duplicate.model_dump(mode="json")
    duplicate_payload["hypotheses"].append(copy.deepcopy(duplicate_payload["hypotheses"][0]))
    with pytest.raises(ValidationError):
        RegisterProteinSubtypeHypothesesRequest.model_validate(duplicate_payload, strict=True)


def test_result_replay_rejects_digest_and_nested_tampering() -> None:
    engine = m1401_runtime.M1401HypothesisEngine()
    result = engine.register(build_scenario_request())
    with pytest.raises(m1401_runtime.M1401ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    assert result.registry is not None
    forged = result.model_copy(
        update={"registry": result.registry.model_copy(update={"reviewed_by": "attacker"})}
    )
    with pytest.raises(m1401_runtime.M1401ReplayVerificationError):
        engine.verify(forged)


@pytest.mark.parametrize(
    "field", ["request_digest", "result_id", "evidence", "evaluations", "falsification_evaluations"]
)
def test_result_contract_rejects_replay_closure_breaks(field: str) -> None:
    result = m1401_runtime.M1401HypothesisEngine().register(build_scenario_request())
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
        ProteinSubtypeHypothesisRegistryResult.model_validate(forged, strict=True)


def test_duplicate_nested_ids_and_unsafe_result_states_are_rejected() -> None:
    request = build_scenario_request()
    hypothesis = request.hypotheses[0]
    with pytest.raises(ValidationError):
        RegisterProteinSubtypeHypothesesRequest.model_validate(
            request.model_copy(update={"hypotheses": (hypothesis, hypothesis)}), strict=True
        )
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(
            hypothesis.model_copy(
                update={"competing_explanations": (hypothesis.competing_explanations[0],) * 2}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(
            hypothesis.model_copy(
                update={"falsification_rules": (hypothesis.falsification_rules[0],) * 2}
            ),
            strict=True,
        )
    engine = m1401_runtime.M1401HypothesisEngine()
    result = engine.register(request)
    assert result.registry is not None
    with pytest.raises(ValidationError):
        HypothesisRegistry.model_validate(
            result.registry.model_copy(update={"hypotheses": (result.registry.hypotheses[0],) * 2}),
            strict=True,
        )
    with pytest.raises(ValidationError):
        ProteinSubtypeHypothesisRegistryResult.model_validate(
            result.model_copy(update={"registry": None}), strict=True
        )
    abstained = engine.register(build_scenario_request("unknown_hypothesis"))
    with pytest.raises(ValidationError):
        ProteinSubtypeHypothesisRegistryResult.model_validate(
            abstained.model_copy(update={"human_review_required": False}), strict=True
        )
    with pytest.raises(ValidationError):
        ProteinSubtypeHypothesisRegistryResult.model_validate(
            abstained.model_copy(update={"registry": result.registry}), strict=True
        )


def test_canonical_dict_projection_and_replay_disabled_paths() -> None:
    request = build_scenario_request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert normalized_request(request.model_dump(mode="json"))
    result = m1401_runtime.M1401HypothesisEngine().register(request)
    assert "result_digest" not in normalized_result_payload(result.model_dump(mode="json"))
    assert result_payload_digest(result) == result.result_digest
    assert m1401_runtime.M1401HypothesisEngine().verify(result, replay=False) == result


def test_service_public_seams_and_plugin_hostile_token_inputs() -> None:
    request = build_scenario_request()
    service = m1401_runtime.M1401Service()
    assert service.validate_request(request) == request
    assert service.execute(request).status is HypothesisStatus.SUPPORTED
    assert (
        m1401_runtime.register_protein_subtype_hypotheses(request).status
        is HypothesisStatus.SUPPORTED
    )
    plugin = m1401_runtime.M1401Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token).status is HypothesisStatus.SUPPORTED
    json_token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(json_token).status is HypothesisStatus.SUPPORTED
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    assert plugin.verify(plugin.run(token))


def test_http_schema_register_verify_and_sanitized_failures() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    body = canonical_json_bytes(request)
    response = client.get("/v1/m14-01/schema/request")
    assert response.status_code == HTTP_OK
    assert response.json()["$id"].endswith(":request")
    assert client.get("/v1/m14-01/schema/nope").status_code == HTTP_NOT_FOUND
    response = client.post(
        "/v1/modules/M14-01/hypotheses", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == HTTP_OK
    result_payload = response.json()
    response = client.post("/v1/modules/M14-01/verify", json=result_payload)
    assert response.status_code == HTTP_OK
    assert response.json()["result_digest"] == result_payload["result_digest"]
    assert (
        client.post(
            "/v1/modules/M14-01/hypotheses", content=body, headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA
    )
    assert (
        client.post(
            "/v1/modules/M14-01/hypotheses",
            content=b'{"x":1}',
            headers={"content-type": "application/json"},
        ).status_code
        == HTTP_FORBIDDEN
    )
    assert (
        client.post(
            "/v1/modules/M14-01/verify", content=b"{}", headers={"content-type": "application/json"}
        ).status_code
        == HTTP_UNPROCESSABLE
    )
    assert (
        client.post(
            "/v1/modules/M14-01/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA
    )
    malformed = client.post(
        "/v1/modules/M14-01/hypotheses",
        content=b"{not-json}",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTP_UNPROCESSABLE


def test_cli_register_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    export = runner.invoke(m1401_app, ["export-schema", "request"])
    assert export.exit_code == 0
    assert '"$id"' in export.stdout
    assert runner.invoke(m1401_app, ["export-schema", "invalid"]).exit_code == CLI_USAGE_ERROR
    stdout_register = runner.invoke(m1401_app, ["register", str(request_path)])
    assert stdout_register.exit_code == 0
    assert "result_digest" in stdout_register.stdout
    registered = runner.invoke(
        m1401_app, ["register", str(request_path), "--output", str(result_path)]
    )
    assert registered.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1401_app, ["register", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    verified = runner.invoke(m1401_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert "result_digest" in verified.stdout
    result_path.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1401_app, ["verify", str(result_path)]).exit_code != 0
    request_path.write_text('{"duplicate": 1, "duplicate": 2}', encoding="utf-8")
    assert runner.invoke(m1401_app, ["register", str(request_path)]).exit_code != 0


def test_evaluator_and_benchmark_are_fixture_bound() -> None:
    evaluation = run_evaluator()
    assert evaluation["passed"] is True
    assert evaluation["declared"] == EVALUATOR_CASE_COUNT
    assert evaluation["executed"] == EVALUATOR_CASE_COUNT
    benchmark = run_benchmark(BENCHMARK_ITERATIONS)
    assert benchmark["passed"] is True
    assert benchmark["iterations"] == BENCHMARK_ITERATIONS
