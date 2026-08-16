from __future__ import annotations

import copy
import json
from importlib import import_module
from pathlib import Path  # noqa: TC003 - pytest injects a concrete temporary path.
from typing import Any, Final, cast

import pytest
from evals.m11_01.benchmark import run_benchmark
from evals.m11_01.run import build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters import m1101 as m1101_adapter
from glio_proteogen.adapters.m1101 import app, m1101_app
from glio_proteogen.contracts.m11_01 import (
    M1101_OUTPUT_MEDIA_TYPE,
    BiologicalHypothesis,
    HypothesisRegistry,
    HypothesisStatus,
    RegisterVariantPeptideHypothesesRequest,
    VariantPeptideHypothesisRegistryResult,
    canonical_request_digest,
    contract_json_schema,
    contract_json_schemas,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_01_biological_hypothesis_registry as m1101_runtime,
)

SCHEMA_COUNT: Final = 10
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
EVALUATOR_CASE_COUNT: Final = 7
BENCHMARK_CASE_COUNT: Final = 2
CLI_USAGE_ERROR: Final = 2


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


@pytest.mark.parametrize(
    "field",
    ["request_digest", "result_id", "evidence", "evaluations", "falsification_evaluations"],
)
def test_result_contract_rejects_each_replay_closure_break(field: str) -> None:
    engine = m1101_runtime.M1101HypothesisEngine()
    result = engine.register(build_scenario_request())
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
        VariantPeptideHypothesisRegistryResult.model_validate(forged, strict=True)


def test_registry_contract_rejects_duplicate_nested_ids_and_unsafe_result_states() -> None:
    request = build_scenario_request()
    hypothesis = request.hypotheses[0]
    duplicate_rule = hypothesis.model_copy(
        update={"falsification_rules": (hypothesis.falsification_rules[0],) * 2}
    )
    with pytest.raises(ValidationError):
        RegisterVariantPeptideHypothesesRequest.model_validate(
            request.model_copy(update={"hypotheses": (duplicate_rule,)}), strict=True
        )
    duplicate_explanation = hypothesis.model_copy(
        update={
            "competing_explanations": (
                hypothesis.competing_explanations[0],
                hypothesis.competing_explanations[0],
            )
        }
    )
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(duplicate_explanation, strict=True)
    duplicate_tier = hypothesis.model_copy(
        update={"evidence_tiers": (hypothesis.evidence_tiers[0], hypothesis.evidence_tiers[0])}
    )
    with pytest.raises(ValidationError):
        BiologicalHypothesis.model_validate(duplicate_tier, strict=True)
    engine = m1101_runtime.M1101HypothesisEngine()
    result = engine.register(request)
    assert result.registry is not None
    duplicate_registry = result.registry.model_copy(
        update={"hypotheses": (result.registry.hypotheses[0], result.registry.hypotheses[0])}
    )
    with pytest.raises(ValidationError):
        HypothesisRegistry.model_validate(duplicate_registry, strict=True)
    with pytest.raises(ValidationError):
        RegisterVariantPeptideHypothesesRequest.model_validate(
            request.model_copy(
                update={"hypotheses": (request.hypotheses[0], request.hypotheses[0])}
            ),
            strict=True,
        )
    result = engine.register(request)
    with pytest.raises(ValidationError):
        VariantPeptideHypothesisRegistryResult.model_validate(
            result.model_copy(update={"registry": None}), strict=True
        )
    abstained = engine.register(build_scenario_request("unknown_hypothesis"))
    with pytest.raises(ValidationError):
        VariantPeptideHypothesisRegistryResult.model_validate(
            abstained.model_copy(update={"human_review_required": False}), strict=True
        )
    with pytest.raises(ValidationError):
        VariantPeptideHypothesisRegistryResult.model_validate(
            abstained.model_copy(update={"registry": result.registry}), strict=True
        )


def test_canonical_dict_projection_and_replay_disabled_paths_are_exercised() -> None:
    request = build_scenario_request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert normalized_request(request.model_dump(mode="json"))
    result = m1101_runtime.M1101HypothesisEngine().register(request)
    assert "result_digest" not in normalized_result_payload(result.model_dump(mode="json"))
    assert result_payload_digest(result) == result.result_digest
    assert m1101_runtime.M1101HypothesisEngine().verify(result, replay=False) == result


