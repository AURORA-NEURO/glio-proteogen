"""Strict public contracts for deterministic M01-08 release packaging."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from glio_proteogen.contracts.m01_08.canonical import (
    configuration_digest,
    manifest_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0108_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-08"
M0108_CONTRACT_VERSION: Final = "1.0.0"
M0108_MAX_ARTIFACTS: Final = 1024
M0108_PACKAGE_LIMITATION_CODE: Final = "deterministic_packaging_only"
M0108_AUTHORITY_LIMITATION_CODE: Final = "external_signature_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_USTAR_NAME_BYTES: Final = 100
_USTAR_PREFIX_BYTES: Final = 155

CanonicalPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/-]+$"),
]


class ReleaseDisposition(StrEnum):
    RELEASED = "released"
    QUARANTINED = "quarantined"


class DecisionKind(StrEnum):
    QUALITY = "quality"
    SUPPORT = "support"


class DecisionState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class NumericalToleranceMode(StrEnum):
    EXACT = "exact"
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class ReleaseArtifact(FrozenModel):
    path: CanonicalPath
    role: Identifier
    source: ArtifactReference
    byte_size: int = Field(ge=0)

    @model_validator(mode="after")
    def path_is_safe_canonical_posix(self) -> ReleaseArtifact:
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or "\\" in self.path
            or ":" in self.path
            or self.path != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
            or len(path.name.encode("ascii")) > _USTAR_NAME_BYTES
            or len(str(path.parent).encode("ascii")) > _USTAR_PREFIX_BYTES
        ):
            raise ValueError("release artifact path must be canonical safe relative POSIX")
        return self


class SoftwareVersionRecord(FrozenModel):
    software_id: Identifier
    version: SemanticVersion
    digest: Sha256Digest
    evidence: ArtifactReference


class ReferenceVersionRecord(FrozenModel):
    reference_id: Identifier
    version: SemanticVersion
    digest: Sha256Digest
    evidence: ArtifactReference


class TransformationRecord(FrozenModel):
    step_id: Identifier
    ordinal: int = Field(ge=0, le=10_000)
    name: NonEmptyStr
    version: SemanticVersion
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=1024)
    output_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=1024)
    evidence: ArtifactReference


class DecisionReceipt(FrozenModel):
    kind: DecisionKind
    decision_id: Identifier
    state: DecisionState
    policy_version: SemanticVersion
    evidence: ArtifactReference


class NumericalTolerance(FrozenModel):
    tolerance_id: Identifier
    mode: NumericalToleranceMode
    value: float | None = Field(default=None, ge=0.0)
    unit: NonEmptyStr | None = None

    @model_validator(mode="after")
    def fields_match_mode(self) -> NumericalTolerance:
        if self.mode is NumericalToleranceMode.EXACT:
            if self.value is not None or self.unit is not None:
                raise ValueError("exact tolerance cannot carry a value or unit")
        elif self.value is None:
            raise ValueError("non-exact tolerance requires a finite nonnegative value")
        return self


class ExternalSignatureReceipt(FrozenModel):
    key_id: Identifier
    algorithm: Identifier
    signer_id: Identifier
    policy_id: Identifier
    policy_version: SemanticVersion
    package_digest: Sha256Digest
    manifest_digest: Sha256Digest
    evidence: ArtifactReference


class ReleasePackagingPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    max_entries: int = Field(default=1024, gt=0, le=M0108_MAX_ARTIFACTS)
    max_total_bytes: int = Field(default=64 * 1024 * 1024, gt=0, le=1024**3)
    fixed_mtime: int = Field(default=0, ge=0, le=0o77777777777)
    file_mode: int = Field(default=0o644, ge=0, le=0o777)
    allowed_signature_algorithms: tuple[Identifier, ...] = Field(min_length=1, max_length=16)


class BuildReleasePackageRequest(FrozenModel):
    operation: Literal["build_release_package"] = "build_release_package"
    contract_version: Literal["1.0.0"] = M0108_CONTRACT_VERSION
    context: ExecutionContext
    release_id: Identifier
    release_version: SemanticVersion
    artifacts: tuple[ReleaseArtifact, ...] = Field(min_length=1, max_length=M0108_MAX_ARTIFACTS)
    software_versions: tuple[SoftwareVersionRecord, ...] = Field(min_length=1, max_length=256)
    reference_versions: tuple[ReferenceVersionRecord, ...] = Field(min_length=1, max_length=256)
    transformations: tuple[TransformationRecord, ...] = Field(min_length=1, max_length=1024)
    decisions: tuple[DecisionReceipt, ...] = Field(min_length=2, max_length=2)
    numerical_tolerances: tuple[NumericalTolerance, ...] = Field(min_length=1, max_length=256)
    policy: ReleasePackagingPolicy
    signature_receipt: ExternalSignatureReceipt | None = None
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed_and_configuration_bound(self) -> BuildReleasePackageRequest:
        paths = [item.path for item in self.artifacts]
        if len(paths) != len(set(paths)) or len(paths) != len(
            {path.casefold() for path in paths}
        ):
            raise ValueError("release artifact paths must be unique")
        if len(self.artifacts) > self.policy.max_entries:
            raise ValueError("release artifact count exceeds active policy")
        if sum(item.byte_size for item in self.artifacts) > self.policy.max_total_bytes:
            raise ValueError("release artifact bytes exceed active policy")
        if {item.kind for item in self.decisions} != set(DecisionKind):
            raise ValueError("release request requires quality and support decisions")
        if len({item.tolerance_id for item in self.numerical_tolerances}) != len(
            self.numerical_tolerances
        ):
            raise ValueError("numerical tolerance identifiers must be unique")
        expected = configuration_digest(self.policy)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind release policy")
        return self


class ReleasePackageDescriptor(FrozenModel):
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    byte_size: int = Field(gt=0)
    digest: Sha256Digest
    artifact_count: int = Field(gt=0, le=M0108_MAX_ARTIFACTS)


class ReproducibilityManifest(FrozenModel):
    release_id: Identifier
    release_version: SemanticVersion
    artifacts: tuple[ReleaseArtifact, ...] = Field(min_length=1, max_length=M0108_MAX_ARTIFACTS)
    software_versions: tuple[SoftwareVersionRecord, ...] = Field(min_length=1, max_length=256)
    reference_versions: tuple[ReferenceVersionRecord, ...] = Field(min_length=1, max_length=256)
    transformations: tuple[TransformationRecord, ...] = Field(min_length=1, max_length=1024)
    decisions: tuple[DecisionReceipt, ...] = Field(min_length=2, max_length=2)
    numerical_tolerances: tuple[NumericalTolerance, ...] = Field(min_length=1, max_length=256)
    policy_digest: Sha256Digest
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    fixed_mtime: int = Field(ge=0, le=0o77777777777)
    file_mode: int = Field(ge=0, le=0o777)

    @model_validator(mode="after")
    def manifest_is_closed(self) -> ReproducibilityManifest:
        unique_fields = (
            (item.path.casefold() for item in self.artifacts),
            (item.software_id for item in self.software_versions),
            (item.reference_id for item in self.reference_versions),
            (item.step_id for item in self.transformations),
            (item.kind.value for item in self.decisions),
            (item.tolerance_id for item in self.numerical_tolerances),
        )
        for values in unique_fields:
            sequence = tuple(values)
            if len(sequence) != len(set(sequence)):
                raise ValueError("reproducibility manifest identifiers must be unique")
        if {item.kind for item in self.decisions} != set(DecisionKind):
            raise ValueError("reproducibility manifest requires quality and support decisions")
        return self


class ReleasePackagingResult(FrozenModel):
    output_type: Literal["release_packaging_result"] = "release_packaging_result"
    packaging_id: Identifier
    result_version: Literal["1.0.0"] = M0108_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: ReleaseDisposition
    package: ReleasePackageDescriptor
    manifest: ReproducibilityManifest
    manifest_digest: Sha256Digest
    signature_receipt: ExternalSignatureReceipt | None
    quarantine_reason: Identifier | None = None
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=4096)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_digest_is_bound(self) -> ReleasePackagingResult:
        if self.package.artifact_count != len(self.manifest.artifacts):
            raise ValueError("package artifact count contradicts the manifest")
        if self.manifest.policy_digest != self.policy_digest:
            raise ValueError("manifest and result policy digests must match")
        released = self.disposition is ReleaseDisposition.RELEASED
        if released and self.signature_receipt is None:
            raise ValueError("released package requires an external signature receipt")
        if released and any(
            item.state is not DecisionState.ACCEPTED for item in self.manifest.decisions
        ):
            raise ValueError("released package requires accepted upstream decisions")
        if released and self.quarantine_reason is not None:
            raise ValueError("released package cannot carry a quarantine reason")
        if not released and (self.quarantine_reason is None or not self.human_review_required):
            raise ValueError("quarantined package requires a reason and human review")
        if released and self.human_review_required:
            raise ValueError("released package cannot require human review")
        if manifest_digest(self.manifest) != self.manifest_digest:
            raise ValueError("manifest digest does not match manifest content")
        receipt = self.signature_receipt
        receipt_binds = receipt is not None and (
            receipt.package_digest == self.package.digest
            and receipt.manifest_digest == self.manifest_digest
        )
        if released and not receipt_binds:
            raise ValueError("released package requires a bound external signature receipt")
        if (
            not released
            and receipt is not None
            and not receipt_binds
            and self.quarantine_reason
            not in {"signature_receipt_mismatch", "upstream_decision_not_accepted"}
        ):
            raise ValueError("mismatched receipt requires its fixed quarantine reason")
        _validate_result_envelope(self)
        expected = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected)
        elif self.result_digest != expected:
            raise ValueError("release packaging result digest does not match its content")
        return self


def _validate_result_envelope(result: ReleasePackagingResult) -> None:
    expected_support = {
        ReleaseDisposition.RELEASED: (SupportStatus.LIMITED, "package_released", False),
        ReleaseDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "package_quarantined",
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("release packaging support envelope contradicts disposition")
    suffix = result.request_digest.removeprefix("sha256:")
    if result.packaging_id != f"packaging.m0108.{suffix}":
        raise ValueError("packaging identifier does not bind its request digest")
    provenance = result.provenance
    if (
        provenance.activity_id != f"activity.m0108.{suffix}"
        or provenance.module_id != M0108_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or provenance.configuration_digest != result.policy_digest
        or not {result.request_digest, result.policy_digest}.issubset(
            provenance.input_digests
        )
    ):
        raise ValueError("release packaging provenance envelope is inconsistent")
    states = {item.role: item.state for item in provenance.control_decisions}
    if states != {
        ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
        ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.CONSENT: ConsentState.GRANTED.value,
        ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
    }:
        raise ValueError("release packaging provenance requires accepted controls")
    if provenance.consent_state is not ConsentState.GRANTED:
        raise ValueError("release packaging provenance requires granted consent")
    consent = next(
        item for item in provenance.control_decisions if item.role is ControlRole.CONSENT
    )
    if (
        consent.decision_id != provenance.consent_decision_id
        or consent.policy_version != provenance.consent_policy_version
        or consent.evidence_digest != provenance.consent_evidence_digest
    ):
        raise ValueError("release packaging consent provenance is inconsistent")
    configuration = next(
        item
        for item in provenance.control_decisions
        if item.role is ControlRole.APPROVED_CONFIGURATION
    )
    if configuration.evidence_digest != result.policy_digest:
        raise ValueError("approved configuration must bind the release policy")
    if {item.code for item in result.limitations} != {
        M0108_PACKAGE_LIMITATION_CODE,
        M0108_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("release packaging requires both limitation codes")


class PackageVerification(FrozenModel):
    verified: bool
    package_digest: Sha256Digest
    manifest_digest: Sha256Digest
    artifact_count: int = Field(ge=0, le=M0108_MAX_ARTIFACTS)
    reason_code: Identifier | None = None


__all__ = [
    "M0108_CONTRACT_VERSION",
    "M0108_MODULE_ID",
    "BuildReleasePackageRequest",
    "DecisionKind",
    "DecisionReceipt",
    "DecisionState",
    "ExternalSignatureReceipt",
    "NumericalTolerance",
    "NumericalToleranceMode",
    "PackageVerification",
    "ReferenceVersionRecord",
    "ReleaseArtifact",
    "ReleaseDisposition",
    "ReleasePackageDescriptor",
    "ReleasePackagingPolicy",
    "ReleasePackagingResult",
    "ReproducibilityManifest",
    "SoftwareVersionRecord",
    "TransformationRecord",
]
