"""Deterministic, quarantine-first M03-08 protein-inference release engine."""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m03_01 import ProteinInferenceProtocolConformanceResult
from glio_proteogen.contracts.m03_02 import ProteinInferenceIdentityLineageResolution
from glio_proteogen.contracts.m03_03 import ProteinInferenceRawAdmissionResult
from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
from glio_proteogen.contracts.m03_05 import ProteinInferenceArtifactDetectionResult
from glio_proteogen.contracts.m03_06 import ProteinInferenceHarmonizationResult
from glio_proteogen.contracts.m03_07 import ProteinInferenceSupportRouteResult
from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_AUTHORITY_LIMITATION_CODE,
    M0308_AUTHORITY_LIMITATION_STATEMENT,
    M0308_CONTRACT_VERSION,
    M0308_MANIFEST_PATH,
    M0308_MAX_ARTIFACT_BYTES,
    M0308_MAX_PACKAGE_BYTES,
    M0308_MODULE_ID,
    M0308_PACKAGE_LIMITATION_CODE,
    M0308_PACKAGE_LIMITATION_STATEMENT,
    M0308_QUARANTINED_SUPPORT_RATIONALE,
    M0308_RELEASED_SUPPORT_RATIONALE,
    M0308_REPRODUCIBILITY_LIMITATION_CODE,
    M0308_REPRODUCIBILITY_LIMITATION_STATEMENT,
    M0308_SENSITIVITY_NOTES,
    M0308_SIGNATURE_RECEIPT_PATH,
    M0308_UNCERTAINTY_RATIONALES,
    BuildProteinInferenceReleaseRequest,
    ExternalProteinInferenceSignature,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceParentComplexActivityReceipt,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleaseMember,
    ProteinInferenceReleasePackageDescriptor,
    ProteinInferenceReleaseResult,
    ProteinInferenceReleaseVerification,
    ProteinInferenceReproducibilityManifest,
    ProteinInferenceSignatureVerification,
    ProteinInferenceSignatureVerificationReason,
    ProteinInferenceStageModuleId,
    ProteinInferenceStageProvenance,
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
    ProteinInferenceProtocolConformanceResult
    | ProteinInferenceIdentityLineageResolution
    | ProteinInferenceRawAdmissionResult
    | ProteinInferenceQualityResult
    | ProteinInferenceArtifactDetectionResult
    | ProteinInferenceHarmonizationResult
    | ProteinInferenceSupportRouteResult
)
StageModule = Literal[
    "GLIO-PROTEOGEN-M03-01",
    "GLIO-PROTEOGEN-M03-02",
    "GLIO-PROTEOGEN-M03-03",
    "GLIO-PROTEOGEN-M03-04",
    "GLIO-PROTEOGEN-M03-05",
    "GLIO-PROTEOGEN-M03-06",
    "GLIO-PROTEOGEN-M03-07",
]

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteinInferenceReleaseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceReleaseResult)
_PARENT_ADAPTER: Final = TypeAdapter(ProteinInferenceParentComplexActivityReceipt)
_M0301_ADAPTER: Final = TypeAdapter(ProteinInferenceProtocolConformanceResult)
_M0302_ADAPTER: Final = TypeAdapter(ProteinInferenceIdentityLineageResolution)
_M0303_ADAPTER: Final = TypeAdapter(ProteinInferenceRawAdmissionResult)
_M0304_ADAPTER: Final = TypeAdapter(ProteinInferenceQualityResult)
_M0305_ADAPTER: Final = TypeAdapter(ProteinInferenceArtifactDetectionResult)
_M0306_ADAPTER: Final = TypeAdapter(ProteinInferenceHarmonizationResult)
_M0307_ADAPTER: Final = TypeAdapter(ProteinInferenceSupportRouteResult)

