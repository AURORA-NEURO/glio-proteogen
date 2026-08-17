"""API/CLI parity and strict-ingress tests for M05-08."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m05_08 import (
    ContractName,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.api import (
    create_app,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.cli import (
    app as cli_app,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.service import (
    M0508Service,
)
from tests.modules.c05_ptm_localization.test_m05_08_release_packaging import (
    _valid_fixture,
    _Verifier,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema() -> None:
    contracts: tuple[ContractName, ...] = (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "signature",
        "quarantine",
        "verification",
        "transformation",
        "quality-decision",
    )
    assert tuple(contract_json_schemas()) == contracts
    runner = CliRunner()
    with TestClient(create_app()) as client:
        for name in contracts:
            api_schema = client.get(f"/v1/modules/M05-08/schemas/{name}")
            cli_schema = runner.invoke(cli_app, ["export-schema", name])
            assert api_schema.status_code == _HTTP_OK
            assert cli_schema.exit_code == 0
            assert api_schema.json() == json.loads(cli_schema.stdout)
            assert api_schema.json() == contract_json_schema(name)


def test_api_and_cli_validate_the_same_canonical_request(tmp_path: Path) -> None:
    request, _ = _valid_fixture()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))

    with TestClient(create_app()) as client:
        api = client.post(
            "/v1/modules/M05-08/validate",
            content=request_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_reject_duplicate_keys_without_leaking_input(tmp_path: Path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)

    with TestClient(create_app()) as client:
        api = client.post("/v1/modules/M05-08/validate", content=payload)
    cli = CliRunner().invoke(cli_app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in api.text
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


def test_api_build_quarantines_without_default_signing_verifier() -> None:
    request, artifacts = _valid_fixture()
    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii") for path, content in artifacts.items()
        },
    }

    with TestClient(create_app()) as client:
        response = client.post("/v1/modules/M05-08/build", json=envelope)

    assert response.status_code == _HTTP_OK
    assert response.json()["package"] is None
    assert response.json()["result"]["disposition"] == "quarantined"


def test_cli_build_matches_api_quarantine_result(tmp_path: Path) -> None:
    request, artifacts = _valid_fixture()
    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii") for path, content in artifacts.items()
        },
    }
    request_path = tmp_path / "build.json"
    request_path.write_bytes(canonical_json_bytes(envelope))

    with TestClient(create_app()) as client:
        api = client.post("/v1/modules/M05-08/build", content=request_path.read_bytes())
    cli = CliRunner().invoke(cli_app, ["build", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 1
    api_payload = api.json()
    cli_payload = json.loads(cli.stdout)
    assert api_payload["package"] == cli_payload["package"]
    assert api_payload["result"]["request_digest"] == cli_payload["result"]["request_digest"]
    assert api_payload["result"]["disposition"] == cli_payload["result"]["disposition"]
    assert (
        api_payload["result"]["quarantine_reasons"] == cli_payload["result"]["quarantine_reasons"]
    )


def test_api_strict_errors_cover_unknown_schema_build_and_authorization() -> None:
    request, _artifacts = _valid_fixture()
    with TestClient(create_app()) as client:
        unknown = client.get("/v1/modules/M05-08/schemas/unknown")
        malformed_validate = client.post(
            "/v1/modules/M05-08/validate",
            content=b"[]",
            headers={"content-type": "application/json"},
        )
        malformed_build = client.post("/v1/modules/M05-08/build", json={})
        invalid_artifact = client.post(
            "/v1/modules/M05-08/build",
            json={
                "request": request.model_dump(mode="json"),
                "artifacts": {"parent/variant-peptide.json": "not-base64!"},
            },
        )
        missing_artifacts = client.post(
            "/v1/modules/M05-08/build",
            json={"request": request.model_dump(mode="json"), "artifacts": {}},
        )
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert malformed_validate.status_code == _HTTP_UNPROCESSABLE
    assert malformed_build.status_code == _HTTP_UNPROCESSABLE
    assert invalid_artifact.status_code == _HTTP_UNPROCESSABLE
    assert missing_artifacts.status_code == _HTTP_UNPROCESSABLE

    withheld_refs = request.context.references.model_copy(
        update={
            "consent": request.context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    withheld = request.model_copy(
        update={"context": request.context.model_copy(update={"references": withheld_refs})}
    )
    with TestClient(create_app()) as client:
        denied = client.post(
            "/v1/modules/M05-08/validate",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert denied.status_code == _HTTP_FORBIDDEN
    assert "authorization denied" in denied.text


def test_cli_strict_errors_and_output_lifecycle(tmp_path: Path) -> None:
    request, artifacts = _valid_fixture()
    invalid_request = tmp_path / "invalid.json"
    invalid_request.write_bytes(b"{}")
    invalid_result = CliRunner().invoke(cli_app, ["validate", str(invalid_request)])
    unknown_schema = CliRunner().invoke(cli_app, ["export-schema", "unknown"])
    assert invalid_result.exit_code != 0
    assert unknown_schema.exit_code != 0

    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii") for path, content in artifacts.items()
        },
    }
    build_input = tmp_path / "build-output.json"
    build_input.write_bytes(canonical_json_bytes(envelope))
    output = tmp_path / "result.json"
    first = CliRunner().invoke(cli_app, ["build", str(build_input), "--output", str(output)])
    second = CliRunner().invoke(cli_app, ["build", str(build_input), "--output", str(output)])
    assert first.exit_code == 1
    assert output.exists()
    assert second.exit_code != 0

    invalid_envelope = tmp_path / "invalid-envelope.json"
    invalid_envelope.write_bytes(canonical_json_bytes({"request": request.model_dump(mode="json")}))
    invalid_build = CliRunner().invoke(cli_app, ["build", str(invalid_envelope)])
    assert invalid_build.exit_code != 0


def test_api_release_path_emits_package_with_injected_verifier() -> None:
    request, artifacts = _valid_fixture()

    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii") for path, content in artifacts.items()
        },
    }
    with TestClient(create_app(M0508Service(verifier=_Verifier()))) as client:
        response = client.post("/v1/modules/M05-08/build", json=envelope)
    assert response.status_code == _HTTP_OK
    assert response.json()["result"]["disposition"] == "released"
    assert response.json()["package"] is not None
