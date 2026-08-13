"""Human-readable and automation-safe command-line interface."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal

import typer
import uvicorn
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.api import (
    _artifact_contract_schema,
    _contract_schema,
    _harmonization_contract_schema,
    _identification_artifact_contract_schema,
    _identification_contract_schema,
    _identification_harmonization_contract_schema,
    _identification_quality_contract_schema,
    _identification_raw_contract_schema,
    _identification_release_contract_schema,
    _identification_support_contract_schema,
    _identity_binding_contract_schema,
    _identity_contract_schema,
    _protein_inference_lineage_contract_schema,
    _protein_inference_protocol_contract_schema,
    _protein_inference_raw_contract_schema,
    _quality_contract_schema,
    _raw_contract_schema,
    _release_packaging_contract_schema,
    _support_routing_contract_schema,
    create_app,
)
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.contracts.m01_04.v1 import ComputeQualityMetricsRequest
from glio_proteogen.contracts.m01_05.v1 import DetectArtifactsRequest
from glio_proteogen.contracts.m01_06.v1 import HarmonizeObservationsRequest
from glio_proteogen.contracts.m01_07.v1 import RouteSupportRequest
from glio_proteogen.contracts.m01_08.v1 import (
    BuildReleasePackageRequest,
    ReleaseDisposition,
    ReleasePackagingResult,
)
from glio_proteogen.contracts.m02_01.v1 import (
    ConformanceEvaluation as M0201ConformanceEvaluation,
)
from glio_proteogen.contracts.m02_01.v1 import EvaluateConformanceRequest
from glio_proteogen.contracts.m02_02.v1 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.contracts.m02_03.v1 import (
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
)
from glio_proteogen.contracts.m02_04.v1 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.contracts.m02_05.v1 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.contracts.m02_06.v1 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.contracts.m02_07.v1 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.contracts.m02_08 import (
    BuildIdentificationQcReleaseRequest,
    IdentificationQcReleaseResult,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
)
from glio_proteogen.contracts.m03_01.v1 import EvaluateProteinInferenceProtocolRequest
from glio_proteogen.contracts.m03_02.v1 import (
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    InvalidProtocolLookupError,
    M0101Service,
    M0101ServiceError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
    M0105Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    preflight_harmonization_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.service import (
    M0106Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    preflight_support_routing_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.service import (
    M0107Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging import (
    M0108Service,
    ReleasePackagingInputError,
    preflight_release_packaging_authorization,
    verify_release_package,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
    preflight_conformance_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
    preflight_identity_binding_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    IdentificationRawIngestionInputError,
    M0203Service,
    preflight_identification_raw_ingestion_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    M0204Service,
    preflight_identification_quality_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    M0205Service,
    preflight_identification_artifact_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    M0206Service,
    preflight_identification_harmonization_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    M0207Service,
    preflight_identification_support_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    IdentificationReleaseAuthorizationError,
    IdentificationReleaseInputError,
    M0208Service,
    preflight_identification_release_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Service,
    preflight_protein_inference_protocol_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Service,
    preflight_protein_identity_lineage_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    M0303Service,
    ProteinInferenceRawIngestionInputError,
    preflight_protein_inference_raw_ingestion_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
protocol_app = typer.Typer(no_args_is_help=True, help="M01-01 protocol operations.")
app.add_typer(protocol_app, name="protocol")
identity_app = typer.Typer(no_args_is_help=True, help="M01-02 identity and lineage operations.")
app.add_typer(identity_app, name="identity")
raw_app = typer.Typer(no_args_is_help=True, help="M01-03 bounded raw-format ingestion.")
app.add_typer(raw_app, name="raw")
quality_app = typer.Typer(no_args_is_help=True, help="M01-04 deterministic quality metrics.")
app.add_typer(quality_app, name="quality")
artifact_app = typer.Typer(no_args_is_help=True, help="M01-05 deterministic artifact detection.")
app.add_typer(artifact_app, name="artifact")
harmonization_app = typer.Typer(
    no_args_is_help=True,
    help="M01-06 deterministic harmonization and normalization.",
)
app.add_typer(harmonization_app, name="harmonize")
support_routing_app = typer.Typer(
    no_args_is_help=True,
    help="M01-07 deterministic support and abstention routing.",
)
app.add_typer(support_routing_app, name="support")
release_packaging_app = typer.Typer(
    no_args_is_help=True,
    help="M01-08 deterministic provenance and release packaging.",
)
app.add_typer(release_packaging_app, name="release")
identification_app = typer.Typer(
    no_args_is_help=True,
    help="M02-01 peptide-identification protocol metadata conformance.",
)
app.add_typer(identification_app, name="identification")
binding_audit_app = typer.Typer(
    no_args_is_help=True,
    help="M02-02 peptide-identification identity-binding audit.",
)
app.add_typer(binding_audit_app, name="binding")
identification_raw_app = typer.Typer(
    no_args_is_help=True,
    help="M02-03 role-aware peptide-identification raw ingestion.",
)
app.add_typer(identification_raw_app, name="identification-raw")
identification_quality_app = typer.Typer(
    no_args_is_help=True,
    help="M02-04 deterministic peptide-identification quality metrics.",
)
app.add_typer(identification_quality_app, name="identification-quality")
identification_artifacts_app = typer.Typer(
    no_args_is_help=True,
    help="M02-05 deterministic peptide-identification artifact detection.",
)
app.add_typer(identification_artifacts_app, name="identification-artifacts")
identification_harmonization_app = typer.Typer(
    no_args_is_help=True,
    help="M02-06 peptide-identification harmonization and normalization.",
)
app.add_typer(identification_harmonization_app, name="identification-harmonization")
identification_support_app = typer.Typer(
    no_args_is_help=True,
    help="M02-07 joint-envelope peptide-identification support routing.",
)
app.add_typer(identification_support_app, name="identification-support")
identification_release_app = typer.Typer(
    no_args_is_help=True,
    help="M02-08 peptide-identification provenance and release packaging.",
)
app.add_typer(identification_release_app, name="identification-release")
protein_inference_protocol_app = typer.Typer(
    no_args_is_help=True,
    help="M03-01 protein-inference protocol conformance.",
)
app.add_typer(protein_inference_protocol_app, name="protein-inference-protocol")
protein_inference_lineage_app = typer.Typer(
    no_args_is_help=True,
    help="M03-02 protein-inference artifact identity-lineage reconciliation.",
)
app.add_typer(protein_inference_lineage_app, name="protein-inference-lineage")
protein_inference_raw_app = typer.Typer(
    no_args_is_help=True,
    help="M03-03 bounded protein-inference raw-source admission.",
)
app.add_typer(protein_inference_raw_app, name="protein-inference-raw")

_RESOLUTION_DIGEST_ADAPTER = TypeAdapter(Sha256Digest)
_IDENTIFICATION_RELEASE_STAGES = (
    (
        IdentificationReleaseArtifactRole.M02_01_CONFORMANCE,
        "GLIO-PROTEOGEN-M02-01",
        TypeAdapter(M0201ConformanceEvaluation),
    ),
    (
        IdentificationReleaseArtifactRole.M02_02_IDENTITY_LINEAGE,
        "GLIO-PROTEOGEN-M02-02",
        TypeAdapter(IdentityBindingEvaluation),
    ),
    (
        IdentificationReleaseArtifactRole.M02_03_RAW_INGESTION,
        "GLIO-PROTEOGEN-M02-03",
        TypeAdapter(IdentificationRawIngestionResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_04_QUALITY,
        "GLIO-PROTEOGEN-M02-04",
        TypeAdapter(IdentificationQualityProfile),
    ),
    (
        IdentificationReleaseArtifactRole.M02_05_ARTIFACT_DETECTION,
        "GLIO-PROTEOGEN-M02-05",
        TypeAdapter(IdentificationArtifactDetectionResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_06_HARMONIZATION,
        "GLIO-PROTEOGEN-M02-06",
        TypeAdapter(IdentificationHarmonizationResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_07_SUPPORT_ROUTE,
        "GLIO-PROTEOGEN-M02-07",
        TypeAdapter(IdentificationSupportRouteResult),
    ),
)

DatabaseOption = Annotated[
    Path,
    typer.Option("--database", "-d", help="Append-only SQLite event database."),
]
RequestArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
]
SourceDirectoryArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
]
OutputOption = Annotated[
    Path,
    typer.Option("--output", "-o", help="New canonical USTAR package path."),
]


class _ReleaseFileError(ValueError):
    """A CLI filesystem boundary could not be read or written safely."""

    @classmethod
    def source_not_directory(cls) -> _ReleaseFileError:
        return cls("source is not a directory")

    @classmethod
    def symlink_source(cls) -> _ReleaseFileError:
        return cls("artifact source cannot traverse a symbolic link")

    @classmethod
    def non_regular_source(cls) -> _ReleaseFileError:
        return cls("artifact source must be a regular file below source")

    @classmethod
    def source_size_mismatch(cls) -> _ReleaseFileError:
        return cls("artifact source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _ReleaseFileError:
        return cls("artifact source closure is unavailable")

    @classmethod
    def package_unavailable(cls) -> _ReleaseFileError:
        return cls("package is unavailable")

    @classmethod
    def package_size_mismatch(cls) -> _ReleaseFileError:
        return cls("package size contradicts its descriptor")

    @classmethod
    def output_unavailable(cls) -> _ReleaseFileError:
        return cls("package output must be a new writable file")


class _IdentificationRawFileError(ValueError):
    """A declared M02-03 source cannot be read through the safe directory boundary."""

    @classmethod
    def source_not_directory(cls) -> _IdentificationRawFileError:
        return cls("source directory is unavailable")

    @classmethod
    def symlink_source(cls) -> _IdentificationRawFileError:
        return cls("raw source cannot traverse a symbolic link")

    @classmethod
    def invalid_source_name(cls) -> _IdentificationRawFileError:
        return cls("raw source identifier is not a safe filename")

    @classmethod
    def non_regular_source(cls) -> _IdentificationRawFileError:
        return cls("raw source must be a regular file below source directory")

    @classmethod
    def source_size_mismatch(cls) -> _IdentificationRawFileError:
        return cls("raw source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _IdentificationRawFileError:
        return cls("raw source is unavailable")


class _ProteinInferenceRawFileError(ValueError):
    """A declared M03-03 source violates the directory-backed CLI boundary."""

    @classmethod
    def source_not_directory(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference source directory is unavailable")

    @classmethod
    def linked_or_reparse_source(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source cannot be a link or reparse point")

    @classmethod
    def invalid_source_name(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference source identifier is not a safe filename")

    @classmethod
    def non_regular_source(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source must be a regular file")

    @classmethod
    def source_changed(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source changed during admission")

    @classmethod
    def source_size_mismatch(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source is unavailable")


class _IdentificationReleaseFileError(ValueError):
    """A CLI path violates the closed M02-08 file or archive boundary."""

    @classmethod
    def source_not_directory(cls) -> _IdentificationReleaseFileError:
        return cls("release source directory is unavailable")

    @classmethod
    def linked_source(cls) -> _IdentificationReleaseFileError:
        return cls("release source cannot contain symbolic links or junctions")

    @classmethod
    def unexpected_entry(cls) -> _IdentificationReleaseFileError:
        return cls("release source must contain exactly the declared artifact paths")

    @classmethod
    def non_regular_source(cls) -> _IdentificationReleaseFileError:
        return cls("release artifacts must be regular files")

    @classmethod
    def source_size_mismatch(cls) -> _IdentificationReleaseFileError:
        return cls("release artifact size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("release artifact source is unavailable")

    @classmethod
    def stage_invalid(cls) -> _IdentificationReleaseFileError:
        return cls("release stage artifact is not its exact strict result contract")

    @classmethod
    def package_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("identification release package is unavailable")

    @classmethod
    def package_size_mismatch(cls) -> _IdentificationReleaseFileError:
        return cls("identification release package size contradicts its descriptor")

    @classmethod
    def output_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("identification release output must be a new writable file")


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


def _load_request[RequestT](
    path: Path,
    adapter: TypeAdapter[RequestT],
    preflight: Callable[[object], None] | None = None,
) -> RequestT:
    try:
        payload = read_bounded(path)
        decoded = strict_json_loads(payload)
        if preflight is not None:
            preflight(decoded)
        return adapter.validate_json(payload, strict=True)
    except RequestBodyTooLargeError as error:
        typer.echo(f"invalid request: {error}", err=True)
        raise typer.Exit(code=2) from error
    except StrictJsonError as error:
        typer.echo(f"invalid request: {error} ({error.code.value})", err=True)
        raise typer.Exit(code=2) from error
    except ValidationError as error:
        details = canonical_json_bytes(sanitized_validation_errors(error)).decode("utf-8")
        typer.echo(f"invalid request: {details}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, ValueError) as error:
        typer.echo("invalid request: unable to read or decode request document", err=True)
        raise typer.Exit(code=2) from error


def _service(database: Path) -> M0101Service:
    return M0101Service(M0101EventStore(database))


def _identity_service(database: Path) -> M0102Service:
    return M0102Service(M0102EventStore(database))


def _load_release_files(
    request: BuildReleasePackageRequest,
    source_directory: Path,
) -> dict[str, bytes]:
    """Resolve declared POSIX paths beneath one directory and read their exact bytes."""

    root = _resolve_release_source(source_directory)
    if not root.is_dir():
        raise _ReleaseFileError.source_not_directory()
    files: dict[str, bytes] = {}
    for artifact in request.artifacts:
        parts = PurePosixPath(artifact.path).parts
        candidate = root.joinpath(*parts)
        cursor = root
        for part in parts:
            cursor /= part
            if cursor.is_symlink():
                raise _ReleaseFileError.symlink_source()
        resolved = _resolve_release_source(candidate)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise _ReleaseFileError.non_regular_source()
        content = _read_release_source(resolved, artifact.byte_size)
        files[artifact.path] = content
    return files


def _resolve_release_source(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise _ReleaseFileError.source_unavailable() from error


def _read_release_source(path: Path, expected_size: int) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(expected_size + 1)
    except OSError as error:
        raise _ReleaseFileError.source_unavailable() from error
    if len(content) != expected_size:
        raise _ReleaseFileError.source_size_mismatch()
    return content


def _read_release_package(path: Path, expected_size: int) -> bytes:
    try:
        with path.open("rb") as stream:
            package_bytes = stream.read(expected_size + 1)
    except OSError as error:
        raise _ReleaseFileError.package_unavailable() from error
    if len(package_bytes) != expected_size:
        raise _ReleaseFileError.package_size_mismatch()
    return package_bytes


def _write_release_package(path: Path, package_bytes: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(package_bytes)
    except OSError as error:
        raise _ReleaseFileError.output_unavailable() from error


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _load_identification_release_inputs(
    request: BuildIdentificationQcReleaseRequest,
    source_directory: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Read the exact declared tree and strictly reconstruct all seven stage results."""

    root = _resolve_identification_release_directory(source_directory)
    expected_paths = {item.path for item in request.artifacts}
    _validate_identification_release_tree(root, expected_paths)

    artifacts: dict[str, bytes] = {}
    by_role = {item.role: item for item in request.artifacts}
    for declaration in request.artifacts:
        candidate = root.joinpath(*PurePosixPath(declaration.path).parts)
        artifacts[declaration.path] = _read_identification_release_artifact(
            root,
            candidate,
            declaration.declared_size,
        )

    stages: dict[str, object] = {}
    for role, module_id, adapter in _IDENTIFICATION_RELEASE_STAGES:
        declaration = by_role[role]
        try:
            stages[module_id] = adapter.validate_json(
                artifacts[declaration.path],
                strict=True,
            )
        except ValidationError as error:
            raise _IdentificationReleaseFileError.stage_invalid() from error
    return artifacts, stages