_STAGE_MODULES: Final[tuple[StageModule, ...]] = (
    "GLIO-PROTEOGEN-M03-01",
    "GLIO-PROTEOGEN-M03-02",
    "GLIO-PROTEOGEN-M03-03",
    "GLIO-PROTEOGEN-M03-04",
    "GLIO-PROTEOGEN-M03-05",
    "GLIO-PROTEOGEN-M03-06",
    "GLIO-PROTEOGEN-M03-07",
)
_ROLE_BY_MODULE: Final = {
    "GLIO-PROTEOGEN-M03-01": ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE,
    "GLIO-PROTEOGEN-M03-02": ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE,
    "GLIO-PROTEOGEN-M03-03": ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION,
    "GLIO-PROTEOGEN-M03-04": ProteinInferenceReleaseArtifactRole.M03_04_QUALITY,
    "GLIO-PROTEOGEN-M03-05": ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION,
    "GLIO-PROTEOGEN-M03-06": ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION,
    "GLIO-PROTEOGEN-M03-07": ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE,
}
_STAGE_TYPE_BY_MODULE: Final[dict[StageModule, type[object]]] = {
    "GLIO-PROTEOGEN-M03-01": ProteinInferenceProtocolConformanceResult,
    "GLIO-PROTEOGEN-M03-02": ProteinInferenceIdentityLineageResolution,
    "GLIO-PROTEOGEN-M03-03": ProteinInferenceRawAdmissionResult,
    "GLIO-PROTEOGEN-M03-04": ProteinInferenceQualityResult,
    "GLIO-PROTEOGEN-M03-05": ProteinInferenceArtifactDetectionResult,
    "GLIO-PROTEOGEN-M03-06": ProteinInferenceHarmonizationResult,
    "GLIO-PROTEOGEN-M03-07": ProteinInferenceSupportRouteResult,
}
_LIMITATIONS: Final = (
    Limitation(
        code=M0308_PACKAGE_LIMITATION_CODE,
        statement=M0308_PACKAGE_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0308_AUTHORITY_LIMITATION_CODE,
        statement=M0308_AUTHORITY_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0308_REPRODUCIBILITY_LIMITATION_CODE,
        statement=M0308_REPRODUCIBILITY_LIMITATION_STATEMENT,
    ),
)


class ProteinInferenceReleaseAuthorizationError(PermissionError):
    """The raw request does not authorize release-input traversal."""

    def __init__(self) -> None:
        super().__init__("M03-08 release operation is not authorized")


class ProteinInferenceReleaseInputErrorCode(StrEnum):
    ARTIFACT_MAPPING_MISMATCH = "artifact_mapping_mismatch"
    ARTIFACT_TYPE_INVALID = "artifact_type_invalid"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_DIGEST_MISMATCH = "artifact_digest_mismatch"
    PARENT_JSON_INVALID = "parent_json_invalid"
    STAGE_MAPPING_MISMATCH = "stage_mapping_mismatch"
    STAGE_JSON_INVALID = "stage_json_invalid"
    STAGE_RESULT_MISMATCH = "stage_result_mismatch"
    CHAIN_MISMATCH = "chain_mismatch"


class ProteinInferenceReleaseInputError(ValueError):
    """Caller bytes, stage objects, or cross-stage receipts are malformed."""

    def __init__(self, code: ProteinInferenceReleaseInputErrorCode) -> None:
        self.code = code
        super().__init__(f"M03-08 input rejected: {code.value}")


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


class ProteinInferenceSignatureVerifier(Protocol):
    """Narrow injected authenticity boundary; M03-08 owns the typed receipt."""

    @property
    def verifier_id(self) -> str: ...

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteinInferenceSignature,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BuiltProteinInferenceRelease:
    """Typed release outcome plus bytes only when the release is approved."""

    result: ProteinInferenceReleaseResult
    package_bytes: bytes | None

    def __post_init__(self) -> None:
        released = self.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
        if released != (self.package_bytes is not None):
            raise _BuiltReleaseInvariantError


@dataclass(frozen=True, slots=True)
class _PreparedRelease:
    request: BuildProteinInferenceReleaseRequest
    caller_bytes: dict[str, bytes]
    stages: dict[str, StageResult]
    manifest: ProteinInferenceReproducibilityManifest


class M0308ProteinInferenceReleaseEngine:
    """Build or inspect one immutable protein-inference release without persistence."""

    __slots__ = ("_verifier",)

    def __init__(self, verifier: ProteinInferenceSignatureVerifier | None = None) -> None:
        self._verifier = verifier

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteinInferenceRelease:
        prepared = _prepare_release(request, artifacts_by_path, stage_results_by_module)
        verification = _signature_verification(prepared, self._verifier)
        return _present_release(prepared, verification)

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteinInferenceReproducibilityManifest:
        return _prepare_release(request, artifacts_by_path, stage_results_by_module).manifest

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> ProteinInferenceReleaseVerification:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return _verify_package(validated, package_bytes, self._verifier)