def test_service_public_seams_and_plugin_typed_hostile_inputs() -> None:
    request = build_scenario_request()
    service = m1101_runtime.M1101Service()
    assert service.validate_request(request) == request
    assert service.execute(request).status is HypothesisStatus.SUPPORTED
    assert (
        m1101_runtime.register_variant_peptide_hypotheses(request).status
        is HypothesisStatus.SUPPORTED
    )
    plugin = m1101_runtime.M1101Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M11-01"
    typed_token = plugin.validate(request)
    assert plugin.run(typed_token).status is HypothesisStatus.SUPPORTED
    assert service.verify(service.execute(request))
    assert plugin.verify(service.execute(request))
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_preflight_mapping_exception_and_replay_mismatch_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request()
    m1101_runtime.preflight_hypothesis_authorization({"context": request.context})

    class Explosive:
        @property
        def context(self) -> object:
            raise RuntimeError("canary")

    with pytest.raises(m1101_runtime.M1101HypothesisAuthorizationError):
        m1101_runtime.preflight_hypothesis_authorization(Explosive())
    engine = m1101_runtime.M1101HypothesisEngine()
    result = engine.register(request)
    changed = result.model_copy(
        update={
            "limitations": (
                *result.limitations,
                result.limitations[0].model_copy(update={"code": "extra"}),
            )
        }
    )
    resealed = changed.model_copy(
        update={
            "result_digest": cast(
                "Any",
                import_module(
                    "glio_proteogen.modules.c11_protein_native_subtype."
                    "m11_01_biological_hypothesis_registry.engine"
                ),
            ).result_payload_digest(changed)
        }
    )
    with pytest.raises(m1101_runtime.M1101ReplayVerificationError):
        engine.verify(resealed)
    monkeypatch.setattr(
        cast(
            "Any",
            import_module(
                "glio_proteogen.modules.c11_protein_native_subtype."
                "m11_01_biological_hypothesis_registry.engine"
            ),
        ),
        "result_payload_digest",
        lambda _value: "sha256:" + "0" * 64,
    )
    with pytest.raises(m1101_runtime.M1101ReplayVerificationError):
        engine.verify(result)


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


def test_http_rejects_malformed_and_unauthorized_json_without_execution() -> None:
    client = TestClient(app)
    invalid_json = client.post(
        "/v1/modules/M11-01/hypotheses",
        content=b"{not-json}",
        headers={"content-type": "application/json"},
    )
    assert invalid_json.status_code == HTTP_UNPROCESSABLE
    invalid_payload = build_scenario_request().model_dump(mode="json")
    invalid_payload.pop("hypotheses")
    invalid_model = client.post(
        "/v1/modules/M11-01/hypotheses",
        content=canonical_json_bytes(invalid_payload),
        headers={"content-type": "application/json"},
    )
    assert invalid_model.status_code == HTTP_UNPROCESSABLE
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
    denied_response = client.post(
        "/v1/modules/M11-01/hypotheses",
        content=canonical_json_bytes(denied),
        headers={"content-type": "application/json"},
    )
    assert denied_response.status_code == HTTP_FORBIDDEN


def test_http_verify_route_covers_success_and_tamper_failures() -> None:
    client = TestClient(app)
    result = m1101_runtime.M1101HypothesisEngine().register(build_scenario_request())
    payload = canonical_json_bytes(result)
    verified = client.post(
        "/v1/modules/M11-01/verify",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == HTTP_OK
    wrong_media = client.post("/v1/modules/M11-01/verify", content=payload)
    assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    rejected = client.post(
        "/v1/modules/M11-01/verify",
        content=canonical_json_bytes(forged),
        headers={"content-type": "application/json"},
    )
    assert rejected.status_code == HTTP_UNPROCESSABLE


def test_http_execution_authentication_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DenyingService:
        def _execute_validated(self, _request: object) -> object:
            raise m1101_runtime.M1101HypothesisAuthorizationError

    monkeypatch.setattr(m1101_adapter, "_SERVICE", DenyingService())
    client = TestClient(app)
    response = client.post(
        "/v1/modules/M11-01/hypotheses",
        content=canonical_json_bytes(build_scenario_request()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_FORBIDDEN


def test_cli_register_verify_and_failure_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    result_path = tmp_path / "result.json"
    registered = runner.invoke(
        m1101_app,
        ["register", str(request_path), "--output", str(result_path)],
    )
    assert registered.exit_code == 0
    assert result_path.exists()
    verified = runner.invoke(m1101_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    stdout_register = runner.invoke(m1101_app, ["register", str(request_path)])
    assert stdout_register.exit_code == 0
    overwrite = runner.invoke(
        m1101_app,
        ["register", str(request_path), "--output", str(result_path)],
    )
    assert overwrite.exit_code != 0
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    failed = runner.invoke(m1101_app, ["register", str(invalid)])
    assert failed.exit_code != 0
    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("{bad", encoding="utf-8")
    failed_verify = runner.invoke(m1101_app, ["verify", str(invalid_result)])
    assert failed_verify.exit_code != 0
    unknown_schema = runner.invoke(m1101_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code == CLI_USAGE_ERROR


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
