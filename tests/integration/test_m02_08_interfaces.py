"""Black-box interface checks for M02-08 identification release packaging."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Final

import pytest
from evals.m02_08.run import (
    DeterministicNonCryptographicVerifier,
    build_representative_release_fixture,
)
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_08 import (
    IdentificationQcReleaseResult,
    IdentificationReleaseDisposition,
    IdentificationReleaseVerification,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    IdentificationReleaseAuthorizationError,
    IdentificationReleaseSubmission,
    M0208Plugin,
    M0208Service,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404
HTTP_METHOD_NOT_ALLOWED: Final = 405
SCHEMAS = (
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "verification",
    "signature",
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_api_and_cli_export_identical_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-08/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["identification-release", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["x-glio-contract"]["signatureAuthorityOwnedExternally"] is True


def test_api_exposes_no_release_execution_route(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post("/v1/modules/M02-08/release", json={})

    assert response.status_code in {HTTP_NOT_FOUND, HTTP_METHOD_NOT_ALLOWED}


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, object]:
    fixture, verifier = build_representative_release_fixture()
    request_path = tmp_path / "request.json"
    source = tmp_path / "source"
    output = tmp_path / "identification-release.tar"
    request_path.write_text(fixture.request.model_dump_json(), encoding="utf-8")
    for name, content in fixture.artifacts.items():
        target = source.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return request_path, source, output, (fixture, verifier)


def test_default_cli_build_quarantines_and_never_creates_output(tmp_path: Path) -> None:
    request_path, source, output, _fixture = _write_fixture(tmp_path)

    built = CliRunner().invoke(
        cli_app,
        [
            "identification-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1, built.output
    assert not output.exists()
    result = IdentificationQcReleaseResult.model_validate_json(built.stdout, strict=True)
    assert result.disposition is IdentificationReleaseDisposition.QUARANTINED
    assert result.package_descriptor is None
    assert result.signature_verification.reason_code.value == "verifier_unavailable"


def test_library_service_and_plugin_release_with_explicit_verifier() -> None:
    fixture, verifier = build_representative_release_fixture()
    service = M0208Service(verifier)
    plugin = M0208Plugin(service)
    submission = IdentificationReleaseSubmission(
        fixture.request.model_dump_json(),
        fixture.artifacts,
        fixture.stages,
    )

    built = plugin.run(plugin.validate(submission))

    assert built.result.disposition is IdentificationReleaseDisposition.RELEASED
    assert built.package_bytes is not None
    assert service.verify(built.result, built.package_bytes).verified
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-08"
    assert isinstance(verifier, DeterministicNonCryptographicVerifier)


def test_cli_verify_checks_content_but_not_authenticity(tmp_path: Path) -> None:
    fixture, verifier = build_representative_release_fixture()
    built = M0208Service(verifier).build(fixture.request, fixture.artifacts, fixture.stages)
    assert built.package_bytes is not None
    result_path = tmp_path / "result.json"
    package_path = tmp_path / "package.tar"
    result_path.write_text(built.result.model_dump_json(), encoding="utf-8")
    package_path.write_bytes(built.package_bytes)

    verified = CliRunner().invoke(
        cli_app,
        ["identification-release", "verify", str(result_path), str(package_path)],
    )

    assert verified.exit_code == 1, verified.output
    receipt = IdentificationReleaseVerification.model_validate_json(
        verified.stdout,
        strict=True,
    )
    assert receipt.content_verified
    assert not receipt.authenticity_verified
    assert not receipt.verified
    assert receipt.reason_code.value == "verifier_unavailable"


@pytest.mark.parametrize("extra_kind", ["file", "directory"])
def test_cli_rejects_undeclared_source_entries(tmp_path: Path, extra_kind: str) -> None:
    request_path, source, output, _fixture = _write_fixture(tmp_path)
    extra = source / "undeclared"
    if extra_kind == "file":
        extra.write_bytes(b"extra")
    else:
        extra.mkdir()

    built = CliRunner().invoke(
        cli_app,
        [
            "identification-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert "exactly the declared artifact paths" in built.output
    assert not output.exists()


def test_cli_rejects_symlinked_stage_without_leaking_bytes(tmp_path: Path) -> None:
    request_path, source, output, fixture_and_verifier = _write_fixture(tmp_path)
    fixture, _verifier = fixture_and_verifier
    stage = next(
        item
        for item in fixture.request.artifacts
        if item.role.value == "m02_01_conformance"
    )
    target = source.joinpath(*stage.path.split("/"))
    outside = tmp_path / "PRIVATE_RELEASE_CANARY.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    built = CliRunner().invoke(
        cli_app,
        [
            "identification-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert "symbolic" in built.output
    assert "PRIVATE_RELEASE_CANARY" not in built.output
    assert not output.exists()


class _HostileTraversalError(AssertionError):
    pass


class _HostileMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise _HostileTraversalError(key)

    def __iter__(self) -> Iterator[str]:
        raise _HostileTraversalError

    def __len__(self) -> int:
        raise _HostileTraversalError


def test_service_and_plugin_authorize_before_hostile_mappings() -> None:
    fixture, _verifier = build_representative_release_fixture()
    payload = fixture.request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    hostile = _HostileMapping()
    service = M0208Service()

    with pytest.raises(IdentificationReleaseAuthorizationError):
        service.build(payload, hostile, hostile)
    with pytest.raises(IdentificationReleaseAuthorizationError):
        M0208Plugin(service).validate(IdentificationReleaseSubmission(payload, hostile, hostile))
