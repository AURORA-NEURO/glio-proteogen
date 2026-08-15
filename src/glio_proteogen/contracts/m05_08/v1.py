"""Provisional M05-08 PTM-localization provenance/release-package contracts.

This is a local scaffold only.  The dossier responsibility is authoritative, but
the field-level ABI, fixture values, and byte limits below remain provisional until
the M05-08 contract is frozen by its owning review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m05_08.canonical import manifest_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
)

M0508_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-08"
M0508_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0508_OPERATION: Final = "package_ptm_localization_release"
M0508_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-08+json"
M0508_PARENT: Final = "variant_peptide"
M0508_OWNER: Final = "ML engineering"
M0508_SAFETY_CLASS: Final = "S2"
M0508_GATE: Final = "G1"
M0508_PROVISIONAL_ABI: Final = True

# Provisional envelope copied from the M04-08 packaging shape; these values are
# intentionally not a release promise and must be frozen with the final ABI.
M0508_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0508_MAX_PACKAGE_BYTES: Final = 72 * 1024 * 1024
M0508_MAX_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
M0508_MAX_ARTIFACTS: Final = 8
M0508_MAX_STAGE_RESULTS: Final = 7
M0508_MAX_EVIDENCE: Final = 64


class PtmLocalizationReleaseArtifactRole(StrEnum):
    PARENT_VARIANT_PEPTIDE_HANDOFF = "parent_variant_peptide_handoff"
    STAGE_RESULT = "stage_result"
    SOFTWARE_BUILD = "software_build"
    REFERENCE_BUILD = "reference_build"
    REPRODUCIBILITY_EVIDENCE = "reproducibility_evidence"


class PtmLocalizationReleaseDisposition(StrEnum):
    RELEASED = "released"
    QUARANTINED = "quarantined"


class PtmLocalizationSignatureVerificationReason(StrEnum):
    VERIFIED = "verified"
    NOT_ATTEMPTED = "not_attempted"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFIER_REJECTED = "verifier_rejected"
    MANIFEST_MISMATCH = "manifest_mismatch"


class PtmLocalizationReleaseQuarantineCode(StrEnum):
    UPSTREAM_NOT_RELEASABLE = "upstream_not_releasable"
    SIGNATURE_UNVERIFIED = "signature_unverified"
    PROVENANCE_INCOMPLETE = "provenance_incomplete"


CanonicalPath = str


class PtmLocalizationReleaseArtifact(FrozenModel):
    """Caller-owned bytes referenced by the provisional release manifest."""

    path: CanonicalPath
    role: PtmLocalizationReleaseArtifactRole
    reference: ArtifactReference
    declared_size: int = Field(gt=0, le=M0508_MAX_ARTIFACT_BYTES)

    @field_validator("path")
    @classmethod
    def path_is_safe_relative_posix(cls, value: str) -> str:
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or ".." in value.split("/")
            or ":" in value
        ):
            raise ValueError("release artifact path must be a relative POSIX path")
        return value


class PtmLocalizationReleaseTransformation(FrozenModel):
    """One immutable transformation recorded in the reproducibility manifest."""

    transformation_id: Identifier
    name: NonEmptyStr
    version: SemanticVersion
    digest: Sha256Digest
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=64)
    output_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def transformations_are_closed(self) -> PtmLocalizationReleaseTransformation:
        if len(set(self.input_digests)) != len(self.input_digests):
            raise ValueError("transformation input digests must be unique")
        if len(set(self.output_digests)) != len(self.output_digests):
            raise ValueError("transformation output digests must be unique")
        if set(self.input_digests) & set(self.output_digests):
            raise ValueError("transformation cannot emit an input digest unchanged")
        return self


class PtmLocalizationReleaseQualityDecision(FrozenModel):
    """Quality decision retained as evidence instead of being recomputed here."""

    decision_id: Identifier
    status: Literal["accepted", "limited", "rejected"]
    evidence: ArtifactReference
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def rejected_quality_cannot_be_accepted(self) -> PtmLocalizationReleaseQualityDecision:
        if self.status == "rejected" and self.evidence.digest.startswith("sha256:0000"):
            raise ValueError("rejected quality decisions require non-empty evidence")
        return self


class PtmLocalizationReleasePolicy(FrozenModel):
    policy_id: Identifier
    policy_version: SemanticVersion
    allowed_signature_algorithms: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    allowed_verifier_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def policy_entries_are_unique(self) -> PtmLocalizationReleasePolicy:
        if len(set(self.allowed_signature_algorithms)) != len(self.allowed_signature_algorithms):
            raise ValueError("signature algorithms must be unique")
        if len(set(self.allowed_verifier_ids)) != len(self.allowed_verifier_ids):
            raise ValueError("verifier ids must be unique")
        return self


class PtmLocalizationReleaseManifest(FrozenModel):
    """Immutable provenance/reproducibility inventory for one candidate release."""

    manifest_id: Identifier
    release_id: Identifier
    release_version: SemanticVersion
    artifact_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0508_MAX_ARTIFACTS)
    stage_result_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=M0508_MAX_STAGE_RESULTS
    )
    software_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=64)
    reference_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=64)
    transformation_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=64)
    quality_decision_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    support_status: SupportStatus
    reproducibility_evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0508_MAX_EVIDENCE
    )
    transformations: tuple[PtmLocalizationReleaseTransformation, ...] = Field(
        default=(), max_length=64
    )
    quality_decisions: tuple[PtmLocalizationReleaseQualityDecision, ...] = Field(
        min_length=1, max_length=16
    )

    @model_validator(mode="after")
    def manifest_entries_are_unique(self) -> PtmLocalizationReleaseManifest:
        digest_groups = (
            self.artifact_digests,
            self.stage_result_digests,
            self.transformation_digests,
            self.quality_decision_ids,
        )
        if any(len(set(group)) != len(group) for group in digest_groups):
            raise ValueError("manifest entries must be unique")
        quality_ids = {item.decision_id for item in self.quality_decisions}
        if len(quality_ids) != len(self.quality_decisions):
            raise ValueError("quality decision ids must be unique")
        if set(self.quality_decision_ids) != quality_ids:
            raise ValueError("quality decision ids must match quality decision evidence")
        if set(self.transformation_digests) != {item.digest for item in self.transformations}:
            raise ValueError("transformation digests must match transformation evidence")
        return self


class PtmLocalizationReleaseSignature(FrozenModel):
    algorithm: NonEmptyStr
    key_id: Identifier
    signature_value: NonEmptyStr
    claimed_manifest_digest: Sha256Digest
    evidence: ArtifactReference

    @field_validator("signature_value")
    @classmethod
    def signature_value_is_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("signature value must not be blank")
        return value


class BuildPtmLocalizationReleaseRequest(FrozenModel):
    """Provisional request shape; upstream stage ABI is deliberately opaque."""

    context: ExecutionContext
    artifacts: tuple[PtmLocalizationReleaseArtifact, ...] = Field(
        min_length=1, max_length=M0508_MAX_ARTIFACTS
    )
    manifest: PtmLocalizationReleaseManifest
    policy: PtmLocalizationReleasePolicy
    signature: PtmLocalizationReleaseSignature
    upstream_result_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=M0508_MAX_STAGE_RESULTS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def manifest_binds_declared_upstream(self) -> BuildPtmLocalizationReleaseRequest:
        if tuple(sorted(self.upstream_result_digests)) != tuple(
            sorted(self.manifest.stage_result_digests)
        ):
            raise ValueError("upstream result digests must match the immutable manifest")
        if len({item.path for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("release artifact paths must be unique")
        artifact_digests = tuple(item.reference.digest for item in self.artifacts)
        if tuple(sorted(artifact_digests)) != tuple(sorted(self.manifest.artifact_digests)):
            raise ValueError("artifact digests must match the immutable manifest")
        if self.signature.algorithm not in self.policy.allowed_signature_algorithms:
            raise ValueError("signature algorithm is not allowed by policy")

        if self.signature.claimed_manifest_digest != manifest_digest(self.manifest):
            raise ValueError("signature manifest digest does not match the manifest")
        return self


class PtmLocalizationReleaseQuarantine(FrozenModel):
    code: PtmLocalizationReleaseQuarantineCode
    reason: NonEmptyStr
    remediation: NonEmptyStr


class PtmLocalizationReleaseResult(FrozenModel):
    output_type: Literal["ptm_localization_release_result"] = "ptm_localization_release_result"
    release_result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0508_CONTRACT_VERSION
    request_digest: Sha256Digest
    manifest_digest: Sha256Digest
    disposition: PtmLocalizationReleaseDisposition
    signature_verified: bool
    signature_reason: PtmLocalizationSignatureVerificationReason
    package_digest: Sha256Digest | None = None
    package_member_count: int = Field(default=0, ge=0, le=M0508_MAX_ARTIFACTS + 3)
    support: SupportDecision
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0508_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=8)
    quarantine_reasons: tuple[PtmLocalizationReleaseQuarantine, ...] = Field(
        default=(), max_length=8
    )
    parent_target: Literal["variant_peptide"] = M0508_PARENT
    emits_variant_peptide: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_proteogenomic_state: Literal[False] = False
    infers_proteotype: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    signs_release: Literal[False] = False
    authenticates_signer: Literal[False] = False
    human_review_required: bool
    completed_at: AwareDatetime
    result_digest: Sha256Digest

    @model_validator(mode="after")
    def disposition_is_closed(self) -> PtmLocalizationReleaseResult:
        released = self.disposition is PtmLocalizationReleaseDisposition.RELEASED
        if released != (self.signature_verified and self.package_digest is not None):
            raise ValueError("release disposition contradicts signature/package closure")
        if released == bool(self.quarantine_reasons):
            raise ValueError("quarantine reasons must match the disposition")
        if released == self.human_review_required:
            raise ValueError("human review routing must match the disposition")
        if released and self.support.status is not SupportStatus.SUPPORTED:
            raise ValueError("released package requires supported status")
        if not released and (self.signature_verified or self.package_digest is not None):
            raise ValueError("quarantined package cannot expose verified release bytes")
        if self.package_member_count == 0 and released:
            raise ValueError("released package must contain members")
        return self


class PtmLocalizationReleaseVerification(FrozenModel):
    content_verified: bool
    authenticity_verified: bool
    verified: bool
    package_digest: Sha256Digest | None = None
    reason: PtmLocalizationSignatureVerificationReason

    @model_validator(mode="after")
    def verification_is_closed(self) -> PtmLocalizationReleaseVerification:
        if self.authenticity_verified != (
            self.reason is PtmLocalizationSignatureVerificationReason.VERIFIED
        ):
            raise ValueError("authenticity must match the signature reason")
        if self.verified != (self.content_verified and self.authenticity_verified):
            raise ValueError("verified must match content and authenticity")
        return self


__all__ = [
    "M0508_ARTIFACT_ROLE_COUNT",
    "M0508_CONTRACT_VERSION",
    "M0508_GATE",
    "M0508_MAX_ARTIFACTS",
    "M0508_MAX_ARTIFACT_BYTES",
    "M0508_MAX_CANONICAL_REQUEST_BYTES",
    "M0508_MAX_EVIDENCE",
    "M0508_MAX_PACKAGE_BYTES",
    "M0508_MAX_STAGE_RESULTS",
    "M0508_MODULE_ID",
    "M0508_OPERATION",
    "M0508_OUTPUT_MEDIA_TYPE",
    "M0508_OWNER",
    "M0508_PARENT",
    "M0508_PROVISIONAL_ABI",
    "M0508_SAFETY_CLASS",
    "BuildPtmLocalizationReleaseRequest",
    "PtmLocalizationReleaseArtifact",
    "PtmLocalizationReleaseArtifactRole",
    "PtmLocalizationReleaseDisposition",
    "PtmLocalizationReleaseManifest",
    "PtmLocalizationReleasePolicy",
    "PtmLocalizationReleaseQualityDecision",
    "PtmLocalizationReleaseQuarantine",
    "PtmLocalizationReleaseQuarantineCode",
    "PtmLocalizationReleaseResult",
    "PtmLocalizationReleaseSignature",
    "PtmLocalizationReleaseTransformation",
    "PtmLocalizationReleaseVerification",
    "PtmLocalizationSignatureVerificationReason",
]


# Kept as a named marker so downstream scaffold tooling can display the pending
# ABI surface without interpreting it as a frozen count.
M0508_ARTIFACT_ROLE_COUNT: Final = len(PtmLocalizationReleaseArtifactRole)
