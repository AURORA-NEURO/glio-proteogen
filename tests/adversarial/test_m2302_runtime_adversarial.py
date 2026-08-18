"""Deep runtime and interface boundary coverage for M23-02."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path  # noqa: TC003 - pytest resolves the temporary path annotation.

import pytest
from evals.m23_02.fixture import denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c21_reference_material.m23_02_synthetic_truth_simulation_generator.api as m2302_api  # noqa: E501
import glio_proteogen.modules.c21_reference_material.m23_02_synthetic_truth_simulation_generator.cli as m2302_cli  # noqa: E501
from glio_proteogen.contracts.m23_02 import (
    GenerationStatus,
    VariantPeptideSyntheticTruthResult,
)
from glio_proteogen.contracts.m23_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2302AuthorizationError,
    M2302Engine,
    M2302EvaluationError,
    M2302Plugin,
    generate_variant_peptide_synthetic_truth,
)
from tests.adversarial.test_m2302_contract_adversarial import _request


def test_engine_rejects_malformed_preflight_without_leaking_details() -> None:
    with pytest.raises(M2302AuthorizationError, match="seven accepted controls"):
        M2302Engine().generate({"secret": "must-not-echo"})


def test_engine_handles_property_failure_and_public_entrypoint() -> None:
    class BrokenCandidate:
        @property
        def context(self) -> object:
            raise RuntimeError("private control failure")  # noqa: TRY003

    with pytest.raises(M2302AuthorizationError, match="controls are malformed"):
        M2302Engine().generate(BrokenCandidate())
    assert generate_variant_peptide_synthetic_truth(_request()).status.value == "generated"


def test_engine_rejects_unsupported_upstream_media() -> None:
    request = _request()
    invalid_upstream = request.upstream_result.model_copy(
        update={"media_type": "application/octet-stream"}
    )
    payload = request.model_copy(update={"upstream_result": invalid_upstream})

    with pytest.raises(M2302EvaluationError):
        M2302Engine().generate(payload)


def test_plugin_accepts_typed_object_and_rejects_duplicate_json_keys() -> None:
    plugin = M2302Plugin()
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "generated"

    duplicate = b'{"request_id":"one","request_id":"two"}'
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate(duplicate)


def test_api_sanitizes_invalid_json_and_non_object_replay() -> None:
    client = TestClient(m2302_api.create_app())
    malformed = client.post("/v1/modules/M23-02/generate", content=b"not-json")
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not-json" not in malformed.text

    non_object = client.post("/v1/modules/M23-02/verify", json=["not-an-object"])
    assert non_object.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not-an-object" not in non_object.text

    invalid_json = client.post("/v1/modules/M23-02/verify", content=b"not-json")
    assert invalid_json.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_api_sanitizes_denied_controls_and_exports_named_schema() -> None:
    client = TestClient(m2302_api.create_app())
    denied = denied_request().model_dump_json()
    validated = client.post("/v1/modules/M23-02/validate", content=denied)
    assert validated.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    generated = client.post("/v1/modules/M23-02/generate", content=denied)
    assert generated.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    schema = client.get("/v1/modules/M23-02/schemas/request")
    assert schema.status_code == HTTPStatus.OK


def test_api_sanitizes_tampered_result() -> None:
    client = TestClient(m2302_api.create_app())
    generated = client.post(
        "/v1/modules/M23-02/generate",
        content=_request().model_dump_json(),
    )
    assert generated.status_code == HTTPStatus.OK
    tampered = generated.json()
    tampered["result_digest"] = sha256_digest("tampered")

    response = client.post("/v1/modules/M23-02/verify", json=tampered)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "tampered" not in response.text


def test_cli_sanitizes_unknown_schema_and_invalid_request(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2302_cli.app, ["export-schema", "secret"])
    assert unknown.exit_code != 0
    assert "unknown M23-02 contract" in unknown.output

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"secret": "do-not-echo"}), encoding="utf-8")
    invalid = runner.invoke(m2302_cli.app, ["validate", str(invalid_path)])
    assert invalid.exit_code != 0
    assert "do-not-echo" not in invalid.output

    generated = runner.invoke(m2302_cli.app, ["generate", str(invalid_path)])
    assert generated.exit_code != 0


def test_cli_denied_request_and_invalid_result_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    validated = runner.invoke(m2302_cli.app, ["validate", str(denied_path)])
    assert validated.exit_code != 0
    generated = runner.invoke(m2302_cli.app, ["generate", str(denied_path)])
    assert generated.exit_code != 0

    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("{}", encoding="utf-8")
    verified = runner.invoke(m2302_cli.app, ["verify", str(invalid_result)])
    assert verified.exit_code != 0
    assert "valid M23-02 result" in verified.output


def test_cli_can_emit_schema_and_result_to_stdout_or_new_file(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request-schema.json"
    exported = runner.invoke(
        m2302_cli.app,
        ["export-schema", "request", "--output", str(schema_path)],
    )
    assert exported.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["$schema"]

    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    generated = runner.invoke(m2302_cli.app, ["generate", str(request_path)])
    assert generated.exit_code == 0
    assert json.loads(generated.stdout)["status"] == "generated"


def test_cli_emits_abstention_with_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    generated = M2302Engine().generate(_request())
    payload = generated.__dict__.copy()
    payload.update(
        {
            "status": GenerationStatus.ABSTAINED,
            "corpus": None,
            "manifest": None,
            "abstention_reason": "caller-declared support requires review",
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m2302_review_required",
                rationale="Review is required before synthetic fixture generation.",
            ),
            "human_review_required": True,
        }
    )
    payload["result_digest"] = result_payload_digest(
        VariantPeptideSyntheticTruthResult.model_construct(**payload)
    )
    abstained = VariantPeptideSyntheticTruthResult.model_validate(payload)
    monkeypatch.setattr(m2302_cli._SERVICE, "execute", lambda _request: abstained)
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(m2302_cli.app, ["generate", str(request_path)])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "abstained"


def test_cli_sanitizes_service_verify_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = M2302Engine().generate(_request())
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")

    def fail_verify(_result: object) -> VariantPeptideSyntheticTruthResult:
        raise ValueError("private replay detail")  # noqa: TRY003

    monkeypatch.setattr(m2302_cli._SERVICE, "verify", fail_verify)
    response = CliRunner().invoke(m2302_cli.app, ["verify", str(result_path)])

    assert response.exit_code != 0
    assert "private replay detail" not in response.output
    assert "result replay is invalid" in response.output


def test_cli_reports_replay_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = M2302Engine().generate(_request())
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    forged = result.model_copy(update={"result_digest": sha256_digest("cli-mismatch")})
    monkeypatch.setattr(m2302_cli._SERVICE, "verify", lambda _result: forged)

    response = CliRunner().invoke(m2302_cli.app, ["verify", str(result_path)])

    assert response.exit_code == 1
    assert json.loads(response.stdout)["verified"] is False
