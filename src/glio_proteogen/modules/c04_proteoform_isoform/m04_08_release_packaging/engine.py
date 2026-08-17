"""Deterministic, quarantine-first M04-08 protein-inference release engine."""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m04_01 import ProteoformProtocolConformanceResult
from glio_proteogen.contracts.m04_02 import ProteoformIdentityLineageResolution
from glio_proteogen.contracts.m04_03 import ProteoformRawInputValidationResult
from glio_proteogen.contracts.m04_04 import ProteoformQualityResult
from glio_proteogen.contracts.m04_05 import ProteoformArtifactDetectionResult
from glio_proteogen.contracts.m04_06 import ProteoformHarmonizationResult
from glio_proteogen.contracts.m04_07 import ProteoformSupportRouteResult
from glio_proteogen.contracts.m04_08 import (
    M0408_ARCHIVE_MEMBER_COUNT,
    M0408_AUTHORITY_LIMITATION_CODE,
    M0408_AUTHORITY_LIMITATION_STATEMENT,
    M0408_CONTRACT_VERSION,
    M0408_MANIFEST_PATH,
    M0408_MAX_ARTIFACT_BYTES,
    M0408_MAX_PACKAGE_BYTES,
    M0408_MODULE_ID,
    M0408_PACKAGE_LIMITATION_CODE,
    M0408_PACKAGE_LIMITATION_STATEMENT,
    M0408_QUARANTINED_SUPPORT_RATIONALE,
    M0408_RELEASED_SUPPORT_RATIONALE,
    M0408_REPRODUCIBILITY_LIMITATION_CODE,
    M0408_REPRODUCIBILITY_LIMITATION_STATEMENT,
    M0408_SENSITIVITY_NOTES,
    M0408_SIGNATURE_RECEIPT_PATH,
    M0408_UNCERTAINTY_RATIONALES,
    BuildProteoformReleaseRequest,
    ExternalProteoformSignature,
    ProteoformPackageVerificationReason,
    ProteoformParentDiscordanceReceipt,
    ProteoformReleaseArtifactRole,
    ProteoformReleaseDisposition,
    ProteoformReleaseMember,
    ProteoformReleasePackageDescriptor,
    ProteoformReleaseResult,
    ProteoformReleaseVerification,
    ProteoformReproducibilityManifest,
    ProteoformSignatureVerification,
    ProteoformSignatureVerificationReason,
    ProteoformStageModuleId,
    ProteoformStageProvenance,
    canonical_request_digest,
    context_digest,
    expected_release_quarantine_reasons,
    manifest_digest,
    normalized_manifest,
    policy_digest,
    release_evidence_index,
    release_provenance_input_digests,
    reproduction_evidence_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Mapping

StageResult = (
    ProteoformProtocolConformanceResult
    | ProteoformIdentityLineageResolution
    | ProteoformRawInputValidationResult
    | ProteoformQualityResult
    | ProteoformArtifactDetectionResult
    | ProteoformHarmonizationResult
    | ProteoformSupportRouteResult
)
StageModule = Literal[
    "GLIO-PROTEOGEN-M04-01",
    "GLIO-PROTEOGEN-M04-02",
    "GLIO-PROTEOGEN-M04-03",
    "GLIO-PROTEOGEN-M04-04",
    "GLIO-PROTEOGEN-M04-05",
    "GLIO-PROTEOGEN-M04-06",
    "GLIO-PROTEOGEN-M04-07",
]

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteoformReleaseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformReleaseResult)
_PARENT_ADAPTER: Final = TypeAdapter(ProteoformParentDiscordanceReceipt)
_M0401_ADAPTER: Final = TypeAdapter(ProteoformProtocolConformanceResult)
_M0402_ADAPTER: Final = TypeAdapter(ProteoformIdentityLineageResolution)
_M0403_ADAPTER: Final = TypeAdapter(ProteoformRawInputValidationResult)
_M0404_ADAPTER: Final = TypeAdapter(ProteoformQualityResult)
_M0405_ADAPTER: Final = TypeAdapter(ProteoformArtifactDetectionResult)
_M0406_ADAPTER: Final = TypeAdapter(ProteoformHarmonizationResult)
_M0407_ADAPTER: Final = TypeAdapter(ProteoformSupportRouteResult)

