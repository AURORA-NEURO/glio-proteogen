"""Black-box library, plugin, API, CLI, schema, and nonreflection checks for M04-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m04_06.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    M0406Plugin,
    M0406ProteoformHarmonizationEngine,
    M0406Service,
    harmonize_proteoform_analysis,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    engine as m0406_engine,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "target-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
)
_DENIED_CONTROLS: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "withheld"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)
_HTTP_OK: Final = 200
_HTTP_FORBIDDEN: Final = 403
_HTTP_UNPROCESSABLE: Final = 422
_HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
_CLI_AUTHORIZATION_ERROR: Final = 2
_ADAPTER_PREPARE_CALL_COUNT: Final = 2


@pytest.fixture(scope="module")
def canonical_request() -> HarmonizeProteoformAnalysisRequest:
    return build_scenario_request("accepted")


def test_api_cli_and_library_export_identical_schema_inventory(tmp_path: Path) -> None:
    runner = CliRunner()
    with TestClient(create_app(tmp_path / "schemas.sqlite3")) as client:
        for name in _SCHEMA_NAMES:
            response = client.get(f"/v1/contracts/M04-06/{name}/schema")
            cli = runner.invoke(
                cli_app,
                ["proteoform-harmonization", "export-schema", name],
            )
            assert response.status_code == _HTTP_OK
            assert cli.exit_code == 0, cli.output
            assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)


def test_library_engine_service_plugin_api_and_cli_have_exact_parity(
    tmp_path: Path,
    canonical_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    serialized = canonical_json_bytes(canonical_request)
    request_path = tmp_path / "harmonization-request.json"
    request_path.write_bytes(serialized)
    service = M0406Service()
    plugin = M0406Plugin(service)
    token = plugin.validate(serialized)

    with TestClient(create_app(tmp_path / "parity.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteoformHarmonizationResult.model_validate_json(response.content, strict=True)
    cli_result = ProteoformHarmonizationResult.model_validate_json(cli.stdout, strict=True)
    expected = harmonize_proteoform_analysis(canonical_request)
    assert expected == M0406ProteoformHarmonizationEngine().harmonize(canonical_request)
    assert expected == service.execute(canonical_request)
    assert expected == plugin.run(token) == api_result == cli_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-06"


def test_api_and_cli_use_the_sealed_adapter_request_without_second_replay(
    tmp_path: Path,
    canonical_request: HarmonizeProteoformAnalysisRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serialized = canonical_json_bytes(canonical_request)
    request_path = tmp_path / "counted-request.json"
    request_path.write_bytes(serialized)
    original = m0406_engine._prepare_harmonization_request_candidate
    calls = 0

    def counted(candidate: object) -> object:
        nonlocal calls
        calls += 1
        return original(candidate)

    monkeypatch.setattr(m0406_engine, "_prepare_harmonization_request_candidate", counted)
    with TestClient(create_app(tmp_path / "counted.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )
    assert response.status_code == _HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert calls == _ADAPTER_PREPARE_CALL_COUNT


@pytest.mark.parametrize(("control", "state"), _DENIED_CONTROLS)
def test_api_and_cli_deny_controls_before_nested_validation_without_reflection(
    tmp_path: Path,
    canonical_request: HarmonizeProteoformAnalysisRequest,
    control: str,
    state: str,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["context"]["references"][control]["state"] = state
    payload["artifact_result"] = "artifact-result-recursive-canary"
    payload["support_ledger"] = "support-ledger-recursive-canary"
    serialized = json.dumps(payload).encode()
    request_path = tmp_path / f"denied-{control}.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / f"denied-{control}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )

    combined = response.text + cli.output
    assert response.status_code == _HTTP_FORBIDDEN
    assert cli.exit_code == _CLI_AUTHORIZATION_ERROR
    assert "recursive-canary" not in combined
    assert "artifact_result" not in combined
    assert "support_ledger" not in combined


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "coercion"])
def test_api_and_cli_reject_non_strict_json_shapes(
    tmp_path: Path,
    canonical_request: HarmonizeProteoformAnalysisRequest,
    mutation: str,
) -> None:
    if mutation == "duplicate":
        canonical = canonical_json_bytes(canonical_request)
        serialized = b'{"operation":"harmonize_proteoform_analysis",' + canonical[1:]
    else:
        payload = canonical_request.model_dump(mode="json")
        if mutation == "unknown":
            payload["recursive_canary"] = True
        else:
            payload["contract_version"] = 1
        serialized = canonical_json_bytes(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / f"{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert cli.exit_code in {1, 2}
    assert "recursive_canary" not in response.text + cli.output


def test_api_rejects_wrong_media_type(
    tmp_path: Path,
    canonical_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=canonical_json_bytes(canonical_request),
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == _HTTP_UNSUPPORTED_MEDIA_TYPE
