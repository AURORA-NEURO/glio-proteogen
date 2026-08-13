"""Black-box interface checks for M03-08 protein-inference release packaging."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Final

import pytest
from evals.m03_08.run import (
    DeterministicNonCryptographicVerifier,
    Scenario,
    build_scenario,
)
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_08 import (
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleaseResult,
    ProteinInferenceReleaseVerification,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    M0308Plugin,
    M0308Service,
    ProteinInferenceReleaseAuthorizationError,
    ProteinInferenceReleaseSubmission,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404
HTTP_METHOD_NOT_ALLOWED: Final = 405
BUILD_AND_VERIFY_CALLS: Final = 2
CLI_INVALID_REQUEST: Final = 2
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
        response = client.get(f"/v1/contracts/M03-08/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-release", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["x-glio-contract"]["signatureAuthorityOwnedExternally"] is True


def test_api_exposes_no_binary_release_execution_route(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post("/v1/modules/M03-08/release", json={})

    assert response.status_code in {HTTP_NOT_FOUND, HTTP_METHOD_NOT_ALLOWED}


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Scenario]:
    scenario = build_scenario()
    request_path = tmp_path / "request.json"
    source = tmp_path / "source"
    output = tmp_path / "protein-inference-release.tar"
    request_path.write_text(scenario.request.model_dump_json(), encoding="utf-8")
    for name, content in scenario.artifacts.items():
        target = source.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return request_path, source, output, scenario


def test_default_cli_build_quarantines_and_never_creates_output(tmp_path: Path) -> None:
    request_path, source, output, _scenario = _write_fixture(tmp_path)

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1, built.output
    assert not output.exists()
    result = ProteinInferenceReleaseResult.model_validate_json(built.stdout, strict=True)
    assert result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
    assert result.package_descriptor is None
    assert result.signature_verification.reason_code.value == "verifier_unavailable"


def test_library_service_and_plugin_release_with_explicit_verifier() -> None:
    scenario = build_scenario()
    verifier = DeterministicNonCryptographicVerifier()
    service = M0308Service(verifier)
    plugin = M0308Plugin(service)
    submission = ProteinInferenceReleaseSubmission(
        scenario.request.model_dump_json(),
        scenario.artifacts,
        scenario.stages,
    )

    built = plugin.run(plugin.validate(submission))

    assert built.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
    assert built.package_bytes is not None
    assert service.verify(built.result, built.package_bytes).verified
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M03-08"
    assert len(verifier.calls) == BUILD_AND_VERIFY_CALLS


def test_cli_verify_checks_content_but_not_authenticity(tmp_path: Path) -> None:
    scenario = build_scenario()
    built = M0308Service(scenario.verifier).build(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
    )
    assert built.package_bytes is not None
    result_path = tmp_path / "result.json"
    package_path = tmp_path / "package.tar"
    result_path.write_text(built.result.model_dump_json(), encoding="utf-8")
    package_path.write_bytes(built.package_bytes)

    verified = CliRunner().invoke(
        cli_app,
        ["protein-inference-release", "verify", str(result_path), str(package_path)],
    )

    assert verified.exit_code == 1, verified.output
    receipt = ProteinInferenceReleaseVerification.model_validate_json(
        verified.stdout,
        strict=True,
    )
    assert receipt.content_verified
    assert not receipt.authenticity_verified
    assert not receipt.verified
    assert receipt.reason_code.value == "verifier_unavailable"


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
    scenario = build_scenario()
    payload = scenario.request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    hostile = _HostileMapping()
    service = M0308Service()

    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        service.build(payload, hostile, hostile)
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        M0308Plugin(service).validate(ProteinInferenceReleaseSubmission(payload, hostile, hostile))


@pytest.mark.parametrize(
    ("control", "denied_state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_all_seven_cli_authorization_denials_precede_source_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: str,
    denied_state: str,
) -> None:
    scenario = build_scenario()
    payload = scenario.request.model_dump(mode="json")
    payload["context"]["references"][control]["state"] = denied_state
    request_path = tmp_path / f"denied-{control}.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    traversals = 0

    def hostile_source(_path: Path) -> Path:
        nonlocal traversals
        traversals += 1
        raise _HostileTraversalError

    monkeypatch.setattr(
        cli_adapter,
        "_resolve_protein_inference_release_directory",
        hostile_source,
    )
    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(tmp_path),
            "--output",
            str(tmp_path / "release.tar"),
        ],
    )

    assert built.exit_code == CLI_INVALID_REQUEST
    assert traversals == 0
    assert "invalid request" in built.output.lower()


@pytest.mark.parametrize("malformation", ["duplicate", "unknown", "coercion", "oversize"])
def test_cli_request_json_is_strict_and_bounded_before_source_access(
    tmp_path: Path,
    malformation: str,
) -> None:
    scenario = build_scenario()
    payload = scenario.request.model_dump(mode="json")
    request_path = tmp_path / f"{malformation}.json"
    if malformation == "duplicate":
        encoded = scenario.request.model_dump_json()
        request_path.write_text('{"context":null,' + encoded[1:], encoding="utf-8")
    elif malformation == "unknown":
        payload["undeclared_member"] = "forbidden"
        request_path.write_text(json.dumps(payload), encoding="utf-8")
    elif malformation == "coercion":
        payload["release_version"] = 1
        request_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        request_path.write_bytes(b"{" + b" " * (M0308_MAX_CANONICAL_REQUEST_BYTES - 1) + b"}")

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(tmp_path / "untrusted-source"),
            "--output",
            str(tmp_path / "release.tar"),
        ],
    )

    assert built.exit_code == CLI_INVALID_REQUEST
    assert "invalid request" in built.output.lower()
    assert "source directory" not in built.output.lower()


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra_file", "extra_directory", "nonregular", "size"],
)
def test_cli_rejects_nonexact_or_changed_source_trees(tmp_path: Path, mutation: str) -> None:
    request_path, source, output, scenario = _write_fixture(tmp_path)
    declaration = scenario.request.artifacts[1]
    target = source.joinpath(*declaration.path.split("/"))
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra_file":
        (source / "undeclared.bin").write_bytes(b"extra")
    elif mutation == "extra_directory":
        (source / "undeclared").mkdir()
    elif mutation == "nonregular":
        target.unlink()
        target.mkdir()
    else:
        target.write_bytes(target.read_bytes()[:-1])

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert not output.exists()


def test_cli_rejects_symlinked_source_without_leaking_target_name(tmp_path: Path) -> None:
    request_path, source, output, scenario = _write_fixture(tmp_path)
    declaration = scenario.request.artifacts[1]
    target = source.joinpath(*declaration.path.split("/"))
    outside = tmp_path / "PRIVATE_PROTEIN_RELEASE_CANARY.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert "link" in built.output.lower()
    assert outside.name not in built.output
    assert not output.exists()


def test_cli_detects_source_toctou_before_engine_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path, source, output, _scenario = _write_fixture(tmp_path)
    monkeypatch.setattr(cli_adapter, "_same_file_receipt", lambda _left, _right: False)

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert "changed during admission" in built.output
    assert not output.exists()


@pytest.mark.parametrize("output_kind", ["existing", "symlink"])
def test_cli_refuses_existing_or_linked_output_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_kind: str,
) -> None:
    request_path, source, output, _scenario = _write_fixture(tmp_path)
    canary = tmp_path / "OUTPUT_CANARY.bin"
    canary.write_bytes(b"preserve-me")
    if output_kind == "existing":
        output.write_bytes(canary.read_bytes())
    else:
        try:
            output.symlink_to(canary)
        except OSError:
            pytest.skip("symbolic links are unavailable")
    monkeypatch.setattr(
        cli_adapter,
        "M0308Service",
        lambda: M0308Service(DeterministicNonCryptographicVerifier()),
    )

    built = CliRunner().invoke(
        cli_app,
        [
            "protein-inference-release",
            "build",
            str(request_path),
            str(source),
            "--output",
            str(output),
        ],
    )

    assert built.exit_code == 1
    assert "output must be a new" in built.output
    assert canary.read_bytes() == b"preserve-me"


def _write_released_package(tmp_path: Path) -> tuple[Path, Path]:
    scenario = build_scenario()
    built = M0308Service(scenario.verifier).build(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
    )
    assert built.package_bytes is not None
    result_path = tmp_path / "released-result.json"
    package_path = tmp_path / "released-package.tar"
    result_path.write_text(built.result.model_dump_json(), encoding="utf-8")
    package_path.write_bytes(built.package_bytes)
    return result_path, package_path


@pytest.mark.parametrize("mutation", ["symlink", "size", "toctou"])
def test_cli_verify_rejects_hostile_package_filesystem_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    result_path, package_path = _write_released_package(tmp_path)
    if mutation == "symlink":
        outside = tmp_path / "PRIVATE_PACKAGE_CANARY.tar"
        outside.write_bytes(package_path.read_bytes())
        package_path.unlink()
        try:
            package_path.symlink_to(outside)
        except OSError:
            pytest.skip("symbolic links are unavailable")
    elif mutation == "size":
        package_path.write_bytes(package_path.read_bytes()[:-1])
    else:
        monkeypatch.setattr(cli_adapter, "_same_file_receipt", lambda _left, _right: False)

    verified = CliRunner().invoke(
        cli_app,
        ["protein-inference-release", "verify", str(result_path), str(package_path)],
    )

    assert verified.exit_code == 1
    assert "verification failed" in verified.output