_STAGE_MODULES: Final[tuple[StageModule, ...]] = (
    "GLIO-PROTEOGEN-M04-01",
    "GLIO-PROTEOGEN-M04-02",
    "GLIO-PROTEOGEN-M04-03",
    "GLIO-PROTEOGEN-M04-04",
    "GLIO-PROTEOGEN-M04-05",
    "GLIO-PROTEOGEN-M04-06",
    "GLIO-PROTEOGEN-M04-07",
)
_ROLE_BY_MODULE: Final = {
    "GLIO-PROTEOGEN-M04-01": ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE,
    "GLIO-PROTEOGEN-M04-02": ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE,
    "GLIO-PROTEOGEN-M04-03": ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION,
    "GLIO-PROTEOGEN-M04-04": ProteoformReleaseArtifactRole.M04_04_QUALITY,
    "GLIO-PROTEOGEN-M04-05": ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION,
    "GLIO-PROTEOGEN-M04-06": ProteoformReleaseArtifactRole.M04_06_HARMONIZATION,
    "GLIO-PROTEOGEN-M04-07": ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT,
}
_STAGE_TYPE_BY_MODULE: Final[dict[StageModule, type[object]]] = {
    "GLIO-PROTEOGEN-M04-01": ProteoformProtocolConformanceResult,
    "GLIO-PROTEOGEN-M04-02": ProteoformIdentityLineageResolution,
    "GLIO-PROTEOGEN-M04-03": ProteoformRawInputValidationResult,
    "GLIO-PROTEOGEN-M04-04": ProteoformQualityResult,
    "GLIO-PROTEOGEN-M04-05": ProteoformArtifactDetectionResult,
    "GLIO-PROTEOGEN-M04-06": ProteoformHarmonizationResult,
    "GLIO-PROTEOGEN-M04-07": ProteoformSupportRouteResult,
}
_LIMITATIONS: Final = (
    Limitation(
        code=M0408_PACKAGE_LIMITATION_CODE,
        statement=M0408_PACKAGE_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0408_AUTHORITY_LIMITATION_CODE,
        statement=M0408_AUTHORITY_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0408_REPRODUCIBILITY_LIMITATION_CODE,
        statement=M0408_REPRODUCIBILITY_LIMITATION_STATEMENT,
    ),
)


class ProteoformReleaseAuthorizationError(PermissionError):
    """The raw request does not authorize release-input traversal."""

    def __init__(self) -> None:
        super().__init__("M04-08 release operation is not authorized")


class ProteoformReleaseInputErrorCode(StrEnum):
    ARTIFACT_MAPPING_MISMATCH = "artifact_mapping_mismatch"
    ARTIFACT_TYPE_INVALID = "artifact_type_invalid"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_DIGEST_MISMATCH = "artifact_digest_mismatch"
    PARENT_JSON_INVALID = "parent_json_invalid"
    STAGE_MAPPING_MISMATCH = "stage_mapping_mismatch"
    STAGE_JSON_INVALID = "stage_json_invalid"
    STAGE_RESULT_MISMATCH = "stage_result_mismatch"
    CHAIN_MISMATCH = "chain_mismatch"


class ProteoformReleaseInputError(ValueError):
    """Caller bytes, stage objects, or cross-stage receipts are malformed."""

    def __init__(self, code: ProteoformReleaseInputErrorCode) -> None:
        self.code = code
        super().__init__(f"M04-08 input rejected: {code.value}")


class _BuiltReleaseInvariantError(ValueError):
    def __init__(self) -> None:
        super().__init__("released disposition and package-byte presence must agree")


class _PackageBytesTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("package bytes must be immutable bytes")


class _NonCanonicalArtifactError(ValueError):
    """A typed JSON artifact was not encoded as its exact canonical bytes."""


def _require_canonical_artifact_bytes(value: object, content: bytes) -> None:
    if canonical_json_bytes(value) != content:
        raise _NonCanonicalArtifactError


class ProteoformSignatureVerifier(Protocol):
    """Narrow injected authenticity boundary; M04-08 owns the typed receipt."""

    @property
    def verifier_id(self) -> str: ...

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteoformSignature,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BuiltProteoformRelease:
    """Typed release outcome plus bytes only when the release is approved."""

    result: ProteoformReleaseResult
    package_bytes: bytes | None

    def __post_init__(self) -> None:
        released = self.result.disposition is ProteoformReleaseDisposition.RELEASED
        if released != (self.package_bytes is not None):
            raise _BuiltReleaseInvariantError


@dataclass(frozen=True, slots=True)
class _PreparedRelease:
    request: BuildProteoformReleaseRequest
    caller_bytes: dict[str, bytes]
    stages: dict[str, StageResult]
    manifest: ProteoformReproducibilityManifest


class M0408ProteoformReleaseEngine:
    """Build or inspect one immutable protein-inference release without persistence."""

    __slots__ = ("_verifier",)

    def __init__(self, verifier: ProteoformSignatureVerifier | None = None) -> None:
        self._verifier = verifier

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteoformRelease:
        prepared = _prepare_release(request, artifacts_by_path, stage_results_by_module)
        verification = _signature_verification(prepared, self._verifier)
        return _present_release(prepared, verification)

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteoformReproducibilityManifest:
        return _prepare_release(request, artifacts_by_path, stage_results_by_module).manifest

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> ProteoformReleaseVerification:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return _verify_package(validated, package_bytes, self._verifier)