def build_protein_inference_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
    verifier: ProteinInferenceSignatureVerifier | None = None,
) -> BuiltProteinInferenceRelease:
    """Build a release or typed quarantine; quarantine always returns no bytes."""

    return M0308ProteinInferenceReleaseEngine(verifier).build(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def build_protein_inference_release_manifest(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> ProteinInferenceReproducibilityManifest:
    """Prepare the deterministic unsigned manifest for external statement signing."""

    return M0308ProteinInferenceReleaseEngine().build_manifest(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def verify_protein_inference_release(
    result: object,
    package_bytes: bytes,
    verifier: ProteinInferenceSignatureVerifier | None = None,
) -> ProteinInferenceReleaseVerification:
    """Verify package content first, then authenticity through the injected boundary."""

    return M0308ProteinInferenceReleaseEngine(verifier).verify(result, package_bytes)


def preflight_protein_inference_release_authorization(candidate: object) -> None:
    """Reject denied raw requests before artifact or stage mappings are traversed."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BuildProteinInferenceReleaseRequest in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        context: object = dict.get(storage, "context")
    elif dict in candidate_mro:
        context = dict.get(cast("dict[object, object]", candidate), "context")
    else:
        raise ProteinInferenceReleaseAuthorizationError
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
        raise ProteinInferenceReleaseAuthorizationError


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
    preflight_protein_inference_release_authorization(request)
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
    request: BuildProteinInferenceReleaseRequest,
    supplied: Mapping[str, object],
) -> dict[str, bytes]:
    expected_paths = {item.path for item in request.artifacts}
    _bounded_mapping_keys(
        supplied,
        expected_paths,
        ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
    )
    result: dict[str, bytes] = {}
    for artifact in sorted(request.artifacts, key=lambda item: item.path):
        try:
            content = supplied[artifact.path]
        except Exception as error:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
            ) from error
        if type(content) is not bytes:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.ARTIFACT_TYPE_INVALID
            )
        if len(content) != artifact.declared_size:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH
            )
        if sha256_bytes(content) != artifact.reference.digest:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH
            )
        result[artifact.path] = content
    return result


def _validate_parent_receipt(
    request: BuildProteinInferenceReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    stages: Mapping[str, StageResult],
) -> None:
    parent = next(
        item
        for item in request.artifacts
        if item.role is ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF
    )
    content = caller_bytes[parent.path]
    try:
        strict_json_loads(content, max_bytes=M0308_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(content, strict=True)
        _require_canonical_artifact_bytes(receipt, content)
    except (StrictJsonError, ValidationError, ValueError) as error:
        raise ProteinInferenceReleaseInputError(
            ProteinInferenceReleaseInputErrorCode.PARENT_JSON_INVALID
        ) from error
    identity = cast("ProteinInferenceIdentityLineageResolution", stages["GLIO-PROTEOGEN-M03-02"])
    if (
        receipt.identity_resolution_digest != identity.identity_resolution_digest
        or receipt.intended_use_evidence_digest
        != request.context.references.intended_use.evidence.digest
        or receipt.support_route_result_digest != stages["GLIO-PROTEOGEN-M03-07"].result_digest
    ):
        raise ProteinInferenceReleaseInputError(
            ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH
        )


def _validate_stage_results(
    request: BuildProteinInferenceReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    supplied: Mapping[str, object],
) -> dict[str, StageResult]:
    _bounded_mapping_keys(
        supplied,
        set(_STAGE_MODULES),
        ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH,
    )
    artifact_by_role = {item.role: item for item in request.artifacts}
    results: dict[str, StageResult] = {}
    for module in _STAGE_MODULES:
        artifact = artifact_by_role[_ROLE_BY_MODULE[module]]
        try:
            supplied_result = supplied[module]
        except Exception as error:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
            ) from error
        try:
            content = caller_bytes[artifact.path]
            strict_json_loads(
                content,
                max_bytes=M0308_MAX_ARTIFACT_BYTES,
            )
            parsed = _parse_stage_bytes(module, content)
            _require_canonical_artifact_bytes(parsed, content)
        except Exception as error:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.STAGE_JSON_INVALID
            ) from error
        if type(supplied_result) is not _STAGE_TYPE_BY_MODULE[module]:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH
            )
        if parsed != supplied_result:
            raise ProteinInferenceReleaseInputError(
                ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH
            )
        results[module] = parsed
    return results


def _bounded_mapping_keys(
    supplied: Mapping[str, object],
    expected: set[str],
    error_code: ProteinInferenceReleaseInputErrorCode,
) -> set[str]:
    """Prove exact key-set equality without exhausting a caller iterator."""

    actual: set[str] = set()
    try:
        iterator = iter(supplied)
        for _ in range(len(expected) + 1):
            try:
                key = next(iterator)
            except StopIteration:
                break
            if type(key) is not str or key in actual:
                raise ProteinInferenceReleaseInputError(error_code)  # noqa: TRY301
            actual.add(key)
            if len(actual) > len(expected):
                raise ProteinInferenceReleaseInputError(error_code)  # noqa: TRY301
    except ProteinInferenceReleaseInputError:
        raise
    except Exception as error:
        raise ProteinInferenceReleaseInputError(error_code) from error
    if actual != expected:
        raise ProteinInferenceReleaseInputError(error_code)
    return actual


def _stage_adapter(module: StageModule) -> TypeAdapter[object]:
    adapters: dict[StageModule, TypeAdapter[object]] = {
        "GLIO-PROTEOGEN-M03-01": cast("TypeAdapter[object]", _M0301_ADAPTER),
        "GLIO-PROTEOGEN-M03-02": cast("TypeAdapter[object]", _M0302_ADAPTER),
        "GLIO-PROTEOGEN-M03-03": cast("TypeAdapter[object]", _M0303_ADAPTER),
        "GLIO-PROTEOGEN-M03-04": cast("TypeAdapter[object]", _M0304_ADAPTER),
        "GLIO-PROTEOGEN-M03-05": cast("TypeAdapter[object]", _M0305_ADAPTER),
        "GLIO-PROTEOGEN-M03-06": cast("TypeAdapter[object]", _M0306_ADAPTER),
        "GLIO-PROTEOGEN-M03-07": cast("TypeAdapter[object]", _M0307_ADAPTER),
    }
    return adapters[module]


def _parse_stage_bytes(
    module: StageModule,
    content: bytes,
) -> StageResult:
    return cast("StageResult", _stage_adapter(module).validate_json(content, strict=True))


def _validate_stage_chain(
    request: BuildProteinInferenceReleaseRequest,
    stages: Mapping[str, StageResult],
) -> None:
    m0301 = cast("ProteinInferenceProtocolConformanceResult", stages["GLIO-PROTEOGEN-M03-01"])
    m0302 = cast("ProteinInferenceIdentityLineageResolution", stages["GLIO-PROTEOGEN-M03-02"])
    m0303 = cast("ProteinInferenceRawAdmissionResult", stages["GLIO-PROTEOGEN-M03-03"])
    m0304 = cast("ProteinInferenceQualityResult", stages["GLIO-PROTEOGEN-M03-04"])
    m0305 = cast(
        "ProteinInferenceArtifactDetectionResult",
        stages["GLIO-PROTEOGEN-M03-05"],
    )
    m0306 = cast(
        "ProteinInferenceHarmonizationResult",
        stages["GLIO-PROTEOGEN-M03-06"],
    )
    m0307 = cast("ProteinInferenceSupportRouteResult", stages["GLIO-PROTEOGEN-M03-07"])
    identity = _identity_subject(m0301)
    intended_use_digests = {
        _stage_context(item).references.intended_use.evidence.digest for item in stages.values()
    }
    stage_times = tuple(item.completed_at for item in stages.values())
    if (
        m0302.protocol_result_digest != m0301.result_digest
        or m0303.request.protocol_receipt.protocol_result_digest != m0301.result_digest
        or m0303.request.lineage_receipt.lineage_result_digest != m0302.result_digest
        or m0303.request.lineage_receipt.protocol_result_digest != m0301.result_digest
        or m0304.request.raw_quality_receipt.protocol_result_digest != m0301.result_digest
        or m0304.request.raw_quality_receipt.lineage_result_digest != m0302.result_digest
        or m0304.request.raw_quality_receipt.admission_result_digest != m0303.result_digest
        or m0305.request.quality_receipt.protocol_result_digest != m0301.result_digest
        or m0305.request.quality_receipt.admission_result_digest != m0303.result_digest
        or m0305.request.quality_receipt.quality_result_digest != m0304.result_digest
        or m0306.request.artifact_receipt.quality_result_digest != m0304.result_digest
        or m0306.request.artifact_receipt.artifact_result_digest != m0305.result_digest
        or m0307.request.prerequisites.quality.result_digest != m0304.result_digest
        or m0307.request.prerequisites.harmonization.result_digest != m0306.result_digest
        or {_identity_subject(item) for item in (m0301, m0302, m0303, m0304, m0305, m0306, m0307)}
        != {identity}
        or m0307.request.context.references.identity_lineage.binding_digest != identity
        or request.context.references.identity_lineage.binding_digest != identity
        or intended_use_digests != {request.context.references.intended_use.evidence.digest}
        or request.context.references.quality.evidence.digest != m0304.result_digest
        or request.context.references.support.evidence.digest != m0307.result_digest
        or stage_times != tuple(sorted(stage_times))
        or stage_times[-1] > request.signature.issued_at
    ):
        raise ProteinInferenceReleaseInputError(
            ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH
        )


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
        raise ProteinInferenceReleaseInputError(
            ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH
        )
    return record.subject_digest


def _stage_context(result: StageResult) -> ExecutionContext:
    if isinstance(result, ProteinInferenceProtocolConformanceResult):
        return result.context
    return result.request.context


def _stage_result_digest(result: StageResult) -> str:
    return result.result_digest


def _build_manifest(
    request: BuildProteinInferenceReleaseRequest,
    stages: Mapping[str, StageResult],
) -> ProteinInferenceReproducibilityManifest:
    m0304 = cast("ProteinInferenceQualityResult", stages["GLIO-PROTEOGEN-M03-04"])
    m0306 = cast(
        "ProteinInferenceHarmonizationResult",
        stages["GLIO-PROTEOGEN-M03-06"],
    )
    m0307 = cast("ProteinInferenceSupportRouteResult", stages["GLIO-PROTEOGEN-M03-07"])
    artifacts_by_role = {item.role: item for item in request.artifacts}
    stage_records = tuple(
        _stage_record(
            module,
            stages[module],
            artifacts_by_role[_ROLE_BY_MODULE[module]].reference.digest,
        )
        for module in _STAGE_MODULES
    )
    return ProteinInferenceReproducibilityManifest(
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
        m0306_transformation_manifest_digest=(
            m0306.transformation_manifest.manifest_digest
            if m0306.transformation_manifest is not None
            else None
        ),
        m0306_analysis_digest=(
            m0306.analysis.analysis_digest if m0306.analysis is not None else None
        ),
        m0304_quality_disposition=m0304.disposition.value,
        m0305_artifact_disposition=cast(
            "ProteinInferenceArtifactDetectionResult", stages["GLIO-PROTEOGEN-M03-05"]
        ).disposition.value,
        m0306_harmonization_disposition=m0306.disposition.value,
        m0307_support_disposition=m0307.disposition.value,
        identity_resolution_digest=_identity_subject(m0306),
        intended_use_evidence_digest=request.context.references.intended_use.evidence.digest,
        support_route_result_digest=m0307.result_digest,
        policy_digest=policy_digest(request.policy),
    )


def _stage_record(
    module: StageModule,
    result: StageResult,
    byte_digest: str,
) -> ProteinInferenceStageProvenance:
    upstream: tuple[str, ...] = ()
    if isinstance(result, ProteinInferenceIdentityLineageResolution):
        upstream = (result.protocol_result_digest,)
    elif isinstance(result, ProteinInferenceRawAdmissionResult):
        upstream = tuple(
            sorted(
                (
                    result.request.protocol_receipt.protocol_result_digest,
                    result.request.lineage_receipt.lineage_result_digest,
                )
            )
        )
    elif isinstance(result, ProteinInferenceQualityResult):
        upstream = tuple(
            sorted(
                (
                    result.request.raw_quality_receipt.protocol_result_digest,
                    result.request.raw_quality_receipt.lineage_result_digest,
                    result.request.raw_quality_receipt.admission_result_digest,
                )
            )
        )
    elif isinstance(result, ProteinInferenceArtifactDetectionResult):
        upstream = (result.request.quality_receipt.quality_result_digest,)
    elif isinstance(result, ProteinInferenceHarmonizationResult):
        upstream = tuple(
            sorted(
                (
                    result.request.artifact_receipt.quality_result_digest,
                    result.request.artifact_receipt.artifact_result_digest,
                )
            )
        )
    elif isinstance(result, ProteinInferenceSupportRouteResult):
        upstream = tuple(
            sorted(
                (
                    result.request.prerequisites.quality.result_digest,
                    result.request.prerequisites.harmonization.result_digest,
                )
            )
        )
    return ProteinInferenceStageProvenance(
        module_id=ProteinInferenceStageModuleId(module),
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
    verifier: ProteinInferenceSignatureVerifier | None,
) -> ProteinInferenceSignatureVerification:
    request = prepared.request
    statement = _statement_digest(prepared)
    chain_releasable = not expected_release_quarantine_reasons(
        prepared.manifest,
        ProteinInferenceSignatureVerification(
            algorithm=request.signature.algorithm,
            key_id=request.signature.key_id,
            statement_digest=statement,
            verified=True,
            verifier_id=request.policy.allowed_verifier_ids[0],
            reason_code=ProteinInferenceSignatureVerificationReason.VERIFIED,
        ),
    )
    if not chain_releasable:
        return _verification_receipt(
            request.signature,
            statement,
            ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED,
        )
    if request.signature.claimed_statement_digest != statement:
        return _verification_receipt(
            request.signature,
            statement,
            ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in request.policy.allowed_verifier_ids:
        return _verification_receipt(
            request.signature,
            statement,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
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
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            request.signature,
            statement,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        request.signature,
        statement,
        (
            ProteinInferenceSignatureVerificationReason.VERIFIED
            if accepted
            else ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _safe_verifier_id(verifier: ProteinInferenceSignatureVerifier | None) -> str | None:
    if verifier is None:
        return None
    try:
        value = verifier.verifier_id
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return None
    return value if type(value) is str else None


def _verification_receipt(
    signature: ExternalProteinInferenceSignature,
    statement: str,
    reason: ProteinInferenceSignatureVerificationReason,
    *,
    verifier_id: str | None = None,
) -> ProteinInferenceSignatureVerification:
    return ProteinInferenceSignatureVerification(
        verifier_id=verifier_id,
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        statement_digest=statement,
        verified=reason is ProteinInferenceSignatureVerificationReason.VERIFIED,
        reason_code=reason,
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
        support_route_result_digest=prepared.manifest.support_route_result_digest,
    )


def _present_release(
    prepared: _PreparedRelease,
    verification: ProteinInferenceSignatureVerification,
) -> BuiltProteinInferenceRelease:
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
        ProteinInferenceReleaseDisposition.RELEASED
        if not reasons
        else ProteinInferenceReleaseDisposition.QUARANTINED
    )
    package_bytes: bytes | None = None
    descriptor: ProteinInferenceReleasePackageDescriptor | None = None
    if disposition is ProteinInferenceReleaseDisposition.RELEASED:
        package_bytes, descriptor = _build_package(prepared, verification)
    controls = _control_records(request.context)
    candidate = ProteinInferenceReleaseResult.model_construct(
        release_result_id=f"result.m0308.{request_hash.removeprefix('sha256:')}",
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
        infers_protein=False,
        infers_proteoform=False,
        infers_isoform=False,
        infers_glioma_specific_biology=False,
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
        human_review_required=disposition is ProteinInferenceReleaseDisposition.QUARANTINED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )
    payload = candidate.model_dump(mode="python", by_alias=True, exclude_none=False)
    payload["result_digest"] = result_payload_digest(payload)
    result = _RESULT_ADAPTER.validate_python(payload, strict=True)
    return BuiltProteinInferenceRelease(result=result, package_bytes=package_bytes)


def _build_package(
    prepared: _PreparedRelease,
    verification: ProteinInferenceSignatureVerification,
) -> tuple[bytes, ProteinInferenceReleasePackageDescriptor]:
    manifest_bytes = canonical_json_bytes(normalized_manifest(prepared.manifest))
    receipt_bytes = canonical_json_bytes(
        verification.model_dump(mode="python", by_alias=True, exclude_none=False)
    )
    members = (
        *(
            PackageMember(path=path, content=content)
            for path, content in prepared.caller_bytes.items()
        ),
        PackageMember(path=M0308_MANIFEST_PATH, content=manifest_bytes),
        PackageMember(path=M0308_SIGNATURE_RECEIPT_PATH, content=receipt_bytes),
    )
    package_bytes = build_canonical_ustar(
        members,
        fixed_mtime=prepared.request.policy.fixed_mtime,
        file_mode=prepared.request.policy.file_mode,
    )
    role_by_path = {item.path: item.role for item in prepared.request.artifacts}
    descriptor_members = tuple(
        ProteinInferenceReleaseMember(
            path=item.path,
            byte_size=len(item.content),
            digest=sha256_bytes(item.content),
            role=role_by_path.get(item.path),
        )
        for item in sorted(members, key=lambda value: value.path)
    )
    return package_bytes, ProteinInferenceReleasePackageDescriptor(
        byte_size=len(package_bytes),
        digest=sha256_bytes(package_bytes),
        members=descriptor_members,
    )


def _support(disposition: ProteinInferenceReleaseDisposition) -> SupportDecision:
    if disposition is ProteinInferenceReleaseDisposition.RELEASED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="protein_inference_release_packaged",
            rationale=M0308_RELEASED_SUPPORT_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="protein_inference_release_quarantined",
        rationale=M0308_QUARANTINED_SUPPORT_RATIONALE,
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(M0308_UNCERTAINTY_RATIONALES["measurement"]),
        sampling=_not_estimable(M0308_UNCERTAINTY_RATIONALES["sampling"]),
        parameter=_not_estimable(M0308_UNCERTAINTY_RATIONALES["parameter"]),
        model_form=_not_estimable(M0308_UNCERTAINTY_RATIONALES["model_form"]),
        identification=_not_estimable(M0308_UNCERTAINTY_RATIONALES["identification"]),
        support=_not_estimable(M0308_UNCERTAINTY_RATIONALES["support"]),
        transport=_not_estimable(M0308_UNCERTAINTY_RATIONALES["transport"]),
        sensitivity_notes=M0308_SENSITIVITY_NOTES,
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


def _provenance(  # noqa: PLR0913, PLR0917 - exact release receipt inputs.
    request: BuildProteinInferenceReleaseRequest,
    manifest: ProteinInferenceReproducibilityManifest,
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
        activity_id=f"activity.m0308.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0308_MODULE_ID,
        module_version=M0308_CONTRACT_VERSION,
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
    request: BuildProteinInferenceReleaseRequest,
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
    result: ProteinInferenceReleaseResult,
    package_bytes: bytes,
    verifier: ProteinInferenceSignatureVerifier | None,
) -> ProteinInferenceReleaseVerification:
    if type(package_bytes) is not bytes:
        raise _PackageBytesTypeError
    descriptor = result.package_descriptor
    if len(package_bytes) > M0308_MAX_PACKAGE_BYTES:
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH,
        )
    if descriptor is None or (
        len(package_bytes) != descriptor.byte_size
        or sha256_bytes(package_bytes) != descriptor.digest
    ):
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH,
        )
    try:
        _preflight_archive_inventory(package_bytes)
        inspected = inspect_canonical_ustar(package_bytes)
    except PackageAssemblyError:
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.PACKAGE_INVALID,
        )
    paths = [item.path for item in inspected]
    if len(paths) != len(set(paths)) or set(paths) != {item.path for item in descriptor.members}:
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.INVENTORY_MISMATCH,
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
            ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
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
        content_by_path[M0308_MANIFEST_PATH] != manifest_bytes
        or content_by_path[M0308_SIGNATURE_RECEIPT_PATH] != receipt_bytes
    ):
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.MANIFEST_MISMATCH,
        )
    if not _package_parent_receipt_is_bound(result, content_by_path):
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
        )
    try:
        rebuilt = build_canonical_ustar(
            inspected,
            fixed_mtime=result.policy.fixed_mtime,
            file_mode=result.policy.file_mode,
        )
    except PackageAssemblyError:
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.PACKAGE_INVALID,
        )
    if rebuilt != package_bytes:
        return _package_failure(
            result,
            ProteinInferencePackageVerificationReason.PACKAGE_NOT_CANONICAL,
        )
    verification = _verify_result_signature(result, verifier)
    reason = {
        ProteinInferenceSignatureVerificationReason.VERIFIED: (
            ProteinInferencePackageVerificationReason.VERIFIED
        ),
        ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH: (
            ProteinInferencePackageVerificationReason.STATEMENT_MISMATCH
        ),
        ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE: (
            ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
        ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED: (
            ProteinInferencePackageVerificationReason.VERIFIER_REJECTED
        ),
        ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED: (
            ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
    }[verification.reason_code]
    return ProteinInferenceReleaseVerification(
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
                    member_count > M0308_ARCHIVE_MEMBER_COUNT
                    or not info.isfile()
                    or info.size > M0308_MAX_ARTIFACT_BYTES
                    or declared_total > M0308_MAX_PACKAGE_BYTES
                ):
                    raise PackageAssemblyError.invalid_archive()
            if member_count != M0308_ARCHIVE_MEMBER_COUNT:
                raise PackageAssemblyError.invalid_archive()
    except (tarfile.TarError, OSError) as error:
        raise PackageAssemblyError.invalid_archive() from error


def _package_parent_receipt_is_bound(
    result: ProteinInferenceReleaseResult,
    content_by_path: Mapping[str, bytes],
) -> bool:
    parent_path = next(
        item.path
        for item in result.manifest.artifacts
        if item.role is ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF
    )
    try:
        parent_bytes = content_by_path[parent_path]
        strict_json_loads(parent_bytes, max_bytes=M0308_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(parent_bytes, strict=True)
        if canonical_json_bytes(receipt) != parent_bytes:
            return False
    except (KeyError, StrictJsonError, ValidationError):
        return False
    return (
        receipt.identity_resolution_digest == result.manifest.identity_resolution_digest
        and receipt.intended_use_evidence_digest == result.manifest.intended_use_evidence_digest
        and receipt.support_route_result_digest == result.manifest.support_route_result_digest
    )


def _verify_result_signature(
    result: ProteinInferenceReleaseResult,
    verifier: ProteinInferenceSignatureVerifier | None,
) -> ProteinInferenceSignatureVerification:
    signature = result.signature
    statement = result.signature_verification.statement_digest
    if signature.claimed_statement_digest != statement:
        return _verification_receipt(
            signature,
            statement,
            ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in result.policy.allowed_verifier_ids:
        return _verification_receipt(
            signature,
            statement,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    try:
        accepted = verifier.verify(statement_digest=statement, signature=signature)
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return _verification_receipt(
            signature,
            statement,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            signature,
            statement,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        signature,
        statement,
        (
            ProteinInferenceSignatureVerificationReason.VERIFIED
            if accepted
            else ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _package_failure(
    result: ProteinInferenceReleaseResult,
    reason: ProteinInferencePackageVerificationReason,
) -> ProteinInferenceReleaseVerification:
    signature = _verification_receipt(
        result.signature,
        result.signature_verification.statement_digest,
        ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED,
    )
    return ProteinInferenceReleaseVerification(
        content_verified=False,
        authenticity_verified=False,
        verified=False,
        member_count=0,
        signature_verification=signature,
        reason_code=reason,
    )


__all__ = [
    "BuiltProteinInferenceRelease",
    "M0308ProteinInferenceReleaseEngine",
    "ProteinInferenceReleaseAuthorizationError",
    "ProteinInferenceReleaseInputError",
    "ProteinInferenceReleaseInputErrorCode",
    "ProteinInferenceSignatureVerifier",
    "build_protein_inference_release",
    "build_protein_inference_release_manifest",
    "preflight_protein_inference_release_authorization",
    "verify_protein_inference_release",
]
