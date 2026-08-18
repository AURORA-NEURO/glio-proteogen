"""Public-library parity and hostile authorization boundaries for M03-06."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final

import pytest
from evals.m03_06.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_CANONICAL_RESULT_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    M0306Plugin,
    M0306ProteinInferenceHarmonizationEngine,
    M0306Service,
    ProteinInferenceHarmonizationAuthorizationError,
    harmonize_protein_inference_support,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "unit-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_CONTENT_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
PRIVATE_CANARY: Final = "PRIVATE_M0306_INTERFACE_CANARY"
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
    """Expose authorization context while every downstream accessor is hostile."""

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


@pytest.fixture(scope="module")
def canonical_request() -> HarmonizeProteinInferenceSupportRequest:
    return build_scenario_request()


def _payload(request: HarmonizeProteinInferenceSupportRequest) -> dict[str, Any]:
    return copy.deepcopy(request.model_dump(mode="json"))


def test_library_engine_service_and_plugin_return_equal_result(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    request = canonical_request
    library = harmonize_protein_inference_support(request)
    engine = M0306ProteinInferenceHarmonizationEngine().harmonize(request)
    service = M0306Service()
    service_result = service.execute(request)
    plugin = M0306Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))

    assert library == engine == service_result == plugin_result


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_service_denial_precedes_hostile_downstream_traversal(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    role: str,
    denied_state: str,
) -> None:
    context = _payload(canonical_request)["context"]
    context["references"][role]["state"] = denied_state

    with pytest.raises(ProteinInferenceHarmonizationAuthorizationError) as caught:
        M0306Service.validate_request(_HostileRequest(context))

    assert PRIVATE_CANARY not in str(caught.value)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m03_06_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-06/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"] == (
        f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-06:1.0.0:{name}"
    )


def test_api_and_cli_return_the_same_result_as_public_operation(
    tmp_path: Path,
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    payload = canonical_request.model_dump_json()
    request_path = tmp_path / "harmonization-request.json"
    request_path.write_text(payload, encoding="utf-8")
    expected = harmonize_protein_inference_support(canonical_request)

    with TestClient(create_app(tmp_path / "harmonization.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-06/harmonization",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        ProteinInferenceHarmonizationResult.model_validate_json(response.content, strict=True)
        == expected
    )
    assert (
        ProteinInferenceHarmonizationResult.model_validate_json(cli.stdout, strict=True) == expected
    )


def test_service_api_and_cli_replay_verify_reject_forged_and_duplicate_results(
    tmp_path: Path,
) -> None:
    request = build_scenario_request()
    expected = M0306Service().execute(request)
    result_path = tmp_path / "harmonization-result.json"
    result_path.write_bytes(expected.model_dump_json().encode("utf-8"))

    assert M0306Service().verify(result_path.read_bytes()) == expected
    forged = copy.deepcopy(expected.model_dump(mode="json"))
    forged["result_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError):
        M0306Service().verify(forged)
    duplicate = expected.model_dump_json().replace(
        '"result_id":', '"result_id":"duplicate","result_id":', 1
    )
    with pytest.raises(StrictJsonError):
        M0306Service().verify(duplicate)

    with TestClient(create_app(tmp_path / "verify.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-06/harmonization/verify",
            content=result_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_OK, response.text
    assert (
        ProteinInferenceHarmonizationResult.model_validate_json(response.content, strict=True)
        == expected
    )

    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "verify", str(result_path)],
    )
    assert cli.exit_code == 0, cli.output
    assert (
        ProteinInferenceHarmonizationResult.model_validate_json(cli.stdout, strict=True) == expected
    )
    assert len(result_path.read_bytes()) <= M0306_MAX_CANONICAL_RESULT_BYTES


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_api_and_cli_denial_is_sanitized_before_ledger_validation(
    tmp_path: Path,
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    role: str,
    denied_state: str,
) -> None:
    payload = _payload(canonical_request)
    payload["context"]["references"][role]["state"] = denied_state
    payload["support_ledger"] = PRIVATE_CANARY
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{role}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{role}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.json() == {
        "detail": "upstream controls do not authorize protein-inference support harmonization"
    }
    assert cli.exit_code == CLI_USAGE_ERROR
    assert PRIVATE_CANARY not in response.text + cli.output
    assert "Traceback" not in cli.output


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
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    mutation: str,
    expected_term: str,
) -> None:
    if mutation in {"duplicate", "nonfinite"}:
        serialized = canonical_request.model_dump_json()
        operation = '"operation":"harmonize_protein_inference_support"'
        if mutation == "duplicate":
            serialized = serialized.replace(operation, f"{operation},{operation}", 1)
        else:
            serialized = f'{serialized[:-1]},"{PRIVATE_CANARY}":NaN}}'
    else:
        payload = _payload(canonical_request)
        if mutation == "unknown":
            payload[PRIVATE_CANARY] = "must-not-be-reflected"
        else:
            payload["policy"]["max_units"] = "512"
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"strict-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert expected_term in cli.output.lower()
    assert PRIVATE_CANARY not in response.text + cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_distinguish_exact_four_mib_from_first_byte_past_limit(
    tmp_path: Path,
) -> None:
    exact = b"{" + b" " * (M0306_MAX_CANONICAL_REQUEST_BYTES - 1)
    oversized = exact + b" "
    exact_path = tmp_path / "exact-limit.json"
    oversized_path = tmp_path / "oversized.json"
    exact_path.write_bytes(exact)
    oversized_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "size.sqlite3")) as client:
        exact_api = client.post(
            "/v1/modules/M03-06/harmonization",
            content=exact,
            headers={"content-type": "application/json"},
        )
        oversized_api = client.post(
            "/v1/modules/M03-06/harmonization",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    exact_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(exact_path)],
    )
    oversized_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(oversized_path)],
    )

    assert len(exact) == M0306_MAX_CANONICAL_REQUEST_BYTES
    assert len(oversized) == M0306_MAX_CANONICAL_REQUEST_BYTES + 1
    assert exact_api.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert exact_api.json()["detail"][0]["type"] == "json_invalid_syntax"
    assert oversized_api.status_code == HTTP_CONTENT_TOO_LARGE
    assert oversized_api.json()["detail"] == "request body exceeds the byte limit"
    assert exact_cli.exit_code == CLI_USAGE_ERROR
    assert "json_invalid_syntax" in exact_cli.output
    assert oversized_cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in oversized_cli.output
    assert "Traceback" not in exact_cli.output + oversized_cli.output


def test_api_content_type_is_exact_but_accepts_json_charset(
    tmp_path: Path,
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    payload = canonical_request.model_dump_json()

    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        rejected = client.post(
            "/v1/modules/M03-06/harmonization",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        accepted = client.post(
            "/v1/modules/M03-06/harmonization",
            content=payload,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    assert rejected.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert rejected.json() == {"detail": "content-type must be application/json"}
    assert accepted.status_code == HTTP_OK, accepted.text


def test_invalid_schema_name_is_rejected_by_api_and_cli(tmp_path: Path) -> None:
    invalid_name = "not-a-harmonization-contract"

    with TestClient(create_app(tmp_path / "schema-invalid.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-06/{invalid_name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "export-schema", invalid_name],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["type"] == "literal_error"
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Invalid value" in cli.output
    assert "Traceback" not in cli.output


def test_cli_sanitizes_a_late_request_read_failure(
    tmp_path: Path,
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "unreadable-after-cli-validation.json"
    request_path.write_text(canonical_request.model_dump_json(), encoding="utf-8")

    def fail_read(_path: object, *, max_bytes: int | None = None) -> bytes:
        del max_bytes
        raise OSError(PRIVATE_CANARY)

    monkeypatch.setattr(cli_adapter, "read_bounded", fail_read)
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-harmonization", "harmonize", str(request_path)],
    )

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "unable to read or decode request document" in cli.output
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output