def _validate_identification_release_tree(root: Path, expected_paths: set[str]) -> None:
    expected_directories = {
        parent.as_posix()
        for path in expected_paths
        for parent in PurePosixPath(path).parents
        if parent != PurePosixPath(".")
    }
    actual_paths: set[str] = set()
    try:
        entries = tuple(root.rglob("*"))
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        if _is_link_or_junction(entry):
            raise _IdentificationReleaseFileError.linked_source()
        if entry.is_dir():
            if relative not in expected_directories:
                raise _IdentificationReleaseFileError.unexpected_entry()
            continue
        if not entry.is_file():
            raise _IdentificationReleaseFileError.non_regular_source()
        if relative not in expected_paths:
            raise _IdentificationReleaseFileError.unexpected_entry()
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise _IdentificationReleaseFileError.unexpected_entry()


def _resolve_identification_release_directory(source_directory: Path) -> Path:
    try:
        if _is_link_or_junction(source_directory):
            raise _IdentificationReleaseFileError.linked_source()
        root = source_directory.resolve(strict=True)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_not_directory() from error
    if not root.is_dir():
        raise _IdentificationReleaseFileError.source_not_directory()
    return root


def _read_identification_release_artifact(
    root: Path,
    path: Path,
    expected_size: int,
) -> bytes:
    try:
        if _is_link_or_junction(path):
            raise _IdentificationReleaseFileError.linked_source()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise _IdentificationReleaseFileError.non_regular_source()
    try:
        with resolved.open("rb") as stream:
            content = stream.read(expected_size + 1)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    if len(content) != expected_size:
        raise _IdentificationReleaseFileError.source_size_mismatch()
    return content


