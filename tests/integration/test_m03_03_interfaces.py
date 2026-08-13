"""Black-box schema, CLI, filesystem, and parity tests for M03-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m03_03 import run as m0303_eval
from evals.m03_03.run import build_scenario
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_03 import ProteinInferenceRawAdmissionResult
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "source",
    "protocol-receipt",
    "lineage-receipt",
    "raw-input",
    "receipt",
)
HTTP_OK: Final = 200


def test_locked_m03_03_executable_corpus_passes(tmp_path: Path) -> None:
    """Keep all 77 public-runtime oracles inside the repository coverage gate."""

    report = tmp_path / "m03-03-eval.json"

    assert m0303_eval.main(["--output", str(report)]) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["checks"][-1]["detail"].endswith("missing=none;extra=none")


def _write_capsule(root: Path) -> tuple[Path, Path, ProteinInferenceRawAdmissionResult]:
    scenario = build_scenario()
    request_path = root / "request.json"
    source_directory = root / "sources"
    source_directory.mkdir()
    request_path.write_text(scenario.request.model_dump_json(), encoding="utf-8")
    for source_id, payload in scenario.sources.items():
        (source_directory / source_id).write_bytes(payload)
    result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    return request_path, source_directory, result


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m03_03_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-03/{name}/schema")
        absent = client.post("/v1/modules/M03-03/raw-ingestion", json={})
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-raw", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"].endswith(f":{name}")
    assert absent.status_code in {404, 405}


def test_cli_ingest_equals_public_operation(tmp_path: Path) -> None:
    request_path, source_directory, expected = _write_capsule(tmp_path)
    result = CliRunner().invoke(
        cli_app,
        ["protein-inference-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert result.exit_code == 0, result.output
    assert (
        ProteinInferenceRawAdmissionResult.model_validate_json(
            result.stdout,
            strict=True,
        )
        == expected
    )


def test_cli_rejects_symlink_before_ingestion(tmp_path: Path) -> None:
    request_path, source_directory, _ = _write_capsule(tmp_path)
    target = source_directory / "source.spectra.mzml"
    replacement = source_directory / "spectra-target.mzml"
    target.replace(replacement)
    try:
        target.symlink_to(replacement)
    except OSError as error:
        pytest.skip(f"platform cannot create a test symlink: {error}")

    result = CliRunner().invoke(
        cli_app,
        ["protein-inference-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert result.exit_code == 1
    assert "link or reparse point" in result.output
    assert "Traceback" not in result.output
