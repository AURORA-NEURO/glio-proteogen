"""Deterministic, quarantine-first M02-08 identification release engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, Protocol, cast

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m02_01 import ConformanceEvaluation
from glio_proteogen.contracts.m02_02 import IdentityBindingEvaluation
from glio_proteogen.contracts.m02_03 import IdentificationRawIngestionResult
from glio_proteogen.contracts.m02_04 import IdentificationQualityProfile
from glio_proteogen.contracts.m02_05 import IdentificationArtifactDetectionResult
from glio_proteogen.contracts.m02_06 import IdentificationHarmonizationResult
from glio_proteogen.contracts.m02_07 import IdentificationSupportRouteResult
from glio_proteogen.contracts.m02_08 import (
    M0208_AUTHORITY_LIMITATION_CODE,
    M0208_AUTHORITY_LIMITATION_STATEMENT,
    M0208_CONTRACT_VERSION,
    M0208_MANIFEST_PATH,
    M0208_MAX_ARTIFACT_BYTES,
    M0208_MODULE_ID,
    M0208_PACKAGE_LIMITATION_CODE,
    M0208_PACKAGE_LIMITATION_STATEMENT,
    M0208_QUARANTINED_SUPPORT_RATIONALE,
    M0208_RELEASED_SUPPORT_RATIONALE,
    M0208_SENSITIVITY_NOTES,
    M0208_SIGNATURE_RECEIPT_PATH,
    M0208_UNCERTAINTY_RATIONALES,
    BuildIdentificationQcReleaseRequest,
    ExternalIdentificationSignature,
    IdentificationPackageVerificationReason,
    IdentificationParentProteinSubtypeReceipt,
    IdentificationQcReleaseResult,
    IdentificationQcReproducibilityManifest,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
    IdentificationReleaseMember,
    IdentificationReleasePackageDescriptor,
    IdentificationReleaseVerification,
    IdentificationSignatureVerification,
    IdentificationSignatureVerificationReason,
    IdentificationStageProvenance,
    canonical_request_digest,
    context_digest,
    expected_release_quarantine_reasons,
    manifest_digest,
    normalized_manifest,
    policy_digest,
    release_evidence_index,
    release_provenance_input_digests,
    reproduction_evidence_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

StageResult = (
    ConformanceEvaluation
    | IdentityBindingEvaluation
    | IdentificationRawIngestionResult
    | IdentificationQualityProfile
    | IdentificationArtifactDetectionResult
    | IdentificationHarmonizationResult
    | IdentificationSupportRouteResult
)
StageModule = Literal[
    "GLIO-PROTEOGEN-M02-01",
    "GLIO-PROTEOGEN-M02-02",
    "GLIO-PROTEOGEN-M02-03",
    "GLIO-PROTEOGEN-M02-04",
    "GLIO-PROTEOGEN-M02-05",
    "GLIO-PROTEOGEN-M02-06",
    "GLIO-PROTEOGEN-M02-07",
]

_REQUEST_ADAPTER: Final = TypeAdapter(BuildIdentificationQcReleaseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IdentificationQcReleaseResult)
_PARENT_ADAPTER: Final = TypeAdapter(IdentificationParentProteinSubtypeReceipt)
_M0201_ADAPTER: Final = TypeAdapter(ConformanceEvaluation)
_M0202_ADAPTER: Final = TypeAdapter(IdentityBindingEvaluation)
_M0203_ADAPTER: Final = TypeAdapter(IdentificationRawIngestionResult)
_M0204_ADAPTER: Final = TypeAdapter(IdentificationQualityProfile)
_M0205_ADAPTER: Final = TypeAdapter(IdentificationArtifactDetectionResult)
_M0206_ADAPTER: Final = TypeAdapter(IdentificationHarmonizationResult)
_M0207_ADAPTER: Final = TypeAdapter(IdentificationSupportRouteResult)

_STAGE_MODULES: Final[tuple[StageModule, ...]] = (
    "GLIO-PROTEOGEN-M02-01",
    "GLIO-PROTEOGEN-M02-02",
    "GLIO-PROTEOGEN-M02-03",
    "GLIO-PROTEOGEN-M02-04",
    "GLIO-PROTEOGEN-M02-05",
    "GLIO-PROTEOGEN-M02-06",
    "GLIO-PROTEOGEN-M02-07",
)
_ROLE_BY_MODULE: Final = {
    "GLIO-PROTEOGEN-M02-01": IdentificationReleaseArtifactRole.M02_01_CONFORMANCE,
    "GLIO-PROTEOGEN-M02-02": IdentificationReleaseArtifactRole.M02_02_IDENTITY_LINEAGE,
    "GLIO-PROTEOGEN-M02-03": IdentificationReleaseArtifactRole.M02_03_RAW_INGESTION,
    "GLIO-PROTEOGEN-M02-04": IdentificationReleaseArtifactRole.M02_04_QUALITY,
    "GLIO-PROTEOGEN-M02-05": IdentificationReleaseArtifactRole.M02_05_ARTIFACT_DETECTION,
    "GLIO-PROTEOGEN-M02-06": IdentificationReleaseArtifactRole.M02_06_HARMONIZATION,
    "GLIO-PROTEOGEN-M02-07": IdentificationReleaseArtifactRole.M02_07_SUPPORT_ROUTE,
}
_LIMITATIONS: Final = (
    Limitation(
        code=M0208_PACKAGE_LIMITATION_CODE,
        statement=M0208_PACKAGE_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0208_AUTHORITY_LIMITATION_CODE,
        statement=M0208_AUTHORITY_LIMITATION_STATEMENT,
    ),
)


class IdentificationReleaseAuthorizationError(PermissionError):
    """The raw request does not authorize release-input traversal."""

    def __init__(self) -> None:
        super().__init__("M02-08 release operation is not authorized")


class IdentificationReleaseInputErrorCode(StrEnum):
    ARTIFACT_MAPPING_MISMATCH = "artifact_mapping_mismatch"
    ARTIFACT_TYPE_INVALID = "artifact_type_invalid"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_DIGEST_MISMATCH = "artifact_digest_mismatch"
    PARENT_JSON_INVALID = "parent_json_invalid"
    STAGE_MAPPING_MISMATCH = "stage_mapping_mismatch"
    STAGE_JSON_INVALID = "stage_json_invalid"
    STAGE_RESULT_MISMATCH = "stage_result_mismatch"
    CHAIN_MISMATCH = "chain_mismatch"


class IdentificationReleaseInputError(ValueError):
    """Caller bytes, stage objects, or cross-stage receipts are malformed."""

    def __init__(self, code: IdentificationReleaseInputErrorCode) -> None:
        self.code = code
        super().__init__(f"M02-08 input rejected: {code.value}")


class _BuiltReleaseInvariantError(ValueError):
    def __init__(self) -> None:
        super().__init__("released disposition and package-byte presence must agree")


class _PackageBytesTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("package bytes must be immutable bytes")


class IdentificationSignatureVerifier(Protocol):
    """Narrow injected authenticity boundary; M02-08 owns the typed receipt."""

    @property
    def verifier_id(self) -> str: ...

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalIdentificationSignature,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BuiltIdentificationRelease:
    """Typed release outcome plus bytes only when the release is approved."""

    result: IdentificationQcReleaseResult
    package_bytes: bytes | None

    def __post_init__(self) -> None:
        released = self.result.disposition is IdentificationReleaseDisposition.RELEASED
        if released != (self.package_bytes is not None):
            raise _BuiltReleaseInvariantError


@dataclass(frozen=True, slots=True)
class _PreparedRelease:
    request: BuildIdentificationQcReleaseRequest
    caller_bytes: dict[str, bytes]
    stages: dict[str, StageResult]
    manifest: IdentificationQcReproducibilityManifest


class M0208IdentificationReleaseEngine:
    """Build or inspect one immutable identification-QC release without persistence."""

    __slots__ = ("_verifier",)

    def __init__(self, verifier: IdentificationSignatureVerifier | None = None) -> None:
        self._verifier = verifier

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltIdentificationRelease:
        prepared = _prepare_release(request, artifacts_by_path, stage_results_by_module)
        verification = _signature_verification(prepared, self._verifier)
        return _present_release(prepared, verification)

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> IdentificationQcReproducibilityManifest:
        return _prepare_release(request, artifacts_by_path, stage_results_by_module).manifest

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> IdentificationReleaseVerification:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return _verify_package(validated, package_bytes, self._verifier)


def build_identification_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
    verifier: IdentificationSignatureVerifier | None = None,
) -> BuiltIdentificationRelease:
    """Build a release or typed quarantine; quarantine always returns no bytes."""

    return M0208IdentificationReleaseEngine(verifier).build(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def build_identification_release_manifest(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> IdentificationQcReproducibilityManifest:
    """Prepare the deterministic unsigned manifest for external statement signing."""

    return M0208IdentificationReleaseEngine().build_manifest(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def verify_identification_release(
    result: object,
    package_bytes: bytes,
    verifier: IdentificationSignatureVerifier | None = None,
) -> IdentificationReleaseVerification:
    """Verify package content first, then authenticity through the injected boundary."""

    return M0208IdentificationReleaseEngine(verifier).verify(result, package_bytes)


def preflight_identification_release_authorization(candidate: object) -> None:
    """Reject denied raw requests before artifact or stage mappings are traversed."""

    if isinstance(candidate, BuildIdentificationQcReleaseRequest):
        context: object = candidate.context
    elif isinstance(candidate, Mapping):
        context = candidate.get("context")
    else:
        raise IdentificationReleaseAuthorizationError
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
        raise IdentificationReleaseAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _prepare_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> _PreparedRelease:
    preflight_identification_release_authorization(request)
    validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
    caller_bytes = _validate_caller_bytes(validated, artifacts_by_path)
    stages = _validate_stage_results(validated, caller_bytes, stage_results_by_module)
    _validate_stage_chain(stages)
    _validate_parent_receipt(validated, caller_bytes, stages)
    return _PreparedRelease(
        request=validated,
        caller_bytes=caller_bytes,
        stages=stages,
        manifest=_build_manifest(validated, stages),
    )


def _validate_caller_bytes(
    request: BuildIdentificationQcReleaseRequest,
    supplied: Mapping[str, object],
) -> dict[str, bytes]:
    expected_paths = {item.path for item in request.artifacts}
    try:
        actual_paths = set(supplied.keys())
    except Exception as error:
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        ) from error
    if actual_paths != expected_paths:
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        )
    result: dict[str, bytes] = {}
    for artifact in sorted(request.artifacts, key=lambda item: item.path):
        try:
            content = supplied[artifact.path]
        except Exception as error:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
            ) from error
        if not isinstance(content, bytes):
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.ARTIFACT_TYPE_INVALID
            )
        if len(content) != artifact.declared_size:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH
            )
        if sha256_bytes(content) != artifact.reference.digest:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH
            )
        result[artifact.path] = content
    return result


def _validate_parent_receipt(
    request: BuildIdentificationQcReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    stages: Mapping[str, StageResult],
) -> None:
    parent = next(
        item
        for item in request.artifacts
        if item.role is IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE
    )
    content = caller_bytes[parent.path]
    try:
        strict_json_loads(content, max_bytes=M0208_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(content, strict=True)
    except (StrictJsonError, ValidationError) as error:
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.PARENT_JSON_INVALID
        ) from error
    identity = cast("IdentityBindingEvaluation", stages["GLIO-PROTEOGEN-M02-02"])
    if (
        receipt.subject_binding_digest != identity.result_digest
        or receipt.intended_use_evidence_digest
        != request.context.references.intended_use.evidence.digest
    ):
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.CHAIN_MISMATCH
        )


def _validate_stage_results(
    request: BuildIdentificationQcReleaseRequest,
    caller_bytes: Mapping[str, bytes],
    supplied: Mapping[str, object],
) -> dict[str, StageResult]:
    try:
        modules = set(supplied.keys())
    except Exception as error:
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
        ) from error
    if modules != set(_STAGE_MODULES):
        raise IdentificationReleaseInputError(
            IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
        )
    artifact_by_role = {item.role: item for item in request.artifacts}
    results: dict[str, StageResult] = {}
    for module in _STAGE_MODULES:
        artifact = artifact_by_role[_ROLE_BY_MODULE[module]]
        try:
            supplied_result = supplied[module]
        except Exception as error:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
            ) from error
        try:
            content = caller_bytes[artifact.path]
            strict_json_loads(
                content,
                max_bytes=M0208_MAX_ARTIFACT_BYTES,
            )
            parsed, validated = _parse_stage(module, content, supplied_result)
        except Exception as error:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.STAGE_JSON_INVALID
            ) from error
        if parsed != validated:
            raise IdentificationReleaseInputError(
                IdentificationReleaseInputErrorCode.STAGE_RESULT_MISMATCH
            )
        results[module] = parsed
    return results


def _parse_stage(
    module: StageModule,
    content: bytes,
    supplied: object,
) -> tuple[StageResult, StageResult]:
    adapters: dict[StageModule, TypeAdapter[object]] = {
        "GLIO-PROTEOGEN-M02-01": cast("TypeAdapter[object]", _M0201_ADAPTER),
        "GLIO-PROTEOGEN-M02-02": cast("TypeAdapter[object]", _M0202_ADAPTER),
        "GLIO-PROTEOGEN-M02-03": cast("TypeAdapter[object]", _M0203_ADAPTER),
        "GLIO-PROTEOGEN-M02-04": cast("TypeAdapter[object]", _M0204_ADAPTER),
        "GLIO-PROTEOGEN-M02-05": cast("TypeAdapter[object]", _M0205_ADAPTER),
        "GLIO-PROTEOGEN-M02-06": cast("TypeAdapter[object]", _M0206_ADAPTER),
        "GLIO-PROTEOGEN-M02-07": cast("TypeAdapter[object]", _M0207_ADAPTER),
    }
    adapter = adapters[module]
    return (
        cast("StageResult", adapter.validate_json(content, strict=True)),
        cast("StageResult", adapter.validate_python(supplied, strict=True)),
    )


def _validate_stage_chain(stages: Mapping[str, StageResult]) -> None:
    m0201 = cast("ConformanceEvaluation", stages["GLIO-PROTEOGEN-M02-01"])
    m0202 = cast("IdentityBindingEvaluation", stages["GLIO-PROTEOGEN-M02-02"])
    m0203 = cast("IdentificationRawIngestionResult", stages["GLIO-PROTEOGEN-M02-03"])
    m0204 = cast("IdentificationQualityProfile", stages["GLIO-PROTEOGEN-M02-04"])
    m0205 = cast(
        "IdentificationArtifactDetectionResult",
        stages["GLIO-PROTEOGEN-M02-05"],
    )
    m0206 = cast(
        "IdentificationHarmonizationResult",
        stages["GLIO-PROTEOGEN-M02-06"],
    )
    m0207 = cast("IdentificationSupportRouteResult", stages["GLIO-PROTEOGEN-M02-07"])
    expected_receipts = {
        "GLIO-PROTEOGEN-M02-01": m0201.evaluation_digest,
        "GLIO-PROTEOGEN-M02-02": m0202.result_digest,
        "GLIO-PROTEOGEN-M02-03": m0203.result_digest,
        "GLIO-PROTEOGEN-M02-04": m0204.result_digest,
        "GLIO-PROTEOGEN-M02-05": m0205.result_digest,
    }
    actual_receipts = {item.module_id: item.result_digest for item in m0206.upstream_receipts}
    m0202_subject = m0202.result_digest
    m0204_subject = _identity_subject(m0204)
    m0206_subject = _identity_subject(m0206)
    m0207_subject = _identity_subject(m0207)
    if (
        actual_receipts != expected_receipts
        or m0207.prerequisites.quality.result_digest != m0204.result_digest
        or m0207.prerequisites.harmonization.result_digest != m0206.result_digest
        or m0207.prerequisites.harmonization.m0204_result_digest != m0204.result_digest
        or m0207.prerequisites.quality.identity_subject_digest != m0204_subject
        or m0207.prerequisites.harmonization.identity_subject_digest != m0206_subject
        or {m0202_subject, m0204_subject, m0206_subject, m0207_subject} != {m0202_subject}
        or m0207.context.references.identity_lineage.binding_digest != m0202_subject
    ):
        raise IdentificationReleaseInputError(IdentificationReleaseInputErrorCode.CHAIN_MISMATCH)


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
        raise IdentificationReleaseInputError(IdentificationReleaseInputErrorCode.CHAIN_MISMATCH)
    return record.subject_digest


def _stage_result_digest(result: StageResult) -> str:
    if isinstance(result, ConformanceEvaluation):
        return result.evaluation_digest
    return result.result_digest


def _build_manifest(
    request: BuildIdentificationQcReleaseRequest,
    stages: Mapping[str, StageResult],
) -> IdentificationQcReproducibilityManifest:
    m0204 = cast("IdentificationQualityProfile", stages["GLIO-PROTEOGEN-M02-04"])
    m0206 = cast(
        "IdentificationHarmonizationResult",
        stages["GLIO-PROTEOGEN-M02-06"],
    )
    m0207 = cast("IdentificationSupportRouteResult", stages["GLIO-PROTEOGEN-M02-07"])
    artifacts_by_role = {item.role: item for item in request.artifacts}
    stage_records = tuple(
        _stage_record(
            module,
            stages[module],
            artifacts_by_role[_ROLE_BY_MODULE[module]].reference.digest,
        )
        for module in _STAGE_MODULES
    )
    return IdentificationQcReproducibilityManifest(
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
        m0206_transformation_manifest_digest=sha256_digest(
            m0206.transformation_manifest.model_dump(
                mode="python",
                by_alias=True,
                exclude_none=False,
            )
        ),
        m0204_quality_disposition=m0204.disposition.value,
        m0207_support_disposition=m0207.disposition.value,
        subject_binding_digest=_identity_subject(m0206),
        intended_use_evidence_digest=request.context.references.intended_use.evidence.digest,
        policy_digest=policy_digest(request.policy),
    )


def _stage_record(
    module: StageModule,
    result: StageResult,
    byte_digest: str,
) -> IdentificationStageProvenance:
    upstream: tuple[str, ...] = ()
    analysis_lineage = result.request_digest
    if isinstance(result, IdentificationHarmonizationResult):
        upstream = tuple(sorted(item.result_digest for item in result.upstream_receipts))
        analysis_lineage = result.prerequisites_digest
    elif isinstance(result, IdentificationSupportRouteResult):
        upstream = tuple(
            sorted(
                (
                    result.prerequisites.quality.result_digest,
                    result.prerequisites.harmonization.result_digest,
                )
            )
        )
        analysis_lineage = result.prerequisites.harmonization.result_digest
    return IdentificationStageProvenance(
        module_id=module,
        module_version=result.result_version,
        result_digest=_stage_result_digest(result),
        byte_digest=byte_digest,
        disposition=result.disposition.value,
        generated_at=result.completed_at,
        configuration_digest=result.configuration_digest,
        identity_subject_digest=_identity_subject(result),
        analysis_lineage_digest=analysis_lineage,
        bound_upstream_result_digests=upstream,
        human_review_required=result.human_review_required,
    )


def _signature_verification(
    prepared: _PreparedRelease,
    verifier: IdentificationSignatureVerifier | None,
) -> IdentificationSignatureVerification:
    request = prepared.request
    statement = _statement_digest(prepared)
    chain_releasable = not expected_release_quarantine_reasons(
        prepared.manifest,
        IdentificationSignatureVerification(
            algorithm=request.signature.algorithm,
            key_id=request.signature.key_id,
            statement_digest=statement,
            verified=True,
            verifier_id=request.policy.allowed_verifier_ids[0],
            reason_code=IdentificationSignatureVerificationReason.VERIFIED,
        ),
    )
    if not chain_releasable:
        return _verification_receipt(
            request.signature,
            statement,
            IdentificationSignatureVerificationReason.NOT_ATTEMPTED,
        )
    if request.signature.claimed_statement_digest != statement:
        return _verification_receipt(
            request.signature,
            statement,
            IdentificationSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in request.policy.allowed_verifier_ids:
        return _verification_receipt(
            request.signature,
            statement,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
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
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            request.signature,
            statement,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        request.signature,
        statement,
        (
            IdentificationSignatureVerificationReason.VERIFIED
            if accepted
            else IdentificationSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _safe_verifier_id(verifier: IdentificationSignatureVerifier | None) -> str | None:
    if verifier is None:
        return None
    try:
        value = verifier.verifier_id
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return None
    return value if isinstance(value, str) else None


def _verification_receipt(
    signature: ExternalIdentificationSignature,
    statement: str,
    reason: IdentificationSignatureVerificationReason,
    *,
    verifier_id: str | None = None,
) -> IdentificationSignatureVerification:
    return IdentificationSignatureVerification(
        verifier_id=verifier_id,
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        statement_digest=statement,
        verified=reason is IdentificationSignatureVerificationReason.VERIFIED,
        reason_code=reason,
    )


def _statement_digest(prepared: _PreparedRelease) -> str:
    request = prepared.request
    return signing_statement_digest(
        active_manifest_digest=manifest_digest(prepared.manifest),
        active_policy_digest=policy_digest(request.policy),
        release_id=request.release_id,
        release_version=request.release_version,
        subject_binding_digest=prepared.manifest.subject_binding_digest,
        intended_use_evidence_digest=prepared.manifest.intended_use_evidence_digest,
    )


def _present_release(
    prepared: _PreparedRelease,
    verification: IdentificationSignatureVerification,
) -> BuiltIdentificationRelease:
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
        IdentificationReleaseDisposition.RELEASED
        if not reasons
        else IdentificationReleaseDisposition.QUARANTINED
    )
    package_bytes: bytes | None = None
    descriptor: IdentificationReleasePackageDescriptor | None = None
    if disposition is IdentificationReleaseDisposition.RELEASED:
        package_bytes, descriptor = _build_package(prepared, verification)
    controls = _control_records(request.context)
    result = IdentificationQcReleaseResult(
        release_result_id=f"release.m0208.{request_hash.removeprefix('sha256:')}",
        request_digest=request_hash,
        context_digest=context_hash,
        context=request.context,
        policy_digest=active_policy_hash,
        policy=presented_policy,
        manifest_digest=active_manifest_hash,
        manifest=prepared.manifest,
        signature=request.signature,
        signature_verification=verification,
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
        human_review_required=disposition is IdentificationReleaseDisposition.QUARANTINED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )
    return BuiltIdentificationRelease(result=result, package_bytes=package_bytes)


def _build_package(
    prepared: _PreparedRelease,
    verification: IdentificationSignatureVerification,
) -> tuple[bytes, IdentificationReleasePackageDescriptor]:
    manifest_bytes = canonical_json_bytes(normalized_manifest(prepared.manifest))
    receipt_bytes = canonical_json_bytes(
        verification.model_dump(mode="python", by_alias=True, exclude_none=False)
    )
    members = (
        *(
            PackageMember(path=path, content=content)
            for path, content in prepared.caller_bytes.items()
        ),
        PackageMember(path=M0208_MANIFEST_PATH, content=manifest_bytes),
        PackageMember(path=M0208_SIGNATURE_RECEIPT_PATH, content=receipt_bytes),
    )
    package_bytes = build_canonical_ustar(
        members,
        fixed_mtime=prepared.request.policy.fixed_mtime,
        file_mode=prepared.request.policy.file_mode,
    )
    role_by_path = {item.path: item.role for item in prepared.request.artifacts}
    descriptor_members = tuple(
        IdentificationReleaseMember(
            path=item.path,
            byte_size=len(item.content),
            digest=sha256_bytes(item.content),
            role=role_by_path.get(item.path),
        )
        for item in sorted(members, key=lambda value: value.path)
    )
    return package_bytes, IdentificationReleasePackageDescriptor(
        byte_size=len(package_bytes),
        digest=sha256_bytes(package_bytes),
        members=descriptor_members,
    )


def _support(disposition: IdentificationReleaseDisposition) -> SupportDecision:
    if disposition is IdentificationReleaseDisposition.RELEASED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="identification_release_packaged",
            rationale=M0208_RELEASED_SUPPORT_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="identification_release_quarantined",
        rationale=M0208_QUARANTINED_SUPPORT_RATIONALE,
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(M0208_UNCERTAINTY_RATIONALES["measurement"]),
        sampling=_not_estimable(M0208_UNCERTAINTY_RATIONALES["sampling"]),
        parameter=_not_estimable(M0208_UNCERTAINTY_RATIONALES["parameter"]),
        model_form=_not_estimable(M0208_UNCERTAINTY_RATIONALES["model_form"]),
        identification=_not_estimable(M0208_UNCERTAINTY_RATIONALES["identification"]),
        support=_not_estimable(M0208_UNCERTAINTY_RATIONALES["support"]),
        transport=_not_estimable(M0208_UNCERTAINTY_RATIONALES["transport"]),
        sensitivity_notes=M0208_SENSITIVITY_NOTES,
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
    request: BuildIdentificationQcReleaseRequest,
    manifest: IdentificationQcReproducibilityManifest,
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
        activity_id=f"activity.m0208.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0208_MODULE_ID,
        module_version=M0208_CONTRACT_VERSION,
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
    request: BuildIdentificationQcReleaseRequest,
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


def _verify_package(  # noqa: PLR0911 - ordered typed verification precedence.
    result: IdentificationQcReleaseResult,
    package_bytes: bytes,
    verifier: IdentificationSignatureVerifier | None,
) -> IdentificationReleaseVerification:
    if not isinstance(package_bytes, bytes):
        raise _PackageBytesTypeError
    descriptor = result.package_descriptor
    if descriptor is None or (
        len(package_bytes) != descriptor.byte_size
        or sha256_bytes(package_bytes) != descriptor.digest
    ):
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.DESCRIPTOR_MISMATCH,
        )
    try:
        inspected = inspect_canonical_ustar(package_bytes)
    except PackageAssemblyError:
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.PACKAGE_INVALID,
        )
    paths = [item.path for item in inspected]
    if len(paths) != len(set(paths)) or set(paths) != {item.path for item in descriptor.members}:
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.INVENTORY_MISMATCH,
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
            IdentificationPackageVerificationReason.CONTENT_MISMATCH,
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
        content_by_path[M0208_MANIFEST_PATH] != manifest_bytes
        or content_by_path[M0208_SIGNATURE_RECEIPT_PATH] != receipt_bytes
    ):
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.MANIFEST_MISMATCH,
        )
    if not _package_parent_receipt_is_bound(result, content_by_path):
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.CONTENT_MISMATCH,
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
            IdentificationPackageVerificationReason.PACKAGE_INVALID,
        )
    if rebuilt != package_bytes:
        return _package_failure(
            result,
            IdentificationPackageVerificationReason.PACKAGE_NOT_CANONICAL,
        )
    verification = _verify_result_signature(result, verifier)
    reason = {
        IdentificationSignatureVerificationReason.VERIFIED: (
            IdentificationPackageVerificationReason.VERIFIED
        ),
        IdentificationSignatureVerificationReason.STATEMENT_MISMATCH: (
            IdentificationPackageVerificationReason.STATEMENT_MISMATCH
        ),
        IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE: (
            IdentificationPackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
        IdentificationSignatureVerificationReason.VERIFIER_REJECTED: (
            IdentificationPackageVerificationReason.VERIFIER_REJECTED
        ),
        IdentificationSignatureVerificationReason.NOT_ATTEMPTED: (
            IdentificationPackageVerificationReason.VERIFIER_UNAVAILABLE
        ),
    }[verification.reason_code]
    return IdentificationReleaseVerification(
        content_verified=True,
        authenticity_verified=verification.verified,
        verified=verification.verified,
        package_digest=descriptor.digest,
        manifest_digest=result.manifest_digest,
        member_count=len(inspected),
        signature_verification=verification,
        reason_code=reason,
    )


def _package_parent_receipt_is_bound(
    result: IdentificationQcReleaseResult,
    content_by_path: Mapping[str, bytes],
) -> bool:
    parent_path = next(
        item.path
        for item in result.manifest.artifacts
        if item.role is IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE
    )
    try:
        parent_bytes = content_by_path[parent_path]
        strict_json_loads(parent_bytes, max_bytes=M0208_MAX_ARTIFACT_BYTES)
        receipt = _PARENT_ADAPTER.validate_json(parent_bytes, strict=True)
    except (KeyError, StrictJsonError, ValidationError):
        return False
    return (
        receipt.subject_binding_digest == result.manifest.subject_binding_digest
        and receipt.intended_use_evidence_digest
        == result.manifest.intended_use_evidence_digest
    )


def _verify_result_signature(
    result: IdentificationQcReleaseResult,
    verifier: IdentificationSignatureVerifier | None,
) -> IdentificationSignatureVerification:
    signature = result.signature
    statement = result.signature_verification.statement_digest
    if signature.claimed_statement_digest != statement:
        return _verification_receipt(
            signature,
            statement,
            IdentificationSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in result.policy.allowed_verifier_ids:
        return _verification_receipt(
            signature,
            statement,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    try:
        accepted = verifier.verify(statement_digest=statement, signature=signature)
    except Exception:  # noqa: BLE001 - fail closed across an injected external verifier.
        return _verification_receipt(
            signature,
            statement,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            signature,
            statement,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        signature,
        statement,
        (
            IdentificationSignatureVerificationReason.VERIFIED
            if accepted
            else IdentificationSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


def _package_failure(
    result: IdentificationQcReleaseResult,
    reason: IdentificationPackageVerificationReason,
) -> IdentificationReleaseVerification:
    signature = _verification_receipt(
        result.signature,
        result.signature_verification.statement_digest,
        IdentificationSignatureVerificationReason.NOT_ATTEMPTED,
    )
    return IdentificationReleaseVerification(
        content_verified=False,
        authenticity_verified=False,
        verified=False,
        member_count=0,
        signature_verification=signature,
        reason_code=reason,
    )


__all__ = [
    "BuiltIdentificationRelease",
    "IdentificationReleaseAuthorizationError",
    "IdentificationReleaseInputError",
    "IdentificationReleaseInputErrorCode",
    "IdentificationSignatureVerifier",
    "M0208IdentificationReleaseEngine",
    "build_identification_release",
    "build_identification_release_manifest",
    "preflight_identification_release_authorization",
    "verify_identification_release",
]
