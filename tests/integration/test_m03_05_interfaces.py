"""Black-box parity, strict ingress, and hostile authorization for M03-05."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final

import pytest
from evals.m03_05.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_05 import (
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Plugin,
    M0305ProteinInferenceArtifactEngine,
    M0305Service,
    ProteinInferenceArtifactAuthorizationError,
    detect_protein_inference_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "quality-receipt",
    "evidence-ledger",
    "evidence-unit",
    "signal-score",
    "posterior",
    "contamination-flag",
    "exclusion-mask",
    "finding",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_CONTENT_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
PRIVATE_CANARY: Final = "PRIVATE_M0305_INTERFACE_CANARY"
AUTHORIZATION_DENIALS: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "withheld"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)


class _HostileRequest(Mapping[str, object]):
    """Expose authorization context while every artifact accessor is hostile."""

    def __init__(self, context: object) -> None:
        self._context = context

    def __getitem__(self, key: str) -> object:
        if key == "context":
            return self._context
        raise AssertionError(PRIVATE_CANARY)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(PRIVATE_CANARY)

    def __len__(self) -> int:
        raise AssertionError(PRIVATE_CANARY)


def _payload() -> dict[str, Any]:
    return copy.deepcopy(build_scenario_request().model_dump(mode="json"))


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m03_05_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-05/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"] == (
        f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-05:1.0.0:{name}"
    )


def test_library_engine_service_plugin_api_and_cli_return_equal_result(
    tmp_path: Path,
) -> None:
    request = build_scenario_request()
    payload = request.model_dump_json()
    request_path = tmp_path / "artifact-request.json"
    request_path.write_text(payload, encoding="utf-8")
    library = detect_protein_inference_artifacts(request)
    engine = M0305ProteinInferenceArtifactEngine().detect(request)
    service = M0305Service()
    service_result = service.execute(request)
    plugin = M0305Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))

    with TestClient(create_app(tmp_path / "artifact.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-05/artifacts",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert library == engine == service_result == plugin_result
    assert (
        ProteinInferenceArtifactDetectionResult.model_validate_json(response.content, strict=True)
        == library
    )
    assert (
        ProteinInferenceArtifactDetectionResult.model_validate_json(cli.stdout, strict=True)
        == library
    )


def test_api_cli_and_service_replay_verify_the_complete_result(
    tmp_path: Path,
) -> None:
    result = detect_protein_inference_artifacts(build_scenario_request())
    result_path = tmp_path / "artifact-result.json"
    result_path.write_bytes(canonical_json_bytes(result))

    service = M0305Service()
    assert service.verify(result) == result

    with TestClient(create_app(tmp_path / "verify.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-05/artifacts/verify",
            content=result_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "verify", str(result_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        ProteinInferenceArtifactDetectionResult.model_validate_json(
            response.content,
            strict=True,
        )
        == result
    )
    assert (
        ProteinInferenceArtifactDetectionResult.model_validate_json(
            cli.stdout,
            strict=True,
        )
        == result
    )


def test_replay_verify_rejects_a_re_signed_nested_score(
    tmp_path: Path,
) -> None:
    result = detect_protein_inference_artifacts(build_scenario_request())
    payload = result.model_dump(mode="json")
    payload["result_digest"] = "sha256:" + ("a" * 64)
    result_path = tmp_path / "tampered-result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(create_app(tmp_path / "tamper.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-05/artifacts/verify",
            content=result_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "verify", str(result_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in response.text + cli.output


def test_library_replay_verifier_accepts_bounded_json_and_mapping_inputs(
    tmp_path: Path,
) -> None:
    del tmp_path
    result = detect_protein_inference_artifacts(build_scenario_request())
    serialized = canonical_json_bytes(result)
    service = M0305Service()

    assert service.verify(serialized) == result
    assert service.verify(bytearray(serialized)) == result
    assert service.verify(result.model_dump(mode="json")) == result
    with pytest.raises(ValidationError):
        service.verify([])


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_denied_control_precedes_hostile_ledger_traversal(
    tmp_path: Path,
    role: str,
    denied_state: str,
) -> None:
    payload = _payload()
    payload["context"]["references"][role]["state"] = denied_state
    payload["evidence_ledger"] = PRIVATE_CANARY
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{role}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{role}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-05/artifacts",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.json() == {
        "detail": "upstream controls do not authorize protein-inference artifact detection"
    }
    assert cli.exit_code == CLI_USAGE_ERROR
    assert PRIVATE_CANARY not in response.text + cli.output
    assert "Traceback" not in cli.output


def test_service_denial_does_not_traverse_or_disclose_hostile_accessors() -> None:
    context = _payload()["context"]
    context["references"]["consent"]["state"] = "revoked"

    with pytest.raises(ProteinInferenceArtifactAuthorizationError) as caught:
        M0305Service.validate_request(_HostileRequest(context))

    assert PRIVATE_CANARY not in str(caught.value)


@pytest.mark.parametrize(
    ("mutation", "expected_term"),
    [
        ("duplicate", "duplicate"),
        ("nonfinite", "finite"),
        ("unknown", "extra_forbidden"),
        ("coercion", "int_type"),
    ],
)
def test_api_and_cli_reject_every_non_strict_json_class_without_disclosure(
    tmp_path: Path,
    mutation: str,
    expected_term: str,
) -> None:
    request = build_scenario_request()
    if mutation in {"duplicate", "nonfinite"}:
        serialized = request.model_dump_json()
        operation = '"operation":"detect_protein_inference_artifacts"'
        if mutation == "duplicate":
            serialized = serialized.replace(operation, f"{operation},{operation}", 1)
        else:
            serialized = f'{serialized[:-1]},"{PRIVATE_CANARY}":NaN}}'
    else:
        payload = _payload()
        if mutation == "unknown":
            payload[PRIVATE_CANARY] = "must-not-be-reflected"
        else:
            payload["policy"]["max_sources"] = "64"
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"strict-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-05/artifacts",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert expected_term in cli.output.lower()
    assert PRIVATE_CANARY not in response.text + cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_distinguish_exact_four_mib_from_first_byte_past_limit(
    tmp_path: Path,
) -> None:
    exact = b"{" + b" " * (M0305_MAX_CANONICAL_REQUEST_BYTES - 1)
    oversized = exact + b" "
    exact_path = tmp_path / "exact-limit.json"
    oversized_path = tmp_path / "oversized.json"
    exact_path.write_bytes(exact)
    oversized_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "size.sqlite3")) as client:
        exact_api = client.post(
            "/v1/modules/M03-05/artifacts",
            content=exact,
            headers={"content-type": "application/json"},
        )
        oversized_api = client.post(
            "/v1/modules/M03-05/artifacts",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    exact_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(exact_path)],
    )
    oversized_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(oversized_path)],
    )

    assert len(exact) == M0305_MAX_CANONICAL_REQUEST_BYTES
    assert len(oversized) == M0305_MAX_CANONICAL_REQUEST_BYTES + 1
    assert exact_api.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert exact_api.json()["detail"][0]["type"] == "json_invalid_syntax"
    assert oversized_api.status_code == HTTP_CONTENT_TOO_LARGE
    assert oversized_api.json()["detail"] == "request body exceeds the byte limit"
    assert exact_cli.exit_code == CLI_USAGE_ERROR
    assert "json_invalid_syntax" in exact_cli.output
    assert oversized_cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in oversized_cli.output
    assert "Traceback" not in exact_cli.output + oversized_cli.output


def test_api_content_type_is_exact_but_accepts_json_charset(tmp_path: Path) -> None:
    payload = build_scenario_request().model_dump_json()

    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        rejected = client.post(
            "/v1/modules/M03-05/artifacts",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        accepted = client.post(
            "/v1/modules/M03-05/artifacts",
            content=payload,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    assert rejected.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert rejected.json() == {"detail": "content-type must be application/json"}
    assert accepted.status_code == HTTP_OK, accepted.text


def test_invalid_schema_name_is_rejected_by_api_and_cli(tmp_path: Path) -> None:
    invalid_name = "not-an-artifact-contract"

    with TestClient(create_app(tmp_path / "schema-invalid.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-05/{invalid_name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "export-schema", invalid_name],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["type"] == "literal_error"
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Invalid value" in cli.output
    assert "Traceback" not in cli.output


def test_cli_sanitizes_a_late_request_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "unreadable-after-cli-validation.json"
    request_path.write_text(build_scenario_request().model_dump_json(), encoding="utf-8")

    def fail_read(_path: object, *, max_bytes: int | None = None) -> bytes:
        del max_bytes
        raise OSError(PRIVATE_CANARY)

    monkeypatch.setattr(cli_adapter, "read_bounded", fail_read)
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-artifacts", "detect", str(request_path)],
    )

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "unable to read or decode request document" in cli.output
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output
