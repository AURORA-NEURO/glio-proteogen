from __future__ import annotations

import copy
import json
from typing import Final, cast

import pytest
from evals.m11_01.benchmark import run_benchmark
from evals.m11_01.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1101 import app, m1101_app
from glio_proteogen.contracts.m11_01 import (
    M1101_OUTPUT_MEDIA_TYPE,
    HypothesisStatus,
    RegisterVariantPeptideHypothesesRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_01_biological_hypothesis_registry as m1101_runtime,
)

SCHEMA_COUNT: Final = 10
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404
HTTP_UNSUPPORTED_MEDIA: Final = 415
EVALUATOR_CASE_COUNT: Final = 7
BENCHMARK_CASE_COUNT: Final = 2


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
        assert metadata["outputMediaType"] == M1101_OUTPUT_MEDIA_TYPE
        assert metadata["strict"] is True
    request_metadata = cast("dict[str, object]", contract_json_schema("request")["x-glio-contract"])
    assert request_metadata["strict"] is True


def test_supported_registry_is_replay_bound_and_preserves_competing_evidence() -> None:
    request = build_scenario_request("supported_registry")
    result = m1101_runtime.M1101HypothesisEngine().register(request)
    assert result.status is HypothesisStatus.SUPPORTED
    assert result.registry is not None
    assert result.registry.hypotheses[0].competing_explanations
    assert result.registry.hypotheses[0].falsification_rules
    assert result.human_review_required is False
    assert m1101_runtime.M1101HypothesisEngine().verify(result) == result


@pytest.mark.parametrize(
    "case_id",
    ["refuted_hypothesis", "unknown_hypothesis", "failed_falsification", "unknown_falsification"],
)
def test_unsafe_or_unknown_registry_paths_abstain_without_registry(case_id: str) -> None:
    result = m1101_runtime.M1101HypothesisEngine().register(build_scenario_request(case_id))
    assert result.status is HypothesisStatus.ABSTAINED
    assert result.registry is None
    assert result.human_review_required is True
    assert result.abstention_reason


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
    with pytest.raises(m1101_runtime.M1101HypothesisAuthorizationError):
        m1101_runtime.M1101HypothesisEngine().register(denied)


def test_request_unknown_fields_and_duplicate_hypotheses_are_rejected() -> None:
    payload = json.loads(canonical_json_bytes(build_scenario_request()).decode("utf-8"))
    payload["unknown"] = "canary"
    with pytest.raises(ValidationError):
        RegisterVariantPeptideHypothesesRequest.model_validate(payload, strict=True)
    duplicate = build_scenario_request()
    duplicate_payload = duplicate.model_dump(mode="json")
    duplicate_payload["hypotheses"].append(copy.deepcopy(duplicate_payload["hypotheses"][0]))
    with pytest.raises(ValidationError):
        RegisterVariantPeptideHypothesesRequest.model_validate(duplicate_payload, strict=True)


def test_result_replay_rejects_digest_and_nested_registry_tampering() -> None:
    engine = m1101_runtime.M1101HypothesisEngine()
    result = engine.register(build_scenario_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(m1101_runtime.M1101ReplayVerificationError):
        engine.verify(forged)
    mutated_registry = (
        result.registry.model_copy(update={"reviewed_by": "attacker"}) if result.registry else None
    )
    assert mutated_registry is not None
    forged_nested = result.model_copy(update={"registry": mutated_registry})
    with pytest.raises(m1101_runtime.M1101ReplayVerificationError):
        engine.verify(forged_nested)


def test_plugin_uses_strict_parse_once_and_rejects_copied_or_mutated_tokens() -> None:
    request = build_scenario_request()
    plugin = m1101_runtime.M1101Plugin(m1101_runtime.M1101Service())
    token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(token).status is HypothesisStatus.SUPPORTED
    with pytest.raises(TypeError):
        plugin.run(copy.copy(token))
    with pytest.raises(TypeError):
        plugin.run(token.__class__(request=token.request.model_copy(deep=True), _seal=token._seal))


def test_http_schema_and_registration_match_library_result() -> None:
    client = TestClient(app)
    schema_response = client.get("/v1/m11-01/schema/request")
    assert schema_response.status_code == HTTP_OK
    assert schema_response.json()["$id"].endswith(":request")
    response = client.post(
        "/v1/modules/M11-01/hypotheses",
        content=canonical_json_bytes(build_scenario_request()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "supported"


def test_http_rejects_wrong_media_and_unknown_schema() -> None:
    client = TestClient(app)
    assert client.get("/v1/m11-01/schema/not-real").status_code == HTTP_NOT_FOUND
    assert (
        client.post(
            "/v1/modules/M11-01/hypotheses",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA
    )


def test_cli_exports_schema_and_evaluator_is_fixture_bound() -> None:
    runner = CliRunner()
    schema = runner.invoke(m1101_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$id"].endswith(":request")
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == EVALUATOR_CASE_COUNT
    benchmark = run_benchmark(BENCHMARK_CASE_COUNT)
    assert benchmark["iterations"] == BENCHMARK_CASE_COUNT
    max_ns = benchmark["max_ns"]
    assert isinstance(max_ns, int)
    assert max_ns > 0
