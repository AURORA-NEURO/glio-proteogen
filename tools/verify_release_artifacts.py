# ruff: noqa: TRY003
"""Verify that release evidence describes and tests the exact built wheel.

The checks are intentionally standard-library only so they can run inside the pristine
runtime environment created from a candidate wheel.  They do not qualify a release; they
only reject internally inconsistent build evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import url2pathname
from zipfile import BadZipFile, ZipFile

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_PROJECT_NAME = "glio-proteogen"
_PACKAGE_NAME = "glio_proteogen"
_CONSOLE_SCRIPT = "glio-proteogen"
_CONSOLE_ENTRY_POINT = "glio_proteogen.adapters.cli:app"
_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_CLI_SCHEMA_SMOKE_TESTS = (
    (
        ("export-schema", "protocol-schema"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema",
    ),
    (
        ("identity", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-02:1.0.0:request",
    ),
    (
        ("raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-03:1.0.0:request",
    ),
    (
        ("quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-04:1.0.0:request",
    ),
    (
        ("artifact", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-05:1.0.0:request",
    ),
    (
        ("harmonize", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-06:1.0.0:request",
    ),
    (
        ("support", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-07:1.0.0:request",
    ),
    (
        ("release", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-08:1.0.0:request",
    ),
    (
        ("identification", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-01:1.0.0:request",
    ),
    (
        ("binding", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-02:1.0.0:request",
    ),
    (
        ("identification-raw", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-03:1.0.0:request",
    ),
    (
        ("identification-quality", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-04:1.0.0:request",
    ),
    (
        ("identification-artifacts", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-05:1.0.0:request",
    ),
    (
        ("identification-harmonization", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-06:1.0.0:request",
    ),
    (
        ("identification-support", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-07:1.0.0:request",
    ),
    (
        ("identification-release", "export-schema", "request"),
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-08:1.0.0:request",
    ),
)
_FORBIDDEN_RUNTIME_COMPONENTS = frozenset(
    {
        "cyclonedx-bom",
        "hypothesis",
        "mypy",
        "pip-audit",
        "pytest",
        "pytest-benchmark",
        "pytest-cov",
        "pytest-xdist",
        "ruff",
    }
)


class ReleaseArtifactError(ValueError):
    """Raised when candidate release evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class WheelIdentity:
    """Distribution identity read from a wheel's embedded core metadata."""

    name: str
    version: str
    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeSbomSummary:
    """Verified root identity and component count for a runtime SBOM."""

    root_name: str
    root_version: str
    component_count: int


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_identity(wheel: Path) -> WheelIdentity:
    """Read the one authoritative Name/Version pair embedded in *wheel*."""

    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ReleaseArtifactError("candidate wheel path is not one wheel file")
    try:
        with ZipFile(wheel) as archive:
            metadata_paths = tuple(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            if len(metadata_paths) != 1:
                raise ReleaseArtifactError("candidate wheel must contain one METADATA file")
            message = BytesParser(policy=default).parsebytes(archive.read(metadata_paths[0]))
    except (BadZipFile, KeyError, OSError) as error:
        raise ReleaseArtifactError("candidate wheel cannot be read safely") from error

    name = message.get("Name")
    version = message.get("Version")
    if not isinstance(name, str) or not name.strip():
        raise ReleaseArtifactError("candidate wheel has no distribution name")
    if not isinstance(version, str) or not version.strip():
        raise ReleaseArtifactError("candidate wheel has no distribution version")
    if _normalized_distribution_name(name) != _PROJECT_NAME:
        raise ReleaseArtifactError("candidate wheel is not the expected project")
    return WheelIdentity(
        name=name,
        version=version,
        filename=wheel.name,
        sha256=_sha256(wheel),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ReleaseArtifactError(f"release evidence {label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ReleaseArtifactError(f"release evidence {label} must be an array")
    return value


def _load_sbom(path: Path) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_bytes())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise ReleaseArtifactError("runtime SBOM is not valid UTF-8 JSON") from error
    return _mapping(payload, "document")


def _verify_reproducible_cyclonedx_header(
    document: Mapping[str, object],
) -> Mapping[str, object]:
    if document.get("bomFormat") != "CycloneDX":
        raise ReleaseArtifactError("runtime SBOM is not CycloneDX")
    if document.get("specVersion") != "1.6":
        raise ReleaseArtifactError("runtime SBOM uses an unexpected specification version")
    if "serialNumber" in document:
        raise ReleaseArtifactError("runtime SBOM contains a non-reproducible serial number")
    metadata = _mapping(document.get("metadata"), "metadata")
    if "timestamp" in metadata:
        raise ReleaseArtifactError("runtime SBOM contains a non-reproducible timestamp")
    return metadata


def verify_runtime_sbom(sbom: Path, wheel: Path) -> RuntimeSbomSummary:
    """Verify that *sbom* is a runtime-only CycloneDX BOM rooted at *wheel*."""

    identity = wheel_identity(wheel)
    document = _load_sbom(sbom)
    metadata = _verify_reproducible_cyclonedx_header(document)
    root = _mapping(metadata.get("component"), "root component")
    root_name = root.get("name")
    root_version = root.get("version")
    root_reference = root.get("bom-ref")
    if not isinstance(root_name, str) or not isinstance(root_version, str):
        raise ReleaseArtifactError("runtime SBOM root identity is incomplete")
    if (
        _normalized_distribution_name(root_name) != _normalized_distribution_name(identity.name)
        or root_version != identity.version
    ):
        raise ReleaseArtifactError("runtime SBOM root does not match the candidate wheel")
    if root.get("type") != "application":
        raise ReleaseArtifactError("runtime SBOM root must be an application component")
    if not isinstance(root_reference, str) or not root_reference:
        raise ReleaseArtifactError("runtime SBOM root has no dependency reference")

    dependencies = _sequence(document.get("dependencies"), "dependencies")
    root_edges = sum(
        _mapping(item, "dependency entry").get("ref") == root_reference for item in dependencies
    )
    if root_edges != 1:
        raise ReleaseArtifactError("runtime SBOM dependency graph does not contain one root")

    components = _sequence(document.get("components"), "components")
    component_names: set[str] = set()
    for item in components:
        component = _mapping(item, "component")
        name = component.get("name")
        if not isinstance(name, str) or not name:
            raise ReleaseArtifactError("runtime SBOM contains a component without a name")
        component_names.add(_normalized_distribution_name(name))
    leaked = sorted(component_names & _FORBIDDEN_RUNTIME_COMPONENTS)
    if leaked:
        raise ReleaseArtifactError("runtime SBOM contains development-only components")

    return RuntimeSbomSummary(
        root_name=root_name,
        root_version=root_version,
        component_count=len(components),
    )


def _installed_console_script() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    executable = Path(sys.executable).with_name(f"{_CONSOLE_SCRIPT}{suffix}")
    if not executable.is_file():
        raise ReleaseArtifactError("installed wheel has no console script")
    return executable


def _installed_distribution(
    identity: WheelIdentity,
) -> tuple[importlib.metadata.Distribution, Path]:
    try:
        distribution = importlib.metadata.distribution(identity.name)
    except importlib.metadata.PackageNotFoundError as error:
        raise ReleaseArtifactError("candidate distribution is not installed") from error

    installed_name = distribution.metadata.get("Name")
    if not isinstance(installed_name, str):
        raise ReleaseArtifactError("installed distribution identity is incomplete")
    if (
        _normalized_distribution_name(installed_name)
        != _normalized_distribution_name(identity.name)
        or distribution.version != identity.version
    ):
        raise ReleaseArtifactError("installed distribution does not match the candidate wheel")

    environment = Path(sys.prefix).resolve()
    distribution_root = Path(str(distribution.locate_file(""))).resolve()
    if not distribution_root.is_relative_to(environment):
        raise ReleaseArtifactError("candidate distribution is outside the clean environment")
    return distribution, environment


def _verify_direct_wheel_install(
    distribution: importlib.metadata.Distribution,
    wheel: Path,
) -> None:
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        raise ReleaseArtifactError("candidate distribution has no direct wheel provenance")
    try:
        direct_url: object = json.loads(direct_url_text)
    except json.JSONDecodeError as error:
        raise ReleaseArtifactError("candidate distribution provenance is malformed") from error
    direct_url_mapping = _mapping(direct_url, "installed provenance")
    source_url = direct_url_mapping.get("url")
    if not isinstance(source_url, str) or "dir_info" in direct_url_mapping:
        raise ReleaseArtifactError("candidate distribution was not installed from a wheel")
    parsed_url = urlsplit(source_url)
    if (
        parsed_url.scheme != "file"
        or parsed_url.netloc.casefold() not in {"", "localhost"}
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ReleaseArtifactError("candidate wheel provenance is not one local file")
    source_path = Path(url2pathname(parsed_url.path)).resolve()
    if source_path != wheel.resolve():
        raise ReleaseArtifactError("installed distribution came from a different wheel")


def _verify_installed_files(
    distribution: importlib.metadata.Distribution,
    environment: Path,
    wheel: Path,
) -> None:
    try:
        with ZipFile(wheel) as archive:
            for member in archive.infolist():
                wheel_path = PurePosixPath(member.filename)
                if member.is_dir():
                    continue
                if wheel_path.is_absolute() or ".." in wheel_path.parts:
                    raise ReleaseArtifactError("candidate wheel contains an unsafe member path")
                if member.filename.endswith(".dist-info/RECORD"):
                    continue
                installed_path = Path(
                    str(distribution.locate_file(Path(*wheel_path.parts)))
                ).resolve()
                if not installed_path.is_relative_to(environment):
                    raise ReleaseArtifactError("candidate wheel member escaped the environment")
                try:
                    installed_digest = _sha256(installed_path)
                except OSError as error:
                    raise ReleaseArtifactError("candidate wheel member is not installed") from error
                archive_digest = hashlib.sha256(archive.read(member)).hexdigest()
                if installed_digest != archive_digest:
                    raise ReleaseArtifactError("installed file does not match the candidate wheel")
    except (BadZipFile, OSError) as error:
        raise ReleaseArtifactError("candidate wheel members cannot be verified") from error


def _verify_package_import(identity: WheelIdentity, environment: Path) -> None:
    package = importlib.import_module(_PACKAGE_NAME)
    package_path_value = getattr(package, "__file__", None)
    if not isinstance(package_path_value, str):
        raise ReleaseArtifactError("installed package has no import origin")
    if not Path(package_path_value).resolve().is_relative_to(environment):
        raise ReleaseArtifactError("package import resolved outside the clean environment")
    if getattr(package, "__version__", None) != identity.version:
        raise ReleaseArtifactError("package version does not match wheel metadata")


def _verify_console_script() -> None:
    entry_points = tuple(
        entry_point
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
        if entry_point.name == _CONSOLE_SCRIPT
    )
    if len(entry_points) != 1 or entry_points[0].value != _CONSOLE_ENTRY_POINT:
        raise ReleaseArtifactError("candidate wheel has an unexpected console entry point")
    executable = str(_installed_console_script())
    for arguments, expected_schema_id in _CLI_SCHEMA_SMOKE_TESTS:
        completed = subprocess.run(  # noqa: S603 - path is from this trusted interpreter.
            [executable, *arguments],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise ReleaseArtifactError("installed console-script smoke test failed")
        try:
            schema: object = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ReleaseArtifactError(
                "installed console script emitted invalid schema JSON"
            ) from error
        exported = _mapping(schema, "exported schema")
        if exported.get("$schema") != _SCHEMA_URI:
            raise ReleaseArtifactError("installed console script emitted the wrong schema dialect")
        if exported.get("$id") != expected_schema_id:
            raise ReleaseArtifactError("installed console script emitted the wrong contract")


def verify_installed_wheel(wheel: Path) -> WheelIdentity:
    """Prove this interpreter imports a non-editable install matching *wheel*."""

    identity = wheel_identity(wheel)
    distribution, environment = _installed_distribution(identity)
    _verify_direct_wheel_install(distribution, wheel)
    _verify_installed_files(distribution, environment, wheel)
    _verify_package_import(identity, environment)
    _verify_console_script()
    return identity


def _write_install_report(path: Path, identity: WheelIdentity) -> None:
    report = {
        "distribution": identity.name,
        "schema_dialect": _SCHEMA_URI,
        "version": identity.version,
        "verified_cli_schema_routes": [
            {
                "arguments": list(arguments),
                "schema_id": schema_id,
            }
            for arguments, schema_id in _CLI_SCHEMA_SMOKE_TESTS
        ],
        "wheel": {"filename": identity.filename, "sha256": identity.sha256},
    }
    path.write_text(
        json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _verify_expected_tag(identity: WheelIdentity, expected_tag: str | None) -> None:
    if expected_tag is not None and expected_tag != f"v{identity.version}":
        raise ReleaseArtifactError("release tag does not match candidate wheel version")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    installed = commands.add_parser(
        "installed-wheel", help="verify the wheel installed in this interpreter"
    )
    installed.add_argument("wheel", type=Path)
    installed.add_argument("--expected-tag")
    installed.add_argument("--report", type=Path)
    runtime_sbom = commands.add_parser(
        "runtime-sbom", help="verify a runtime SBOM against its candidate wheel"
    )
    runtime_sbom.add_argument("sbom", type=Path)
    runtime_sbom.add_argument("wheel", type=Path)
    return parser


def main() -> int:
    """Run release-artifact verification without exposing artifact contents on failure."""

    arguments = _parser().parse_args()
    try:
        if arguments.command == "installed-wheel":
            identity = verify_installed_wheel(arguments.wheel)
            _verify_expected_tag(identity, arguments.expected_tag)
            if arguments.report is not None:
                _write_install_report(arguments.report, identity)
        else:
            verify_runtime_sbom(arguments.sbom, arguments.wheel)
    except ReleaseArtifactError as error:
        sys.stderr.write(f"release artifact verification failed: {error}\n")
        return 1
    sys.stdout.write("release artifact verification passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