def build_proteoform_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
    verifier: ProteoformSignatureVerifier | None = None,
) -> BuiltProteoformRelease:
    """Build a release or typed quarantine; quarantine always returns no bytes."""

    return M0408ProteoformReleaseEngine(verifier).build(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def build_proteoform_release_manifest(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> ProteoformReproducibilityManifest:
    """Prepare the deterministic unsigned manifest for external statement signing."""

    return M0408ProteoformReleaseEngine().build_manifest(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def verify_proteoform_release(
    result: object,
    package_bytes: bytes,
    verifier: ProteoformSignatureVerifier | None = None,
) -> ProteoformReleaseVerification:
    """Verify package content first, then authenticity through the injected boundary."""

    return M0408ProteoformReleaseEngine(verifier).verify(result, package_bytes)


def preflight_proteoform_release_authorization(candidate: object) -> None:
    """Reject denied raw requests before artifact or stage mappings are traversed."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BuildProteoformReleaseRequest in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        context: object = dict.get(storage, "context")
    elif dict in candidate_mro:
        context = dict.get(cast("dict[object, object]", candidate), "context")
    else:
        raise ProteoformReleaseAuthorizationError
    references = _member(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _member(_member(references, role), "state") != state for role, state in expected.items()
    ):
        raise ProteoformReleaseAuthorizationError


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(storage, field) if type(storage) is dict else None
    return None


def _prepare_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> _PreparedRelease:
    preflight_proteoform_release_authorization(request)
    validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
    caller_bytes = _validate_caller_bytes(validated, artifacts_by_path)
    stages = _validate_stage_results(validated, caller_bytes, stage_results_by_module)
    _validate_stage_chain(validated, stages)
    _validate_parent_receipt(validated, caller_bytes, stages)
    return _PreparedRelease(
        request=validated,
        caller_bytes=caller_bytes,
        stages=stages,
        manifest=_build_manifest(validated, stages),
    )


def _validate_caller_bytes(
    request: BuildProteoformReleaseRequest,
    supplied: Mapping[str, object],
) -> dict[str, bytes]:
    expected_paths = {item.path for item in request.artifacts}
    try:
        actual_paths = set(supplied.keys())
    except Exception as error:
        raise ProteoformReleaseInputError(
            ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        ) from error
    if actual_paths != expected_paths:
        raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH)
    result: dict[str, bytes] = {}
    for artifact in sorted(request.artifacts, key=lambda item: item.path):
        try:
            content = supplied[artifact.path]
        except Exception as error:
            raise ProteoformReleaseInputError(
                ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
            ) from error
        if type(content) is not bytes:
            raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.ARTIFACT_TYPE_INVALID)
        if len(content) != artifact.declared_size:
            raise ProteoformReleaseInputError(
                ProteoformReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH
            )
        if sha256_bytes(content) != artifact.reference.digest:
            raise ProteoformReleaseInputError(
                ProteoformReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH
            )
        result[artifact.path] = content
    return result


def _validate_parent_receipt(
    request: BuildProteoformReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    stages: Mapping[str, StageResult],
) -> None:
    parent = next(
        item
        for item in request.artifacts
        if item.role is ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF
    )
    content = caller_bytes[parent.path]
    try:
        strict_json_loads(content, max_bytes=M0408_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(content, strict=True)
        _require_canonical_artifact_bytes(receipt, content)
    except (StrictJsonError, ValidationError, ValueError) as error:
        raise ProteoformReleaseInputError(
            ProteoformReleaseInputErrorCode.PARENT_JSON_INVALID
        ) from error
    identity = cast("ProteoformIdentityLineageResolution", stages["GLIO-PROTEOGEN-M04-02"])
    if (
        receipt.identity_resolution_digest != identity.identity_resolution_digest
        or receipt.intended_use_evidence_digest
        != request.context.references.intended_use.evidence.digest
        or receipt.terminal_routing_result_digest != stages["GLIO-PROTEOGEN-M04-07"].result_digest
    ):
        raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.CHAIN_MISMATCH)


def _validate_stage_results(
    request: BuildProteoformReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    supplied: Mapping[str, object],
) -> dict[str, StageResult]:
    try:
        modules = set(supplied.keys())
    except Exception as error:
        raise ProteoformReleaseInputError(
            ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
        ) from error
    if modules != set(_STAGE_MODULES):
        raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH)
    artifact_by_role = {item.role: item for item in request.artifacts}
    results: dict[str, StageResult] = {}
    for module in _STAGE_MODULES:
        artifact = artifact_by_role[_ROLE_BY_MODULE[module]]
        try:
            supplied_result = supplied[module]
        except Exception as error:
            raise ProteoformReleaseInputError(
                ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
            ) from error
        try:
            content = caller_bytes[artifact.path]
            strict_json_loads(
                content,
                max_bytes=M0408_MAX_ARTIFACT_BYTES,
            )
            parsed = _parse_stage_artifact(module, content)
        except Exception as error:
            raise ProteoformReleaseInputError(
                ProteoformReleaseInputErrorCode.STAGE_JSON_INVALID
            ) from error
        if type(supplied_result) is not _STAGE_TYPE_BY_MODULE[module]:
            raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.STAGE_RESULT_MISMATCH)
        if parsed != supplied_result:
            raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.STAGE_RESULT_MISMATCH)
        results[module] = parsed
    return results


def _stage_adapter(module: StageModule) -> TypeAdapter[object]:
    adapters: dict[StageModule, TypeAdapter[object]] = {
        "GLIO-PROTEOGEN-M04-01": cast("TypeAdapter[object]", _M0401_ADAPTER),
        "GLIO-PROTEOGEN-M04-02": cast("TypeAdapter[object]", _M0402_ADAPTER),
        "GLIO-PROTEOGEN-M04-03": cast("TypeAdapter[object]", _M0403_ADAPTER),
        "GLIO-PROTEOGEN-M04-04": cast("TypeAdapter[object]", _M0404_ADAPTER),
        "GLIO-PROTEOGEN-M04-05": cast("TypeAdapter[object]", _M0405_ADAPTER),
        "GLIO-PROTEOGEN-M04-06": cast("TypeAdapter[object]", _M0406_ADAPTER),
        "GLIO-PROTEOGEN-M04-07": cast("TypeAdapter[object]", _M0407_ADAPTER),
    }
    return adapters[module]


def _parse_stage_bytes(
    module: StageModule,
    content: bytes,
) -> StageResult:
    return cast("StageResult", _stage_adapter(module).validate_json(content, strict=True))


@lru_cache(maxsize=32)
def _parse_stage_artifact_cached(module: StageModule, content: bytes) -> StageResult:
    """Validate immutable stage bytes once, then reuse the closed typed result.

    The cache key includes the complete bytes and module ABI.  The first call
    still performs strict JSON parsing, typed validation, and canonical-byte
    equality; later deterministic replays only reuse that already-validated
    immutable model, avoiding repeated multi-megabyte Pydantic reconstruction.
    """

    strict_json_loads(content, max_bytes=M0408_MAX_ARTIFACT_BYTES)
    parsed = _parse_stage_bytes(module, content)
    _require_canonical_artifact_bytes(parsed, content)
    return parsed


def _parse_stage_artifact(module: StageModule, content: bytes) -> StageResult:
    """Return an isolated copy of a cached, fully admitted stage result."""

    return _parse_stage_artifact_cached(module, content).model_copy(deep=True)


def _validate_stage_chain(
    request: BuildProteoformReleaseRequest,
    stages: Mapping[str, StageResult],
) -> None:
    """Close the complete M04-01 through M04-07 result chain."""

    m0401 = cast("ProteoformProtocolConformanceResult", stages["GLIO-PROTEOGEN-M04-01"])
    m0402 = cast("ProteoformIdentityLineageResolution", stages["GLIO-PROTEOGEN-M04-02"])
    m0403 = cast("ProteoformRawInputValidationResult", stages["GLIO-PROTEOGEN-M04-03"])
    m0404 = cast("ProteoformQualityResult", stages["GLIO-PROTEOGEN-M04-04"])
    m0405 = cast("ProteoformArtifactDetectionResult", stages["GLIO-PROTEOGEN-M04-05"])
    m0406 = cast("ProteoformHarmonizationResult", stages["GLIO-PROTEOGEN-M04-06"])
    m0407 = cast("ProteoformSupportRouteResult", stages["GLIO-PROTEOGEN-M04-07"])
    stage_results = (m0401, m0402, m0403, m0404, m0405, m0406, m0407)
    identity = _identity_subject(m0401)
    intended_use_digests = {
        _stage_context(item).references.intended_use.evidence.digest for item in stage_results
    }
    stage_times = tuple(item.completed_at for item in stage_results)
    if (
        m0402.protocol_result_digest != m0401.result_digest
        or m0403.request.lineage_result.result_digest != m0402.result_digest
        or m0404.request.raw_input_result.result_digest != m0403.result_digest
        or m0405.request.quality_result.result_digest != m0404.result_digest
        or m0406.request.artifact_result.result_digest != m0405.result_digest
        or m0406.request.artifact_receipt.quality_result_digest != m0404.result_digest
        or m0406.request.artifact_receipt.artifact_result_digest != m0405.result_digest
        or m0407.request.prerequisites.quality_result.result_digest != m0404.result_digest
        or m0407.request.prerequisites.harmonization_result.result_digest != m0406.result_digest
        or m0407.request.prerequisites.quality.result_digest != m0404.result_digest
        or m0407.request.prerequisites.harmonization.result_digest != m0406.result_digest
        or {_identity_subject(item) for item in stage_results} != {identity}
        or m0407.request.context.references.identity_lineage.binding_digest != identity
        or request.context.references.identity_lineage.binding_digest != identity
        or intended_use_digests != {request.context.references.intended_use.evidence.digest}
        or request.context.references.quality.evidence.digest != m0404.result_digest
        or request.context.references.support.evidence.digest != m0407.result_digest
        or stage_times != tuple(sorted(stage_times))
        or stage_times[-1] > request.signature.issued_at
    ):
        raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.CHAIN_MISMATCH)


def _identity_subject(result: StageResult) -> str:
    record = next(
        (
            item
            for item in result.provenance.control_decisions
            if item.role is ControlRole.IDENTITY_LINEAGE
        ),
        None,
    )
    if record is None or record.subject_digest is None:
        raise ProteoformReleaseInputError(ProteoformReleaseInputErrorCode.CHAIN_MISMATCH)
    return record.subject_digest


def _stage_context(result: StageResult) -> ExecutionContext:
    context = getattr(result, "context", None)
    if isinstance(context, ExecutionContext):
        return context
    return result.request.context


def _stage_result_digest(result: StageResult) -> str:
    return result.result_digest


def _build_manifest(
    request: BuildProteoformReleaseRequest,
    stages: Mapping[str, StageResult],
) -> ProteoformReproducibilityManifest:
    m0404 = cast("ProteoformQualityResult", stages["GLIO-PROTEOGEN-M04-04"])
    m0406 = cast(
        "ProteoformHarmonizationResult",
        stages["GLIO-PROTEOGEN-M04-06"],
    )
    m0407 = cast("ProteoformSupportRouteResult", stages["GLIO-PROTEOGEN-M04-07"])
    artifacts_by_role = {item.role: item for item in request.artifacts}
    stage_records = tuple(
        _stage_record(
            module,
            stages[module],
            artifacts_by_role[_ROLE_BY_MODULE[module]].reference.digest,
        )
        for module in _STAGE_MODULES
    )
    return ProteoformReproducibilityManifest(
        release_id=request.release_id,
        release_version=request.release_version,
        artifacts=tuple(sorted(request.artifacts, key=lambda item: item.path)),
        stages=stage_records,
        software_versions=tuple(
            sorted(request.software_versions, key=lambda item: item.software_id)
        ),
        reference_versions=tuple(
            sorted(request.reference_versions, key=lambda item: item.reference_id)
        ),
        reproduction_evidence=request.reproduction_evidence,
        reproduction_evidence_digest=reproduction_evidence_digest(request.reproduction_evidence),
        m0406_transformation_manifest_digest=(
            m0406.transformation_manifest.manifest_digest
            if m0406.transformation_manifest is not None
            else None
        ),
        m0406_analysis_digest=(
            m0406.analysis.analysis_digest if m0406.analysis is not None else None
        ),
        m0404_quality_disposition=m0404.disposition.value,
        m0405_artifact_disposition=cast(
            "ProteoformArtifactDetectionResult", stages["GLIO-PROTEOGEN-M04-05"]
        ).disposition.value,
        m0406_harmonization_disposition=m0406.disposition.value,
        terminal_routing_disposition=m0407.disposition.value,
        identity_resolution_digest=_identity_subject(m0406),
        intended_use_evidence_digest=request.context.references.intended_use.evidence.digest,
        terminal_routing_result_digest=m0407.result_digest,
        policy_digest=policy_digest(request.policy),
    )


def _stage_record(
    module: StageModule,
    result: StageResult,
    byte_digest: str,
) -> ProteoformStageProvenance:
    upstream: tuple[str, ...] = ()
    if isinstance(result, ProteoformIdentityLineageResolution):
        upstream = (result.protocol_result_digest,)
    elif isinstance(result, ProteoformRawInputValidationResult):
        upstream = tuple(
            sorted(
                (
                    result.request.lineage_result.result_digest,
                    result.request.lineage_result.request.protocol_result.result_digest,
                )
            )
        )
    elif isinstance(result, ProteoformQualityResult):
        raw = result.request.raw_input_result
        upstream = tuple(
            sorted(
                (
                    raw.request.lineage_result.request.protocol_result.result_digest,
                    raw.request.lineage_result.result_digest,
                    raw.result_digest,
                )
            )
        )
    elif isinstance(result, ProteoformArtifactDetectionResult):
        upstream = (result.request.quality_result.result_digest,)
    elif isinstance(result, ProteoformHarmonizationResult):
        upstream = tuple(
            sorted(
                (
                    result.request.artifact_receipt.quality_result_digest,
                    result.request.artifact_receipt.artifact_result_digest,
                )
            )
        )
    elif isinstance(result, ProteoformSupportRouteResult):
        upstream = tuple(
            sorted(
                (
                    result.request.prerequisites.quality.result_digest,
                    result.request.prerequisites.harmonization.result_digest,
                )
            )
        )
    return ProteoformStageProvenance(
        module_id=ProteoformStageModuleId(module),
        module_version=result.result_version,
        result_digest=_stage_result_digest(result),
        request_digest=result.request_digest,
        byte_digest=byte_digest,
        disposition=result.disposition.value,
        generated_at=result.completed_at,
        configuration_digest=result.configuration_digest,
        identity_resolution_digest=_identity_subject(result),
        bound_upstream_result_digests=upstream,
        human_review_required=result.human_review_required,
    )


def _signature_verification(
    prepared: _PreparedRelease,
    verifier: ProteoformSignatureVerifier | None,
) -> ProteoformSignatureVerification:
    request = prepared.request
    statement = _statement_digest(prepared)
    chain_releasable = not expected_release_quarantine_reasons(
        prepared.manifest,
        ProteoformSignatureVerification(
            algorithm=request.signature.algorithm,
            key_id=request.signature.key_id,
            statement_digest=statement,
            verified=True,
            verifier_id=request.policy.allowed_verifier_ids[0],
            reason_code=ProteoformSignatureVerificationReason.VERIFIED,
        ),
    )
    if not chain_releasable:
        return _verification_receipt(
            request.signature,
            statement,
            ProteoformSignatureVerificationReason.NOT_ATTEMPTED,
        )
    if request.signature.claimed_statement_digest != statement:
        return _verification_receipt(
            request.signature,
            statement,
            ProteoformSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in request.policy.allowed_verifier_ids:
        return _verification_receipt(
            request.signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    try:
        accepted = verifier.verify(
            statement_digest=statement,
            signature=request.signature,
        )
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return _verification_receipt(
            request.signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            request.signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        request.signature,
        statement,
        (
            ProteoformSignatureVerificationReason.VERIFIED
            if accepted
            else ProteoformSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _safe_verifier_id(verifier: ProteoformSignatureVerifier | None) -> str | None:
    if verifier is None:
        return None
    try:
        value = verifier.verifier_id
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return None
    return value if type(value) is str else None


def _verification_receipt(
    signature: ExternalProteoformSignature,
    statement: str,
    reason: ProteoformSignatureVerificationReason,
    *,
    verifier_id: str | None = None,
) -> ProteoformSignatureVerification:
    return ProteoformSignatureVerification(
        verifier_id=verifier_id,
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        statement_digest=statement,
        verified=reason is ProteoformSignatureVerificationReason.VERIFIED,
        reason_code=reason,
    )


def _verify_external_signature(  # noqa: PLR0911 - ordered fail-closed verifier outcomes.
    *,
    signature: ExternalProteoformSignature,
    statement_digest: str,
    allowed_verifier_ids: tuple[str, ...],
    chain_releasable: bool,
    verifier: ProteoformSignatureVerifier | None,
) -> ProteoformSignatureVerification:
    """Apply the external verifier only after the release chain is eligible."""
    if type(allowed_verifier_ids) is not tuple or type(chain_releasable) is not bool:
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.NOT_ATTEMPTED
        )
    if not chain_releasable:
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.NOT_ATTEMPTED
        )
    if signature.claimed_statement_digest != statement_digest:
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.STATEMENT_MISMATCH
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in allowed_verifier_ids:
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
        )
    try:
        accepted = verifier.verify(statement_digest=statement_digest, signature=signature)
    except Exception:  # noqa: BLE001 - external verifier is a fail-closed boundary.
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            signature, statement_digest, ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
        )
    return _verification_receipt(
        signature,
        statement_digest,
        (
            ProteoformSignatureVerificationReason.VERIFIED
            if accepted
            else ProteoformSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _statement_digest(prepared: _PreparedRelease) -> str:
    request = prepared.request
    return signing_statement_digest(
        active_manifest_digest=manifest_digest(prepared.manifest),
        active_policy_digest=policy_digest(request.policy),
        release_id=request.release_id,
        release_version=request.release_version,
        identity_resolution_digest=prepared.manifest.identity_resolution_digest,
        intended_use_evidence_digest=prepared.manifest.intended_use_evidence_digest,
        terminal_routing_result_digest=prepared.manifest.terminal_routing_result_digest,
    )


def _present_release(
    prepared: _PreparedRelease,
    verification: ProteoformSignatureVerification,
) -> BuiltProteoformRelease:
    request = prepared.request
    presented_policy = request.policy.model_copy(
        update={
            "allowed_signature_algorithms": tuple(
                sorted(request.policy.allowed_signature_algorithms)
            ),
            "allowed_verifier_ids": tuple(sorted(request.policy.allowed_verifier_ids)),
        }
    )
    request_hash = canonical_request_digest(request)
    context_hash = context_digest(request.context)
    active_policy_hash = policy_digest(request.policy)
    active_manifest_hash = manifest_digest(prepared.manifest)
    reasons = expected_release_quarantine_reasons(prepared.manifest, verification)
    disposition = (
        ProteoformReleaseDisposition.RELEASED
        if not reasons
        else ProteoformReleaseDisposition.QUARANTINED
    )
    package_bytes: bytes | None = None
    descriptor: ProteoformReleasePackageDescriptor | None = None
    if disposition is ProteoformReleaseDisposition.RELEASED:
        package_bytes, descriptor = _build_package(prepared, verification)
    controls = _control_records(request.context)
    candidate = ProteoformReleaseResult.model_construct(
        release_result_id=f"result.m0408.{request_hash.removeprefix('sha256:')}",
        request_digest=request_hash,
        context_digest=context_hash,
        context=request.context,
        policy_digest=active_policy_hash,
        policy=presented_policy,
        manifest_digest=active_manifest_hash,
        manifest=prepared.manifest,
        signature=request.signature,
        signature_verification=verification,
        result_digest="sha256:" + ("0" * 64),
        disposition=disposition,
        package_descriptor=descriptor,
        quarantine_reasons=reasons,
        support=_support(disposition),
        uncertainty=_uncertainty(),
        provenance=_provenance(
            request,
            prepared.manifest,
            request_hash,
            context_hash,
            active_policy_hash,
            active_manifest_hash,
            controls,
        ),
        evidence=_evidence(request),
        limitations=_LIMITATIONS,
        human_review_required=disposition is ProteoformReleaseDisposition.QUARANTINED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )
    payload = candidate.model_dump(mode="python", by_alias=True, exclude_none=False)
    payload["result_digest"] = result_payload_digest(payload)
    result = _RESULT_ADAPTER.validate_python(payload, strict=True)
    return BuiltProteoformRelease(result=result, package_bytes=package_bytes)


def _build_package(
    prepared: _PreparedRelease,
    verification: ProteoformSignatureVerification,
) -> tuple[bytes, ProteoformReleasePackageDescriptor]:
    manifest_bytes = canonical_json_bytes(normalized_manifest(prepared.manifest))
    receipt_bytes = canonical_json_bytes(
        verification.model_dump(mode="python", by_alias=True, exclude_none=False)
    )
    members = (
        *(
            PackageMember(path=path, content=content)
            for path, content in prepared.caller_bytes.items()
        ),
        PackageMember(path=M0408_MANIFEST_PATH, content=manifest_bytes),
        PackageMember(path=M0408_SIGNATURE_RECEIPT_PATH, content=receipt_bytes),
    )
    package_bytes = build_canonical_ustar(
        members,
        fixed_mtime=0,
        file_mode=0o644,
    )
    role_by_path = {item.path: item.role for item in prepared.request.artifacts}
    descriptor_members = tuple(
        ProteoformReleaseMember(
            path=item.path,
            byte_size=len(item.content),
            digest=sha256_bytes(item.content),
            role=role_by_path.get(item.path),
        )
        for item in sorted(members, key=lambda value: value.path)
    )
    return package_bytes, ProteoformReleasePackageDescriptor(
        byte_size=len(package_bytes),
        digest=sha256_bytes(package_bytes),
        members=descriptor_members,
    )


def _support(disposition: ProteoformReleaseDisposition) -> SupportDecision:
    if disposition is ProteoformReleaseDisposition.RELEASED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="proteoform_release_packaged",
            rationale=M0408_RELEASED_SUPPORT_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="proteoform_release_quarantined",
        rationale=M0408_QUARANTINED_SUPPORT_RATIONALE,
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(M0408_UNCERTAINTY_RATIONALES["measurement"]),
        sampling=_not_estimable(M0408_UNCERTAINTY_RATIONALES["sampling"]),
        parameter=_not_estimable(M0408_UNCERTAINTY_RATIONALES["parameter"]),
        model_form=_not_estimable(M0408_UNCERTAINTY_RATIONALES["model_form"]),
        identification=_not_estimable(M0408_UNCERTAINTY_RATIONALES["identification"]),
        support=_not_estimable(M0408_UNCERTAINTY_RATIONALES["support"]),
        transport=_not_estimable(M0408_UNCERTAINTY_RATIONALES["transport"]),
        sensitivity_notes=M0408_SENSITIVITY_NOTES,
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration, None),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage, refs.identity_lineage.binding_digest),
        (ControlRole.PROVENANCE, refs.provenance, None),
        (ControlRole.CONSENT, refs.consent, None),
        (ControlRole.QUALITY, refs.quality, None),
        (ControlRole.SUPPORT, refs.support, None),
        (ControlRole.INTENDED_USE, refs.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(  # noqa: PLR0913,PLR0917 - exact release receipt inputs.
    request: BuildProteoformReleaseRequest,
    manifest: ProteoformReproducibilityManifest,
    request_hash: str,
    context_hash: str,
    active_policy_hash: str,
    active_manifest_hash: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    refs = request.context.references
    inputs = release_provenance_input_digests(
        request,
        manifest,
        request_digest=request_hash,
        context_digest=context_hash,
        policy_digest=active_policy_hash,
        manifest_digest=active_manifest_hash,
        controls=controls,
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0408.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0408_MODULE_ID,
        module_version=M0408_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(inputs)),
        configuration_digest=active_policy_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: BuildProteoformReleaseRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        sorted(
            (
                EvidenceReference(reference=reference, role="evidence", claim=claim)
                for reference, claim in release_evidence_index(request)
            ),
            key=canonical_json_bytes,
        )
    )


def _verify_package(  # noqa: C901, PLR0911 - ordered typed verification precedence.
    result: ProteoformReleaseResult,
    package_bytes: bytes,
    verifier: ProteoformSignatureVerifier | None,
) -> ProteoformReleaseVerification:
    if type(package_bytes) is not bytes:
        raise _PackageBytesTypeError
    descriptor = result.package_descriptor
    if len(package_bytes) > M0408_MAX_PACKAGE_BYTES:
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.DESCRIPTOR_MISMATCH,
        )
    if descriptor is None or (
        len(package_bytes) != descriptor.byte_size
        or sha256_bytes(package_bytes) != descriptor.digest
    ):
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.DESCRIPTOR_MISMATCH,
        )
    try:
        _preflight_archive_inventory(package_bytes)
        inspected = inspect_canonical_ustar(package_bytes)
    except PackageAssemblyError:
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.PACKAGE_INVALID,
        )
    paths = [item.path for item in inspected]
    if len(paths) != len(set(paths)) or set(paths) != {item.path for item in descriptor.members}:
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.INVENTORY_MISMATCH,
        )
    expected_members = {item.path: item for item in descriptor.members}
    if any(
        (
            len(item.content),
            sha256_bytes(item.content),
        )
        != (
            expected_members[item.path].byte_size,
            expected_members[item.path].digest,
        )
        for item in inspected
    ):
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.CONTENT_MISMATCH,
        )
    content_by_path = {item.path: item.content for item in inspected}
    manifest_bytes = canonical_json_bytes(normalized_manifest(result.manifest))
    receipt_bytes = canonical_json_bytes(
        result.signature_verification.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=False,
        )
    )
    if (
        content_by_path[M0408_MANIFEST_PATH] != manifest_bytes
        or content_by_path[M0408_SIGNATURE_RECEIPT_PATH] != receipt_bytes
    ):
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.MANIFEST_MISMATCH,
        )
    if not _package_parent_receipt_is_bound(result, content_by_path):
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.CONTENT_MISMATCH,
        )
    try:
        rebuilt = build_canonical_ustar(
            inspected,
            fixed_mtime=0,
            file_mode=0o644,
        )
    except PackageAssemblyError:
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.PACKAGE_INVALID,
        )
    if rebuilt != package_bytes:
        return _package_failure(
            result,
            ProteoformPackageVerificationReason.PACKAGE_NOT_CANONICAL,
        )
    verification = _verify_result_signature(result, verifier)
    reason = {
        ProteoformSignatureVerificationReason.VERIFIED: (
            ProteoformPackageVerificationReason.VERIFIED
        ),
        ProteoformSignatureVerificationReason.STATEMENT_MISMATCH: (
            ProteoformPackageVerificationReason.STATEMENT_MISMATCH
        ),
        ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE: (
            ProteoformPackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
        ProteoformSignatureVerificationReason.VERIFIER_REJECTED: (
            ProteoformPackageVerificationReason.VERIFIER_REJECTED
        ),
        ProteoformSignatureVerificationReason.NOT_ATTEMPTED: (
            ProteoformPackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
    }[verification.reason_code]
    return ProteoformReleaseVerification(
        content_verified=True,
        authenticity_verified=verification.verified,
        verified=verification.verified,
        package_digest=descriptor.digest,
        manifest_digest=result.manifest_digest,
        member_count=len(inspected),
        signature_verification=verification,
        reason_code=reason,
    )


def _preflight_archive_inventory(package_bytes: bytes) -> None:
    """Bound TarInfo metadata before the shared reader allocates member contents."""

    try:
        with tarfile.open(fileobj=io.BytesIO(package_bytes), mode="r:") as archive:
            member_count = 0
            declared_total = 0
            for info in archive:
                member_count += 1
                declared_total += info.size
                if (
                    member_count > M0408_ARCHIVE_MEMBER_COUNT
                    or not info.isfile()
                    or info.size > M0408_MAX_ARTIFACT_BYTES
                    or declared_total > M0408_MAX_PACKAGE_BYTES
                ):
                    raise PackageAssemblyError.invalid_archive()
            if member_count != M0408_ARCHIVE_MEMBER_COUNT:
                raise PackageAssemblyError.invalid_archive()
    except (tarfile.TarError, OSError) as error:
        raise PackageAssemblyError.invalid_archive() from error


def _package_parent_receipt_is_bound(
    result: ProteoformReleaseResult,
    content_by_path: Mapping[str, bytes],
) -> bool:
    parent_path = next(
        item.path
        for item in result.manifest.artifacts
        if item.role is ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF
    )
    try:
        parent_bytes = content_by_path[parent_path]
        strict_json_loads(parent_bytes, max_bytes=M0408_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(parent_bytes, strict=True)
        if canonical_json_bytes(receipt) != parent_bytes:
            return False
    except (KeyError, StrictJsonError, ValidationError):
        return False
    return (
        receipt.identity_resolution_digest == result.manifest.identity_resolution_digest
        and receipt.intended_use_evidence_digest == result.manifest.intended_use_evidence_digest
        and receipt.terminal_routing_result_digest == result.manifest.terminal_routing_result_digest
    )


def _verify_result_signature(
    result: ProteoformReleaseResult,
    verifier: ProteoformSignatureVerifier | None,
) -> ProteoformSignatureVerification:
    signature = result.signature
    statement = result.signature_verification.statement_digest
    if signature.claimed_statement_digest != statement:
        return _verification_receipt(
            signature,
            statement,
            ProteoformSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in result.policy.allowed_verifier_ids:
        return _verification_receipt(
            signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    try:
        accepted = verifier.verify(statement_digest=statement, signature=signature)
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return _verification_receipt(
            signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            signature,
            statement,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        signature,
        statement,
        (
            ProteoformSignatureVerificationReason.VERIFIED
            if accepted
            else ProteoformSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _package_failure(
    result: ProteoformReleaseResult,
    reason: ProteoformPackageVerificationReason,
) -> ProteoformReleaseVerification:
    signature = _verification_receipt(
        result.signature,
        result.signature_verification.statement_digest,
        ProteoformSignatureVerificationReason.NOT_ATTEMPTED,
    )
    return ProteoformReleaseVerification(
        content_verified=False,
        authenticity_verified=False,
        verified=False,
        member_count=0,
        signature_verification=signature,
        reason_code=reason,
    )


__all__ = [
    "BuiltProteoformRelease",
    "M0408ProteoformReleaseEngine",
    "ProteoformReleaseAuthorizationError",
    "ProteoformReleaseInputError",
    "ProteoformReleaseInputErrorCode",
    "ProteoformSignatureVerifier",
    "build_proteoform_release",
    "build_proteoform_release_manifest",
    "preflight_proteoform_release_authorization",
    "verify_proteoform_release",
]
