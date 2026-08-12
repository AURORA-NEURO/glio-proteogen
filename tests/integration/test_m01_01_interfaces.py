"""Black-box parity evidence for the M01-01 API and CLI."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from pydantic import TypeAdapter
from starlette.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_module
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    ProtocolSchemaReceipt,
)
from glio_proteogen.kernel.models import ConsentState, ControlRole
from glio_proteogen.kernel.strict_json import MAX_VALIDATION_ERRORS
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainIntegrityError,
    ChainVerification,
    IdempotencyConflictError,
    M0101EventStore,
    PayloadTooLargeError,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.plugin import (
    M0101Plugin,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    ConsentAuthorizationError,
    M0101Service,
    ProtocolSchemaValidationError,
    UpstreamControlAuthorizationError,
)
from tests.m01_01_support import FIXTURE_DIRECTORY, load_json

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

    from glio_proteogen.contracts.m01_01.schema import ContractName

pytestmark = [
    pytest.mark.integration,
]

HTTP_OK = 200
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_FORBIDDEN = 403
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_SERVICE_UNAVAILABLE = 503
TWO_EVENT_LEDGER = 2
CLI_SERVICE_FAILURE = 1
CLI_INVALID_INPUT = 2

PUBLIC_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "register-request",
    "evaluate-request",
    "protocol-schema",
    "metadata-document",
    "protocol-receipt",
    "conformance-profile",
)


def _successful_cli(result: Result) -> bytes:
    assert result.exit_code == 0, result.output
    assert result.exception is None
    return result.stdout_bytes


def _duplicate_operation_request() -> bytes:
    source = (FIXTURE_DIRECTORY / "register_minimal.valid.json").read_text(encoding="utf-8")
    operation = '"operation": "register",'
    assert source.count(operation) == 1
    return source.replace(operation, f"{operation}\n  {operation}", 1).encode("utf-8")


def test_api_and_cli_produce_equivalent_typed_outputs(tmp_path: Path) -> None:
    registration_payload = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    evaluation_payload = load_json(FIXTURE_DIRECTORY / "evaluate_conformant.valid.json")
    api_database = tmp_path / "api.sqlite3"
    cli_database = tmp_path / "cli.sqlite3"

    with TestClient(create_app(api_database)) as client:
        api_registration = client.post(
            "/v1/modules/M01-01/protocols",
            json=registration_payload,
        )
        api_evaluation = client.post(
            "/v1/modules/M01-01/conformance",
            json=evaluation_payload,
        )
        api_lookup = client.get(
            "/v1/modules/M01-01/protocols/protocol.synthetic/1.0.0"
        )
        api_verification = client.get("/v1/modules/M01-01/events/verify")

    assert api_registration.status_code == HTTP_OK
    assert api_evaluation.status_code == HTTP_OK
    assert api_lookup.status_code == HTTP_OK
    assert api_verification.status_code == HTTP_OK

    runner = CliRunner()
    cli_registration = _successful_cli(
        runner.invoke(
            cli_app,
            [
                "protocol",
                "register",
                str(FIXTURE_DIRECTORY / "register_minimal.valid.json"),
                "--database",
                str(cli_database),
            ],
        )
    )
    cli_evaluation = _successful_cli(
        runner.invoke(
            cli_app,
            [
                "protocol",
                "evaluate",
                str(FIXTURE_DIRECTORY / "evaluate_conformant.valid.json"),
                "--database",
                str(cli_database),
            ],
        )
    )
    cli_lookup = _successful_cli(
        runner.invoke(
            cli_app,
            [
                "protocol",
                "get",
                "protocol.synthetic",
                "1.0.0",
                "--database",
                str(cli_database),
            ],
        )
    )
    cli_verification = _successful_cli(
        runner.invoke(
            cli_app,
            ["protocol", "verify-ledger", "--database", str(cli_database)],
        )
    )

    receipt_adapter = TypeAdapter(ProtocolSchemaReceipt)
    profile_adapter = TypeAdapter(ConformanceProfile)
    verification_adapter = TypeAdapter(ChainVerification)
    api_receipt = receipt_adapter.validate_json(api_registration.content, strict=True)
    cli_receipt = receipt_adapter.validate_json(cli_registration, strict=True)
    api_profile = profile_adapter.validate_json(api_evaluation.content, strict=True)
    cli_profile = profile_adapter.validate_json(cli_evaluation, strict=True)
    api_chain = verification_adapter.validate_json(api_verification.content, strict=True)
    cli_chain = verification_adapter.validate_json(cli_verification, strict=True)

    assert api_receipt == cli_receipt
    assert receipt_adapter.validate_json(api_lookup.content, strict=True) == api_receipt
    assert receipt_adapter.validate_json(cli_lookup, strict=True) == cli_receipt
    assert api_profile == cli_profile
    assert api_chain == cli_chain
    assert api_chain.valid is True
    assert api_chain.event_count == TWO_EVENT_LEDGER


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_api_and_cli_export_the_same_contract_schema(
    tmp_path: Path,
    name: ContractName,
) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-01/{name}/schema")
    cli_result = CliRunner().invoke(cli_app, ["export-schema", name])

    assert response.status_code == HTTP_OK
    assert response.json() == json.loads(_successful_cli(cli_result))


def test_reordered_protocol_and_document_requests_are_exact_replays(tmp_path: Path) -> None:
    registration = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    evaluation = load_json(FIXTURE_DIRECTORY / "evaluate_conformant.valid.json")
    reordered_registration = deepcopy(registration)
    reordered_evaluation = deepcopy(evaluation)
    schema = reordered_registration["protocol_schema"]
    for field in schema["fields"]:
        field.get("allowed_units", []).reverse()
        field.get("allowed_missingness", []).reverse()
    for vocabulary in schema["vocabularies"]:
        vocabulary["terms"].reverse()
    for rule in schema["compatibility_rules"]:
        for predicate_group in ("when_all", "require_all"):
            for predicate in rule[predicate_group]:
                predicate.get("values", []).reverse()
            rule[predicate_group].reverse()
    for collection in (
        "assay_versions",
        "specimen_versions",
        "fields",
        "vocabularies",
        "units",
        "compatibility_rules",
        "limitations",
    ):
        schema[collection].reverse()
    for entry in reordered_evaluation["document"]["entries"]:
        entry["values"].reverse()
    reordered_evaluation["document"]["entries"].reverse()

    with TestClient(create_app(tmp_path / "order-invariance.sqlite3")) as client:
        first_registration = client.post(
            "/v1/modules/M01-01/protocols",
            json=registration,
        )
        replayed_registration = client.post(
            "/v1/modules/M01-01/protocols",
            json=reordered_registration,
        )
        first_evaluation = client.post(
            "/v1/modules/M01-01/conformance",
            json=evaluation,
        )
        replayed_evaluation = client.post(
            "/v1/modules/M01-01/conformance",
            json=reordered_evaluation,
        )
        verification = client.get("/v1/modules/M01-01/events/verify")

    assert (
        first_registration.status_code
        == replayed_registration.status_code
        == HTTP_OK
    )
    assert first_evaluation.status_code == replayed_evaluation.status_code == HTTP_OK
    assert first_registration.json() == replayed_registration.json()
    assert first_evaluation.json() == replayed_evaluation.json()
    assert verification.json()["event_count"] == TWO_EVENT_LEDGER


def test_api_health_media_type_validation_and_not_found_paths(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api-errors.sqlite3")) as client:
        health = client.get("/healthz")
        readiness = client.get("/readyz")
        unsupported_media_type = client.post(
            "/v1/modules/M01-01/protocols",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        invalid_contract = client.post(
            "/v1/modules/M01-01/protocols",
            content=b"{}",
            headers={"content-type": "application/json; charset=utf-8"},
        )
        not_found = client.get(
            "/v1/modules/M01-01/protocols/protocol.synthetic/9.9.9"
        )

    assert health.json() == {"status": "alive", "module": "GLIO-PROTEOGEN-M01-01"}
    assert readiness.status_code == HTTP_OK
    assert readiness.json()["valid"] is True
    assert readiness.json()["event_count"] == 0
    assert unsupported_media_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert unsupported_media_type.json() == {
        "detail": "content-type must be application/json"
    }
    assert invalid_contract.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert all(item["loc"][0] == "body" for item in invalid_contract.json()["detail"])
    assert not_found.status_code == HTTP_NOT_FOUND
    assert "is not registered" in not_found.json()["detail"]


def test_api_validation_errors_are_bounded_and_never_echo_unknown_fields(
    tmp_path: Path,
) -> None:
    payload = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    canary_prefix = "submitted-field-canary-"
    canary_value = "submitted-value-canary-" + ("Q" * 16)
    for index in range(MAX_VALIDATION_ERRORS + 50):
        payload[f"{canary_prefix}{index:03}"] = canary_value

    with TestClient(create_app(tmp_path / "bounded-errors.sqlite3")) as client:
        response = client.post("/v1/modules/M01-01/protocols", json=payload)

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    details = response.json()["detail"]
    assert len(details) == MAX_VALIDATION_ERRORS
    assert details[-1] == {
        "type": "validation_errors_truncated",
        "loc": ["body"],
        "msg": "Additional validation errors were omitted at the deterministic limit.",
    }
    rendered = json.dumps(details)
    assert canary_prefix not in rendered
    assert canary_value not in rendered


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (IdempotencyConflictError("synthetic conflict"), HTTP_CONFLICT),
        (PayloadTooLargeError("synthetic payload ceiling"), HTTP_PAYLOAD_TOO_LARGE),
        (ConsentAuthorizationError(ConsentState.REVOKED), HTTP_FORBIDDEN),
        (
            UpstreamControlAuthorizationError(ControlRole.QUALITY),
            HTTP_FORBIDDEN,
        ),
        (ProtocolSchemaValidationError(()), HTTP_UNPROCESSABLE_CONTENT),
        (ChainIntegrityError("synthetic chain failure"), HTTP_SERVICE_UNAVAILABLE),
    ],
)
def test_api_maps_typed_service_failures_without_leaking_tracebacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    def fail(_service: M0101Service, _request: object) -> ProtocolSchemaReceipt:
        raise error

    monkeypatch.setattr(M0101Service, "register", fail)
    payload = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    with TestClient(create_app(tmp_path / f"api-{expected_status}.sqlite3")) as client:
        response = client.post("/v1/modules/M01-01/protocols", json=payload)

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)
    if isinstance(error, ProtocolSchemaValidationError):
        assert response.json()["issues"] == []


def test_cli_invalid_and_service_failure_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    invalid = runner.invoke(
        cli_app,
        [
            "protocol",
            "register",
            str(FIXTURE_DIRECTORY / "unknown_operation.invalid.json"),
            "--database",
            str(tmp_path / "invalid.sqlite3"),
        ],
    )

    def registration_failure(
        _service: M0101Service,
        _request: object,
    ) -> ProtocolSchemaReceipt:
        raise IdempotencyConflictError("conflict")

    monkeypatch.setattr(M0101Service, "register", registration_failure)
    registration = runner.invoke(
        cli_app,
        [
            "protocol",
            "register",
            str(FIXTURE_DIRECTORY / "register_minimal.valid.json"),
            "--database",
            str(tmp_path / "registration-error.sqlite3"),
        ],
    )

    assert invalid.exit_code == CLI_INVALID_INPUT
    assert "invalid request:" in invalid.output
    assert registration.exit_code == CLI_SERVICE_FAILURE
    assert "registration failed: conflict" in registration.output


@pytest.mark.parametrize(
    ("reference", "state", "expected_detail"),
    [
        (
            "consent",
            "revoked",
            "consent decision does not authorize this operation",
        ),
        (
            "quality",
            "rejected",
            "upstream quality decision does not authorize this operation",
        ),
    ],
)
def test_api_and_cli_share_fail_closed_upstream_authorization_semantics(
    tmp_path: Path,
    reference: str,
    state: str,
    expected_detail: str,
) -> None:
    payload = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    payload["context"]["references"][reference]["state"] = state
    request_path = tmp_path / f"{reference}-denied.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    api_database = tmp_path / f"{reference}-api.sqlite3"
    cli_database = tmp_path / f"{reference}-cli.sqlite3"

    with TestClient(create_app(api_database)) as client:
        api_response = client.post("/v1/modules/M01-01/protocols", json=payload)
    cli_result = CliRunner().invoke(
        cli_app,
        [
            "protocol",
            "register",
            str(request_path),
            "--database",
            str(cli_database),
        ],
    )

    assert api_response.status_code == HTTP_FORBIDDEN
    assert api_response.json() == {"detail": expected_detail}
    assert cli_result.exit_code == CLI_SERVICE_FAILURE
    assert cli_result.output.strip() == f"registration failed: {expected_detail}"
    for database in (api_database, cli_database):
        store = M0101EventStore(database)
        try:
            verification = store.verify_event_chain()
        finally:
            store.close()
        assert verification.valid is True
        assert verification.event_count == 0


def test_cli_validation_diagnostics_never_echo_submitted_secret_canary(
    tmp_path: Path,
) -> None:
    payload = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    canary = "!sensitive-canary-" + ("Q" * 32)
    payload["context"]["actor_id"] = canary
    request_path = tmp_path / "secret-canary.invalid.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        cli_app,
        [
            "protocol",
            "register",
            str(request_path),
            "--database",
            str(tmp_path / "secret-canary.sqlite3"),
        ],
    )

    assert result.exit_code == CLI_INVALID_INPUT
    assert "invalid request:" in result.output
    assert "string_pattern_mismatch" in result.output
    assert canary not in result.output
    assert "sensitive-canary" not in result.output
    assert "Q" * 8 not in result.output
    assert "input_value" not in result.output


def test_api_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    duplicate_request = _duplicate_operation_request()

    with TestClient(create_app(tmp_path / "duplicate-api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-01/protocols",
            content=duplicate_request,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "duplicate JSON object key" in json.dumps(response.json())


def test_cli_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    request_path = tmp_path / "duplicate-key.invalid.json"
    request_path.write_bytes(_duplicate_operation_request())

    response = CliRunner().invoke(
        cli_app,
        [
            "protocol",
            "register",
            str(request_path),
            "--database",
            str(tmp_path / "duplicate-cli.sqlite3"),
        ],
    )

    assert response.exit_code == CLI_INVALID_INPUT
    assert "duplicate JSON object key" in response.output


def test_plugin_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    with M0101Service(M0101EventStore(tmp_path / "duplicate-plugin.sqlite3")) as service:
        plugin = M0101Plugin(service)
        with pytest.raises(ValueError, match="duplicate JSON object key"):
            plugin.validate(_duplicate_operation_request())


def test_fixture_loader_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    request_path = tmp_path / "duplicate-key.invalid.json"
    request_path.write_bytes(_duplicate_operation_request())

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_json(request_path)


def test_cli_evaluate_lookup_and_verification_failure_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    evaluation = runner.invoke(
        cli_app,
        [
            "protocol",
            "evaluate",
            str(FIXTURE_DIRECTORY / "evaluate_conformant.valid.json"),
            "--database",
            str(tmp_path / "missing-evaluation.sqlite3"),
        ],
    )
    lookup = runner.invoke(
        cli_app,
        [
            "protocol",
            "get",
            "protocol.synthetic",
            "1.0.0",
            "--database",
            str(tmp_path / "missing-lookup.sqlite3"),
        ],
    )

    def invalid_chain(_service: M0101Service) -> ChainVerification:
        return ChainVerification(
            valid=False,
            event_count=0,
            head_digest=f"sha256:{'0' * 64}",
            reason="synthetic verification failure",
        )

    monkeypatch.setattr(M0101Service, "verify_event_chain", invalid_chain)
    invalid_verification = runner.invoke(
        cli_app,
        [
            "protocol",
            "verify-ledger",
            "--database",
            str(tmp_path / "invalid-ledger.sqlite3"),
        ],
    )

    assert evaluation.exit_code == CLI_SERVICE_FAILURE
    assert "evaluation failed:" in evaluation.output
    assert lookup.exit_code == CLI_SERVICE_FAILURE
    assert "lookup failed:" in lookup.output
    assert invalid_verification.exit_code == CLI_SERVICE_FAILURE
    assert '"valid":false' in invalid_verification.output


def test_cli_verification_exception_and_serve_adapter_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    def verification_failure(_service: M0101Service) -> ChainVerification:
        raise ChainIntegrityError("failure")

    monkeypatch.setattr(M0101Service, "verify_event_chain", verification_failure)
    verification = runner.invoke(
        cli_app,
        [
            "protocol",
            "verify-ledger",
            "--database",
            str(tmp_path / "verification-exception.sqlite3"),
        ],
    )
    sentinel_app = object()
    run = Mock()
    monkeypatch.setattr(cli_module, "create_app", lambda _database: sentinel_app)
    monkeypatch.setattr(cli_module.uvicorn, "run", run)
    serve = runner.invoke(
        cli_app,
        [
            "serve",
            "--database",
            str(tmp_path / "serve.sqlite3"),
            "--host",
            "127.0.0.2",
            "--port",
            "9001",
        ],
    )

    assert verification.exit_code == CLI_SERVICE_FAILURE
    assert "verification failed: failure" in verification.output
    assert serve.exit_code == 0
    run.assert_called_once_with(sentinel_app, host="127.0.0.2", port=9001)
