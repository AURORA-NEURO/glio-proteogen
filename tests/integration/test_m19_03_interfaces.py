"""Black-box API, CLI and plugin parity for M19-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_03 import (
    M1903_MAX_CANONICAL_REQUEST_BYTES,
    M1903_MAX_CANONICAL_RESULT_BYTES,
    FuseProteotypeEvidenceRequest,
    ProteotypeIntegratedEvidenceResult,
    contract_json_schema,
)
from glio_proteogen.contracts.m19_03.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_03_fusion_aggregation import (
    M1903Plugin,
    M1903Service,
)
from tests.contract.test_m19_03_adversarial import _request

if TYPE_CHECKING:
    from pathlib import Path

    from glio_proteogen.contracts.m19_03.schema import ContractName as M1903ContractName

pytestmark = pytest.mark.integration

HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
SCHEMA_NAMES: tuple[M1903ContractName, ...] = (
    "request",
    "output",
    "integrated-evidence",
    "source-contribution",
    "disagreement",
    "aggregation",
    "configuration",
    "finding",
)


def test_api_and_cli_export_identical_authority_bound_schemas(tmp_path: Path) -> None:
    for name in SCHEMA_NAMES:
        with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
            response = client.get(f"/v1/contracts/M19-03/{name}/schema")
        cli = CliRunner().invoke(cli_app, ["m1903-fusion", "export-schema", name])

        assert response.status_code == HTTP_OK
        assert cli.exit_code == 0, cli.output
        assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)
        assert response.json()["x-glio-contract"]["dossierSlice"].endswith(":6604-6644")


def test_api_cli_service_plugin_emit_exact_parity(tmp_path: Path) -> None:
    request: FuseProteotypeEvidenceRequest = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "fusion-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M19-03/fusion",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m1903-fusion", "fuse", str(request_path)])

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeIntegratedEvidenceResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    cli_result = ProteotypeIntegratedEvidenceResult.model_validate_json(cli.stdout, strict=True)
    service_result = M1903Service().fuse(request)
    plugin = M1903Plugin()
    assert service_result == plugin.run(request) == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-03"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.replay(api_result) == api_result


def test_api_rejects_non_json_and_missing_controls(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "errors.sqlite3")) as client:
        media = client.post("/v1/modules/M19-03/fusion", content=b"{}")
        missing = client.post(
            "/v1/modules/M19-03/fusion",
            json={"request_id": "request.m1903.bad"},
            headers={"content-type": "application/json"},
        )

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA
    assert missing.status_code in {400, 403, 422}
    assert "traceback" not in missing.text.lower()


def test_central_api_sanitizes_self_rehashed_replay_mutation(tmp_path: Path) -> None:
    result = M1903Service().fuse(_request())
    forged = result.model_copy(update={"human_review_required": True})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with TestClient(create_app(tmp_path / "replay.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-03/verify",
            content=canonical_json_bytes(forged.model_dump(mode="json")),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json() == {"detail": "M19-03 result verification failed"}


def test_central_api_accepts_result_between_request_and_result_ceilings(tmp_path: Path) -> None:
    result = M1903Service().fuse(_request())
    serialized = canonical_json_bytes(result.model_dump(mode="json"))
    target_size = M1903_MAX_CANONICAL_REQUEST_BYTES + 1
    assert target_size < M1903_MAX_CANONICAL_RESULT_BYTES
    padded = serialized + b" " * (target_size - len(serialized))

    with TestClient(create_app(tmp_path / "large-result.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-03/verify",
            content=padded,
            headers={"content-type": "application/json"},
        )

    assert len(padded) == target_size
    assert response.status_code == HTTP_OK, response.text
    assert (
        ProteotypeIntegratedEvidenceResult.model_validate_json(response.content, strict=True)
        == result
    )


def test_api_and_cli_abstain_on_prohibited_caller_claim(tmp_path: Path) -> None:
    request = _request().model_copy(update={"aggregate_values": ("kinase",)})
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "prohibited-fusion-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M19-03/fusion",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m1903-fusion", "fuse", str(request_path)])

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeIntegratedEvidenceResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    cli_result = ProteotypeIntegratedEvidenceResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.status == "abstained"
    assert api_result.integrated_evidence is None
    assert any(finding.code.value == "ownership_unclear" for finding in api_result.findings)
