"""Black-box FastAPI, Typer and plugin parity for M19-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_04 import (
    AdaptProteotypeIntendedUseRequest,
    ProteotypeIntendedUseAdapterResult,
    contract_json_schema,
)
from glio_proteogen.contracts.m19_04.schema import ContractName  # noqa: TC001
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_04_intended_use_adapter import (
    M1904Plugin,
    M1904Service,
)
from tests.runtime.test_m19_04_intended_use import _supported_request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "registration",
    "claim-ceiling",
    "display-semantics",
    "policy-decision",
    "intended-use-object",
    "finding",
)


def test_api_and_cli_export_identical_authority_bound_schemas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    for name in SCHEMA_NAMES:
        with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
            response = client.get(f"/v1/contracts/M19-04/{name}/schema")
        cli = CliRunner().invoke(cli_app, ["m1904-intended-use", "export-schema", name])

        assert response.status_code == HTTP_OK
        assert cli.exit_code == 0, cli.output
        assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)
        assert response.json()["x-glio-contract"]["dossierSlice"].endswith(":6648-6688")


def test_api_cli_service_plugin_emit_exact_parity(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request: AdaptProteotypeIntendedUseRequest = _supported_request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "intended-use-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M19-04/adapt",
            content=serialized,
            headers={"content-type": "application/json"},
        )
        api_result_response = client.post(
            "/v1/modules/M19-04/verify",
            content=api_response.content,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m1904-intended-use", "adapt", str(request_path)])

    assert api_response.status_code == HTTP_OK, api_response.text
    assert api_result_response.status_code == HTTP_OK, api_result_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeIntendedUseAdapterResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    verified_result = ProteotypeIntendedUseAdapterResult.model_validate_json(
        api_result_response.content,
        strict=True,
    )
    cli_result = ProteotypeIntendedUseAdapterResult.model_validate_json(cli.stdout, strict=True)
    service_result = M1904Service().adapt(request)
    plugin = M1904Plugin()
    assert service_result == plugin.run(request) == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-04"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.replay(verified_result) == verified_result

    result_path = tmp_path / "intended-use-result.json"
    result_path.write_bytes(api_response.content)
    verify_cli = CliRunner().invoke(cli_app, ["m1904-intended-use", "verify", str(result_path)])
    assert verify_cli.exit_code == 0, verify_cli.output
    assert (
        ProteotypeIntendedUseAdapterResult.model_validate_json(
            verify_cli.stdout,
            strict=True,
        )
        == api_result
    )


def test_api_rejects_non_json_missing_controls_and_tampered_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _supported_request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "errors.sqlite3")) as client:
        media = client.post("/v1/modules/M19-04/adapt", content=serialized)
        missing = client.post(
            "/v1/modules/M19-04/adapt",
            json={"request_id": "request.m1904.bad"},
            headers={"content-type": "application/json"},
        )
        successful = client.post(
            "/v1/modules/M19-04/adapt",
            content=serialized,
            headers={"content-type": "application/json"},
        )
        payload = successful.json()
        payload["result_id"] = "result.tampered"
        tampered = client.post(
            "/v1/modules/M19-04/verify",
            json=payload,
            headers={"content-type": "application/json"},
        )

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA
    assert missing.status_code in {400, 403, 422}
    assert "traceback" not in missing.text.lower()
    assert tampered.status_code == HTTP_UNPROCESSABLE
    assert "traceback" not in tampered.text.lower()


def test_api_and_cli_abstain_on_prohibited_registration_claim(tmp_path: Path) -> None:
    request = _supported_request()
    registration = request.registration.model_copy(update={"audience": "kinase"})
    request = request.model_copy(update={"registration": registration})
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "prohibited-intended-use-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M19-04/adapt",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m1904-intended-use", "adapt", str(request_path)])

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeIntendedUseAdapterResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    cli_result = ProteotypeIntendedUseAdapterResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.status == "abstained"
    assert api_result.adapted_object is None
    assert api_result.policy_decision.status == "blocked"
    assert api_result.policy_decision.reason_code == "audience_unsupported"
