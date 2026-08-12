"""Black-box checks for the thin M01-08 transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m01_08.run import build_scenario
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_08 import PackageVerification, ReleasePackagingResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = ("request", "output", "policy", "manifest")
HTTP_OK: Final = 200


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-08/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["release", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def _write_release_inputs(
    tmp_path: Path,
    case: str,
) -> tuple[Path, Path, Path, dict[str, bytes]]:
    request, files = build_scenario(case)
    request_path = tmp_path / f"{case}.json"
    source = tmp_path / f"{case}-source"
    output = tmp_path / f"{case}.tar"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    for name, content in files.items():
        target = source.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return request_path, source, output, files


def test_cli_builds_and_verifies_one_canonical_release(tmp_path: Path) -> None:
    request_path, source, package, _files = _write_release_inputs(tmp_path, "canonical")

    built = CliRunner().invoke(
        cli_app,
        ["release", "build", str(request_path), str(source), "--output", str(package)],
    )

    assert built.exit_code == 0, built.output
    assert package.is_file()
    result = ReleasePackagingResult.model_validate_json(built.stdout, strict=True)
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")

    verified = CliRunner().invoke(
        cli_app,
        ["release", "verify", str(result_path), str(package)],
    )
    assert verified.exit_code == 0, verified.output
    assert PackageVerification.model_validate_json(verified.stdout, strict=True).verified


def test_cli_never_publishes_a_quarantined_package(tmp_path: Path) -> None:
    request_path, source, package, _files = _write_release_inputs(tmp_path, "missing_receipt")

    built = CliRunner().invoke(
        cli_app,
        ["release", "build", str(request_path), str(source), "--output", str(package)],
    )

    assert built.exit_code == 1
    assert not package.exists()
    result = ReleasePackagingResult.model_validate_json(built.stdout, strict=True)
    assert result.disposition.value == "quarantined"


def test_cli_rejects_a_symlinked_artifact_source(tmp_path: Path) -> None:
    request_path, source, package, files = _write_release_inputs(tmp_path, "canonical")
    artifact_path = next(iter(files))
    artifact = source.joinpath(*artifact_path.split("/"))
    outside = tmp_path / "outside.bin"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    try:
        artifact.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    built = CliRunner().invoke(
        cli_app,
        ["release", "build", str(request_path), str(source), "--output", str(package)],
    )

    assert built.exit_code == 1
    assert "symbolic link" in built.output
    assert not package.exists()
