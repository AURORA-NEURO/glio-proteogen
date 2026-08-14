"""Public parity and hostile authorization boundaries for M04-07."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final

import pytest
from evals.m04_07.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_07 import (
    M0407_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    M0407Plugin,
    M0407ProteoformSupportRouterEngine,
    M0407Service,
    ProteoformSupportAuthorizationError,
    route_proteoform_support,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
SCHEMA_NAMES: Final = (
    "request",
    "output",
    "prerequisites",
    "quality-receipt",
    "harmonization-receipt",
    "fact",
    "context-receipt",
    "profile",
    "policy",
    "envelope",
    "remediation",
    "dimension-assessment",
    "envelope-assessment",
    "abstention",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_CONTENT_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
PRIVATE_CANARY: Final = "PRIVATE_M0407_INTERFACE_CANARY"
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
    """Expose only authorization context; every governed accessor is hostile."""

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
def canonical_request() -> RouteProteoformSupportRequest:
    return build_scenario_request()


def _payload(request: RouteProteoformSupportRequest) -> dict[str, Any]:
    return copy.deepcopy(request.model_dump(mode="json"))


def test_library_engine_service_and_plugin_return_equal_result(
    canonical_request: RouteProteoformSupportRequest,
) -> None:
    request = canonical_request
    library = route_proteoform_support(request)
    engine = M0407ProteoformSupportRouterEngine().route(request)
    service = M0407Service()
    service_result = service.execute(request)
    plugin = M0407Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))

    assert library == engine == service_result == plugin_result


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_service_denial_precedes_hostile_downstream_traversal(
    canonical_request: RouteProteoformSupportRequest,
    role: str,
    denied_state: str,
) -> None:
    context = _payload(canonical_request)["context"]
    context["references"][role]["state"] = denied_state

    with pytest.raises(ProteoformSupportAuthorizationError) as caught:
        M0407Service.validate_request(_HostileRequest(context))

    assert PRIVATE_CANARY not in str(caught.value)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m04_07_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-07/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"] == (
        f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-07:1.0.0:{name}"
    )


def test_api_and_cli_return_the_same_result_as_public_operation(
    tmp_path: Path,
    canonical_request: RouteProteoformSupportRequest,
) -> None:
    payload = canonical_request.model_dump_json()
    request_path = tmp_path / "support-route-request.json"
    request_path.write_text(payload, encoding="utf-8")
    expected = route_proteoform_support(canonical_request)

    with TestClient(create_app(tmp_path / "support-route.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-07/support-route",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "route", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        ProteoformSupportRouteResult.model_validate_json(response.content, strict=True) == expected
    )
    assert ProteoformSupportRouteResult.model_validate_json(cli.stdout, strict=True) == expected


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_api_and_cli_denial_is_sanitized_before_prerequisite_validation(
    tmp_path: Path,
    canonical_request: RouteProteoformSupportRequest,
    role: str,
    denied_state: str,
) -> None:
    payload = _payload(canonical_request)
    payload["context"]["references"][role]["state"] = denied_state
    payload["prerequisites"] = PRIVATE_CANARY
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{role}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{role}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-07/support-route",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "route", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.json() == {
        "detail": "upstream controls do not authorize proteoform support routing"
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
    canonical_request: RouteProteoformSupportRequest,
    mutation: str,
    expected_term: str,
) -> None:
    if mutation in {"duplicate", "nonfinite"}:
        serialized = canonical_request.model_dump_json()
        operation = '"operation":"route_proteoform_support"'
        if mutation == "duplicate":
            serialized = serialized.replace(operation, f"{operation},{operation}", 1)
        else:
            serialized = f'{serialized[:-1]},"{PRIVATE_CANARY}":NaN}}'
    else:
        payload = _payload(canonical_request)
        if mutation == "unknown":
            payload[PRIVATE_CANARY] = "must-not-be-reflected"
        else:
            payload["policy"]["max_envelopes"] = "1"
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"strict-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-07/support-route",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "route", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert expected_term in cli.output.lower()
    assert PRIVATE_CANARY not in response.text + cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_distinguish_exact_four_mib_from_first_byte_past_limit(
    tmp_path: Path,
) -> None:
    exact = b"{" + b" " * (M0407_MAX_CANONICAL_REQUEST_BYTES - 1)
    oversized = exact + b" "
    exact_path = tmp_path / "exact-limit.json"
    oversized_path = tmp_path / "oversized.json"
    exact_path.write_bytes(exact)
    oversized_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "size.sqlite3")) as client:
        exact_api = client.post(
            "/v1/modules/M04-07/support-route",
            content=exact,
            headers={"content-type": "application/json"},
        )
        oversized_api = client.post(
            "/v1/modules/M04-07/support-route",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    exact_cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "route", str(exact_path)],
    )
    oversized_cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "route", str(oversized_path)],
    )

    assert len(exact) == M0407_MAX_CANONICAL_REQUEST_BYTES
    assert len(oversized) == M0407_MAX_CANONICAL_REQUEST_BYTES + 1
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
    canonical_request: RouteProteoformSupportRequest,
) -> None:
    payload = canonical_request.model_dump_json()

    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        rejected = client.post(
            "/v1/modules/M04-07/support-route",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        accepted = client.post(
            "/v1/modules/M04-07/support-route",
            content=payload,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    assert rejected.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert rejected.json() == {"detail": "content-type must be application/json"}
    assert accepted.status_code == HTTP_OK, accepted.text


def test_invalid_schema_name_is_rejected_by_api_and_cli(tmp_path: Path) -> None:
    invalid_name = "not-a-support-contract"

    with TestClient(create_app(tmp_path / "schema-invalid.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-07/{invalid_name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-support", "export-schema", invalid_name],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["type"] == "literal_error"
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Invalid value" in cli.output
    assert "Traceback" not in cli.output


def test_cli_sanitizes_a_late_request_read_failure(
    tmp_path: Path,
    canonical_request: RouteProteoformSupportRequest,
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
        ["proteoform-support", "route", str(request_path)],
    )

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "unable to read or decode request document" in cli.output
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output