def _read_identification_release_package(
    path: Path,
    result: IdentificationQcReleaseResult,
) -> bytes:
    descriptor = result.package_descriptor
    if descriptor is None:
        raise _IdentificationReleaseFileError.package_unavailable()
    try:
        if _is_link_or_junction(path):
            raise _IdentificationReleaseFileError.package_unavailable()
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise _IdentificationReleaseFileError.package_unavailable()
        with resolved.open("rb") as stream:
            content = stream.read(descriptor.byte_size + 1)
    except OSError as error:
        raise _IdentificationReleaseFileError.package_unavailable() from error
    if len(content) != descriptor.byte_size:
        raise _IdentificationReleaseFileError.package_size_mismatch()
    return content


def _write_identification_release_package(path: Path, package_bytes: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(package_bytes)
    except OSError as error:
        raise _IdentificationReleaseFileError.output_unavailable() from error


def _load_identification_raw_files(
    request: IngestIdentificationRawInputsRequest,
    source_directory: Path,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """Map each exact source identifier to one same-named regular file below a directory."""

    root = _resolve_identification_raw_directory(source_directory)
    payloads: dict[str, bytes] = {}
    filenames: dict[str, str] = {}
    for item in request.sources:
        descriptor = item.source
        payloads[descriptor.source_id] = _read_identification_raw_source(
            root,
            descriptor.source_id,
            descriptor.byte_length,
        )
        filenames[descriptor.source_id] = descriptor.source_id
    return payloads, filenames


def _resolve_identification_raw_directory(source_directory: Path) -> Path:
    try:
        if source_directory.is_symlink():
            raise _IdentificationRawFileError.symlink_source()
        root = source_directory.resolve(strict=True)
    except OSError as error:
        raise _IdentificationRawFileError.source_not_directory() from error
    if not root.is_dir():
        raise _IdentificationRawFileError.source_not_directory()
    return root


def _read_identification_raw_source(root: Path, source_id: str, expected_size: int) -> bytes:
    if ":" in source_id or Path(source_id).name != source_id or source_id in {".", ".."}:
        raise _IdentificationRawFileError.invalid_source_name()
    candidate = root / source_id
    if candidate.is_symlink():
        raise _IdentificationRawFileError.symlink_source()
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise _IdentificationRawFileError.source_unavailable() from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise _IdentificationRawFileError.non_regular_source()
    try:
        with resolved.open("rb") as stream:
            payload = stream.read(expected_size + 1)
    except OSError as error:
        raise _IdentificationRawFileError.source_unavailable() from error
    if len(payload) != expected_size:
        raise _IdentificationRawFileError.source_size_mismatch()
    return payload


def _load_protein_inference_raw_files(
    request: IngestProteinInferenceRawInputsRequest,
    source_directory: Path,
) -> dict[str, bytes]:
    """Validate the complete literal-basename mapping, then read each file exactly once."""

    root = _resolve_protein_inference_raw_directory(source_directory)
    candidates: list[tuple[str, Path, os.stat_result]] = []
    for declaration in sorted(request.sources, key=lambda item: item.source_id):
        _validate_protein_inference_source_name(declaration.source_id)
        candidate = root / declaration.source_id
        before = _protein_inference_source_stat(candidate)
        if before.st_size != declaration.byte_length:
            raise _ProteinInferenceRawFileError.source_size_mismatch()
        candidates.append((declaration.source_id, candidate, before))

    payloads: dict[str, bytes] = {}
    for source_id, candidate, before in candidates:
        try:
            with candidate.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if not _same_file_receipt(before, opened) or not stat.S_ISREG(opened.st_mode):
                    raise _ProteinInferenceRawFileError.source_changed()
                payload = stream.read(before.st_size + 1)
                after = os.fstat(stream.fileno())
        except _ProteinInferenceRawFileError:
            raise
        except OSError as error:
            raise _ProteinInferenceRawFileError.source_unavailable() from error
        if not _same_file_receipt(opened, after):
            raise _ProteinInferenceRawFileError.source_changed()
        if len(payload) != before.st_size:
            raise _ProteinInferenceRawFileError.source_size_mismatch()
        payloads[source_id] = payload
    return payloads


def _resolve_protein_inference_raw_directory(source_directory: Path) -> Path:
    try:
        if _is_reparse_path(source_directory):
            raise _ProteinInferenceRawFileError.linked_or_reparse_source()
        root = source_directory.resolve(strict=True)
    except _ProteinInferenceRawFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_not_directory() from error
    if not root.is_dir():
        raise _ProteinInferenceRawFileError.source_not_directory()
    return root


def _validate_protein_inference_source_name(source_id: str) -> None:
    if (
        not source_id
        or source_id in {".", ".."}
        or ":" in source_id
        or "/" in source_id
        or "\\" in source_id
        or Path(source_id).name != source_id
        or source_id.rstrip(" .") != source_id
        or _is_windows_device_name(source_id)
    ):
        raise _ProteinInferenceRawFileError.invalid_source_name()


def _is_windows_device_name(source_id: str) -> bool:
    stem = source_id.split(".", 1)[0].casefold()
    return stem in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }


def _is_reparse_path(path: Path) -> bool:
    try:
        attributes = path.lstat()
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_unavailable() from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(attributes, "st_file_attributes", 0)
    return path.is_symlink() or path.is_junction() or bool(file_attributes & reparse_flag)


def _protein_inference_source_stat(path: Path) -> os.stat_result:
    if _is_reparse_path(path):
        raise _ProteinInferenceRawFileError.linked_or_reparse_source()
    try:
        received = path.stat(follow_symlinks=False)
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_unavailable() from error
    if not stat.S_ISREG(received.st_mode):
        raise _ProteinInferenceRawFileError.non_regular_source()
    return received


def _same_file_receipt(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


@protocol_app.command("register")
def register_protocol(request: RequestArgument, database: DatabaseOption) -> None:
    """Register an immutable protocol specification."""

    parsed = _load_request(request, TypeAdapter(RegisterProtocolRequest))
    try:
        with _service(database) as service:
            _emit(service.register(parsed))
    except M0101ServiceError as error:
        typer.echo(f"registration failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("evaluate")
def evaluate_metadata(request: RequestArgument, database: DatabaseOption) -> None:
    """Evaluate metadata without mutating the submitted evidence."""

    parsed = _load_request(request, TypeAdapter(EvaluateMetadataRequest))
    try:
        with _service(database) as service:
            _emit(service.evaluate(parsed))
    except M0101ServiceError as error:
        typer.echo(f"evaluation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("get")
def get_protocol(
    schema_id: Annotated[str, typer.Argument(help="Protocol schema identifier.")],
    version: Annotated[str, typer.Argument(help="Exact semantic version.")],
    database: DatabaseOption,
) -> None:
    """Retrieve the original content-addressed registration receipt."""

    try:
        with _service(database) as service:
            _emit(service.get_protocol(schema_id, version))
    except InvalidProtocolLookupError as error:
        typer.echo(f"invalid lookup: {error}", err=True)
        raise typer.Exit(code=2) from error
    except M0101ServiceError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("verify-ledger")
def verify_ledger(database: DatabaseOption) -> None:
    """Verify every link and payload digest in the append-only event chain."""

    try:
        with _service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0101ServiceError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("reconcile")
def reconcile_identity_lineage(request: RequestArgument, database: DatabaseOption) -> None:
    """Reconcile explicit identity assertions and lineage without relabeling inputs."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ReconcileIdentityLineageRequest),
            preflight_identity_authorization,
        )
        with _identity_service(database) as service:
            _emit(service.execute(parsed))
    except (IdentityLineageAuthorizationError, M0102EventStoreError) as error:
        typer.echo(f"reconciliation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("get")
def get_identity_resolution(
    resolution_digest: Annotated[str, typer.Argument(help="Exact resolution digest.")],
    database: DatabaseOption,
) -> None:
    """Retrieve and revalidate an immutable identity-lineage resolution."""

    try:
        validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
            resolution_digest,
            strict=True,
        )
    except ValidationError as error:
        typer.echo("invalid lookup: resolution digest is invalid", err=True)
        raise typer.Exit(code=2) from error
    try:
        with _identity_service(database) as service:
            _emit(service.get_resolution(validated_digest))
    except M0102EventStoreError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("verify-ledger")
def verify_identity_ledger(database: DatabaseOption) -> None:
    """Verify the M01-02 append-only identity-resolution event chain."""

    try:
        with _identity_service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0102EventStoreError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("export-schema")
def export_identity_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "entity", "operation", "resolution"],
        typer.Argument(help="M01-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-02 contract for agents and tools."""

    typer.echo(json.dumps(_identity_contract_schema(contract), indent=2, sort_keys=True))


@raw_app.command("inspect")
def inspect_raw_input(
    source: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    source_id: Annotated[str, typer.Option("--source-id", help="Opaque source identifier.")],
    expected_sha256: Annotated[
        str | None,
        typer.Option("--sha256", help="Optional SHA-256 digest of the transported bytes."),
    ] = None,
) -> None:
    """Inspect one bounded file and emit metadata only; source content is never echoed."""

    try:
        validated_source_id = TypeAdapter(Identifier).validate_python(source_id, strict=True)
        with source.open("rb") as stream:
            result = parse_raw_input(
                stream,
                source_id=validated_source_id,
                filename=source.name,
                expected_sha256=expected_sha256,
            )
    except ValidationError as error:
        typer.echo("invalid source identifier", err=True)
        raise typer.Exit(code=2) from error
    except OSError as error:
        typer.echo("inspection failed: unable to read source", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "accepted":
        raise typer.Exit(code=1)


@raw_app.command("export-schema")
def export_raw_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "source", "raw_input", "diagnostic"],
        typer.Argument(help="M01-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-03 contract for agents and tools."""

    typer.echo(json.dumps(_raw_contract_schema(contract), indent=2, sort_keys=True))


@quality_app.command("compute")
def compute_quality_metrics(request: RequestArgument) -> None:
    """Compute one deterministic typed quality profile."""

    parsed = _load_request(request, TypeAdapter(ComputeQualityMetricsRequest))
    _emit(M0104Service().execute(parsed))


@quality_app.command("export-schema")
def export_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "assay_profile",
            "metric_definition",
            "observation",
            "quality_metric",
        ],
        typer.Argument(help="M01-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-04 contract for agents and tools."""

    typer.echo(json.dumps(_quality_contract_schema(contract), indent=2, sort_keys=True))


@artifact_app.command("detect")
def detect_artifacts(request: RequestArgument) -> None:
    """Run one configured deterministic artifact screen."""

    parsed = _load_request(request, TypeAdapter(DetectArtifactsRequest))
    _emit(M0105Service().execute(parsed))


@artifact_app.command("export-schema")
def export_artifact_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "profile", "rule", "signal", "flag"],
        typer.Argument(help="M01-05 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-05 contract for agents and tools."""

    typer.echo(json.dumps(_artifact_contract_schema(contract), indent=2, sort_keys=True))


@harmonization_app.command("run")
def run_harmonization(request: RequestArgument) -> None:
    """Apply one authorized, configured technical harmonization."""

    parsed = _load_request(
        request,
        TypeAdapter(HarmonizeObservationsRequest),
        preflight_harmonization_authorization,
    )
    _emit(M0106Service().execute(parsed))


@harmonization_app.command("export-schema")
def export_harmonization_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "invariant",
            "value",
            "transformation",
        ],
        typer.Argument(help="M01-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-06 contract for agents and tools."""

    typer.echo(json.dumps(_harmonization_contract_schema(contract), indent=2, sort_keys=True))


@support_routing_app.command("route")
def run_support_routing(request: RequestArgument) -> None:
    """Route one authorized request through a declared support domain."""

    parsed = _load_request(
        request,
        TypeAdapter(RouteSupportRequest),
        preflight_support_routing_authorization,
    )
    _emit(M0107Service().execute(parsed))


@support_routing_app.command("export-schema")
def export_support_routing_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "criterion",
            "evidence",
            "assessment",
        ],
        typer.Argument(help="M01-07 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-07 contract for agents and tools."""

    typer.echo(json.dumps(_support_routing_contract_schema(contract), indent=2, sort_keys=True))


@release_packaging_app.command("export-schema")
def export_release_packaging_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "manifest"],
        typer.Argument(help="M01-08 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-08 contract for agents and tools."""

    typer.echo(json.dumps(_release_packaging_contract_schema(contract), indent=2, sort_keys=True))


@identification_app.command("validate-metadata")
def validate_identification_metadata(request: RequestArgument) -> None:
    """Validate metadata against one exact protocol schema and conformance profile."""

    parsed = _load_request(
        request,
        TypeAdapter(EvaluateConformanceRequest),
        preflight_conformance_authorization,
    )
    _emit(evaluate_conformance(parsed))


@identification_app.command("export-schema")
def export_identification_schema(
    contract: Annotated[
        Literal["request", "output", "schema", "profile", "observation"],
        typer.Argument(help="M02-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-01 contract for agents and tools."""

    typer.echo(json.dumps(_identification_contract_schema(contract), indent=2, sort_keys=True))


@binding_audit_app.command("audit")
def audit_identity_bindings(request: RequestArgument) -> None:
    """Audit bindings against one immutable upstream identity resolution."""

    parsed = _load_request(
        request,
        TypeAdapter(ValidateIdentityBindingsRequest),
        preflight_identity_binding_authorization,
    )
    _emit(evaluate_identity_bindings(parsed))


@binding_audit_app.command("export-schema")
def export_identity_binding_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "binding", "finding"],
        typer.Argument(help="M02-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-02 contract for agents and tools."""

    typer.echo(json.dumps(_identity_binding_contract_schema(contract), indent=2, sort_keys=True))


@identification_raw_app.command("ingest")
def ingest_identification_raw_inputs(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
) -> None:
    """Ingest exact same-named source files from one symlink-free directory."""

    parsed = _load_request(
        request,
        TypeAdapter(IngestIdentificationRawInputsRequest),
        preflight_identification_raw_ingestion_authorization,
    )
    try:
        sources, filenames = _load_identification_raw_files(parsed, source_directory)
        result = M0203Service().execute(parsed, sources, filenames)
    except (IdentificationRawIngestionInputError, _IdentificationRawFileError) as error:
        typer.echo(f"identification raw ingestion failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "accepted":
        raise typer.Exit(code=1)


@identification_raw_app.command("export-schema")
def export_identification_raw_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "source",
            "role_requirement",
            "bundle_diagnostic",
        ],
        typer.Argument(help="M02-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-03 contract for agents and tools."""

    typer.echo(json.dumps(_identification_raw_contract_schema(contract), indent=2, sort_keys=True))


@identification_quality_app.command("export-schema")
def export_identification_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "assay_profile",
            "policy",
            "threshold",
            "observation",
            "metric",
        ],
        typer.Argument(help="M02-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-04 contract for agents and tools."""

    typer.echo(
        json.dumps(_identification_quality_contract_schema(contract), indent=2, sort_keys=True)
    )


@identification_quality_app.command("compute")
def compute_identification_quality(request: RequestArgument) -> None:
    """Compute one authorized deterministic identification-quality profile."""

    parsed = _load_request(
        request,
        TypeAdapter(ComputeIdentificationQualityRequest),
        preflight_identification_quality_authorization,
    )
    _emit(M0204Service().execute(parsed))


@identification_artifacts_app.command("export-schema")
def export_identification_artifact_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "profile",
            "policy",
            "signal",
            "flag",
            "evaluation",
        ],
        typer.Argument(help="M02-05 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-05 contract for agents and tools."""

    typer.echo(
        json.dumps(_identification_artifact_contract_schema(contract), indent=2, sort_keys=True)
    )


@identification_artifacts_app.command("detect")
def detect_identification_artifacts(request: RequestArgument) -> None:
    """Detect configured technical artifacts in authorized identification evidence."""

    parsed = _load_request(
        request,
        TypeAdapter(DetectIdentificationArtifactsRequest),
        preflight_identification_artifact_authorization,
    )
    _emit(M0205Service().execute(parsed))


@identification_harmonization_app.command("export-schema")
def export_identification_harmonization_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "prerequisites",
            "profile",
            "policy",
            "observation",
            "value",
            "manifest",
        ],
        typer.Argument(help="M02-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-06 contract for agents and tools."""

    typer.echo(
        json.dumps(
            _identification_harmonization_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_harmonization_app.command("harmonize")
def harmonize_identification(request: RequestArgument) -> None:
    """Harmonize authorized aggregate identification evidence."""

    parsed = _load_request(
        request,
        TypeAdapter(HarmonizeIdentificationEvidenceRequest),
        preflight_identification_harmonization_authorization,
    )
    _emit(M0206Service().execute(parsed))


@identification_support_app.command("export-schema")
def export_identification_support_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "prerequisites",
            "profile",
            "policy",
            "declaration",
            "envelope",
            "abstention",
        ],
        typer.Argument(help="M02-07 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-07 contract for agents and tools."""

    typer.echo(
        json.dumps(
            _identification_support_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_support_app.command("route")
def route_identification_support(request: RequestArgument) -> None:
    """Route authorized identification evidence through whole support envelopes."""

    parsed = _load_request(
        request,
        TypeAdapter(RouteIdentificationSupportRequest),
        preflight_identification_support_authorization,
    )
    _emit(M0207Service().execute(parsed))


@identification_release_app.command("export-schema")
def export_identification_release_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact",
            "manifest",
            "verification",
            "signature",
        ],
        typer.Argument(help="M02-08 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-08 identification release contract."""

    typer.echo(
        json.dumps(
            _identification_release_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_release_app.command("build")
def build_identification_release_archive(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
    output: OutputOption,
) -> None:
    """Validate a closed release; without an injected verifier this quarantines safely."""

    parsed = _load_request(
        request,
        TypeAdapter(BuildIdentificationQcReleaseRequest),
        preflight_identification_release_authorization,
    )
    try:
        artifacts, stages = _load_identification_release_inputs(parsed, source_directory)
        built = M0208Service().build(parsed, artifacts, stages)
        if built.package_bytes is not None:
            _write_identification_release_package(output, built.package_bytes)
    except (
        IdentificationReleaseAuthorizationError,
        IdentificationReleaseInputError,
        _IdentificationReleaseFileError,
    ) as error:
        typer.echo(f"identification release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    _emit(built.result)
    if built.result.disposition is not IdentificationReleaseDisposition.RELEASED:
        raise typer.Exit(code=1)


@identification_release_app.command("verify")
def verify_identification_release_archive(
    result: RequestArgument,
    package: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Verify archive structure and content; authenticity needs an injected verifier."""

    parsed = _load_request(result, TypeAdapter(IdentificationQcReleaseResult))
    try:
        package_bytes = _read_identification_release_package(package, parsed)
        verification = M0208Service().verify(parsed, package_bytes)
    except _IdentificationReleaseFileError as error:
        typer.echo(f"identification release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(verification)
    if not verification.verified:
        raise typer.Exit(code=1)


@release_packaging_app.command("build")
def build_release_archive(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
    output: OutputOption,
) -> None:
    """Build and publish one externally authorized canonical release package."""

    parsed = _load_request(
        request,
        TypeAdapter(BuildReleasePackageRequest),
        preflight_release_packaging_authorization,
    )
    try:
        built = M0108Service().execute(parsed, _load_release_files(parsed, source_directory))
        if built.result.disposition is ReleaseDisposition.RELEASED:
            _write_release_package(output, built.package_bytes)
    except (ReleasePackagingInputError, _ReleaseFileError) as error:
        typer.echo(f"release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    _emit(built.result)
    if built.result.disposition is not ReleaseDisposition.RELEASED:
        raise typer.Exit(code=1)


@release_packaging_app.command("verify")
def verify_release_archive(
    result: RequestArgument,
    package: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Verify package bytes against one typed M01-08 release result."""

    parsed = _load_request(result, TypeAdapter(ReleasePackagingResult))
    try:
        package_bytes = _read_release_package(package, parsed.package.byte_size)
    except _ReleaseFileError as error:
        typer.echo(f"release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    verification = verify_release_package(parsed, package_bytes)
    _emit(verification)
    if not verification.verified:
        raise typer.Exit(code=1)


@protein_inference_protocol_app.command("export-schema")
def export_protein_inference_protocol_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "protocol",
            "profile",
            "search-space",
            "ambiguity",
            "receipt",
        ],
        typer.Argument(help="M03-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference protocol contract."""

    typer.echo(
        json.dumps(
            _protein_inference_protocol_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_protocol_app.command("validate")
def validate_protein_inference_protocol(request: RequestArgument) -> None:
    """Validate one authorized protein-inference protocol against its reviewed profile."""

    parsed = _load_request(
        request,
        TypeAdapter(EvaluateProteinInferenceProtocolRequest),
        preflight_protein_inference_protocol_authorization,
    )
    _emit(M0301Service().execute(parsed))


@protein_inference_lineage_app.command("export-schema")
def export_protein_inference_lineage_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact-claim",
            "derivation",
            "cn-receipt",
            "graph",
            "receipt",
        ],
        typer.Argument(help="M03-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference lineage contract."""

    typer.echo(
        json.dumps(
            _protein_inference_lineage_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_lineage_app.command("reconcile")
def reconcile_protein_inference_lineage(request: RequestArgument) -> None:
    """Reconcile governed protein-inference artifact lineage without relabeling."""

    parsed = _load_request(
        request,
        TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest),
        preflight_protein_identity_lineage_authorization,
    )
    _emit(M0302Service().execute(parsed))


@protein_inference_raw_app.command("export-schema")
def export_protein_inference_raw_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "source",
            "protocol-receipt",
            "lineage-receipt",
            "raw-input",
            "receipt",
        ],
        typer.Argument(help="M03-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference raw-admission contract."""

    typer.echo(
        json.dumps(
            _protein_inference_raw_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_raw_app.command("ingest")
def ingest_protein_inference_raw_inputs(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
) -> None:
    """Ingest exact same-named, non-reparse source files from one directory."""

    parsed = _load_request(
        request,
        TypeAdapter(IngestProteinInferenceRawInputsRequest),
        preflight_protein_inference_raw_ingestion_authorization,
    )
    try:
        sources = _load_protein_inference_raw_files(parsed, source_directory)
        result = M0303Service().execute(parsed, sources)
    except (
        ProteinInferenceRawIngestionInputError,
        _ProteinInferenceRawFileError,
    ) as error:
        typer.echo(f"protein-inference raw ingestion failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "validated":
        raise typer.Exit(code=1)


@app.command("export-schema")
def export_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "register-request",
            "evaluate-request",
            "protocol-schema",
            "metadata-document",
            "protocol-receipt",
            "conformance-profile",
        ],
        typer.Argument(help="Public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable public contract for agents and tools."""

    typer.echo(json.dumps(_contract_schema(contract), indent=2, sort_keys=True))


@app.command("serve")
def serve(
    database: DatabaseOption,
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65_535, help="Bind port.")] = 8000,
) -> None:
    """Run the typed research API."""

    uvicorn.run(create_app(database), host=host, port=port)


if __name__ == "__main__":
    app()
