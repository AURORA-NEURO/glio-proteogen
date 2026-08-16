"""Black-box API, CLI, schema, and filesystem parity checks for M05-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from evals.m05_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_04 import (
    PtmLocalizationQualityResult,
    contract_json_schemas,
    normalized_request,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    compute_ptm_localization_quality_metrics,
)

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_CONTENT = 422
CLI_USAGE_ERROR = 2


def test_api_executes_one_strict_admission_and_exports_all_schemas(tmp_path: Path) -> None:
    request = build_scenario_request()
    serialized = canonical_json_bytes(normalized_request(request))
    expected = compute_ptm_localization_quality_metrics(request)
    schemas = contract_json_schemas()
    with TestClient(create_app(tmp_path / "m0504-api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == HTTP_OK
        assert (
            PtmLocalizationQualityResult.model_validate_json(response.content, strict=True)
            == expected
        )
        for name, schema in schemas.items():
            exported = client.get(f"/v1/contracts/M05-04/{name}/schema")
            assert exported.status_code == HTTP_OK
            assert exported.json() == schema


def test_api_authorization_and_strict_json_fail_closed(tmp_path: Path) -> None:
    request = build_scenario_request()
    payload = cast("dict[str, object]", request.model_dump(mode="json"))
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    support = cast("dict[str, object]", references["support"])
    support["state"] = "rejected"
    duplicate = request.model_dump_json().replace(
        '"operation":"compute_ptm_localization_quality_metrics"',
        (
            '"operation":"compute_ptm_localization_quality_metrics",'
            '"operation":"compute_ptm_localization_quality_metrics"'
        ),
        1,
    )
    with TestClient(create_app(tmp_path / "m0504-rejections.sqlite3")) as client:
        denied = client.post(
            "/v1/modules/M05-04/quality-metric-computation",
            content=canonical_json_bytes(payload),
            headers={"content-type": "application/json"},
        )
        malformed = client.post(
            "/v1/modules/M05-04/quality-metric-computation",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    assert denied.status_code == HTTP_FORBIDDEN
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_result_schema_and_existing_output_refusal_are_exact(tmp_path: Path) -> None:
    request = build_scenario_request()
    expected = compute_ptm_localization_quality_metrics(request)
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(normalized_request(request)))
    runner = CliRunner()
    computed = runner.invoke(
        cli_app,
        [
            "ptm-localization-quality",
            "compute",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )
    assert computed.exit_code == 0
    assert (
        PtmLocalizationQualityResult.model_validate_json(output_path.read_bytes(), strict=True)
        == expected
    )
    existing = output_path.read_bytes()
    refused = runner.invoke(
        cli_app,
        [
            "ptm-localization-quality",
            "compute",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )
    assert refused.exit_code == 1
    assert output_path.read_bytes() == existing
    for name, schema in contract_json_schemas().items():
        exported = runner.invoke(
            cli_app,
            ["ptm-localization-quality", "export-schema", name],
        )
        assert exported.exit_code == 0
        assert json.loads(exported.stdout) == schema


def test_cli_rejects_duplicate_json_without_creating_output(tmp_path: Path) -> None:
    request = build_scenario_request()
    duplicate = request.model_dump_json().replace(
        '"operation":"compute_ptm_localization_quality_metrics"',
        (
            '"operation":"compute_ptm_localization_quality_metrics",'
            '"operation":"compute_ptm_localization_quality_metrics"'
        ),
        1,
    )
    request_path = tmp_path / "duplicate.json"
    output_path = tmp_path / "must-not-exist.json"
    request_path.write_text(duplicate, encoding="utf-8")
    result = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-quality",
            "compute",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == CLI_USAGE_ERROR
    assert not output_path.exists()
