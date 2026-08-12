"""Strict M02-08 contracts for one deterministic identification-QC release."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from glio_proteogen.contracts.m02_08.canonical import (
    canonical_request_digest,
    context_digest,
    manifest_digest,
    normalized_manifest,
    normalized_request,
    policy_digest,
    reproduction_evidence_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.canonical_ustar import sha256_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    EstimateState,
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

M0208_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-08"
M0208_CONTRACT_VERSION: Final = "1.0.0"
M0208_CALLER_ARTIFACT_COUNT: Final = 8
M0208_STAGE_COUNT: Final = 7
M0208_ARCHIVE_MEMBER_COUNT: Final = 10
M0208_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0208_MAX_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
M0208_MAX_TOTAL_ARTIFACT_BYTES: Final = 64 * 1024 * 1024
M0208_MANIFEST_PATH: Final = "META-INF/glio-proteogen-m02-08/reproducibility-manifest.json"
M0208_SIGNATURE_RECEIPT_PATH: Final = "META-INF/glio-proteogen-m02-08/signature-verification.json"
M0208_PACKAGE_LIMITATION_CODE: Final = "deterministic_identification_packaging_only"
M0208_AUTHORITY_LIMITATION_CODE: Final = "external_signature_authority_unverified"
M0208_PACKAGE_LIMITATION_STATEMENT: Final = (
    "M02-08 packages one closed identification-QC chain without changing or interpreting "
    "its scientific content."
)
M0208_AUTHORITY_LIMITATION_STATEMENT: Final = (
    "Signature verification records one injected verifier outcome and does not establish "
    "signer identity, key custody, certificate validity, or release authority."
)
M0208_RELEASED_SUPPORT_RATIONALE: Final = (
    "The authorized identification-QC chain and injected signature verification satisfied "
    "the pinned deterministic release profile."
)
M0208_QUARANTINED_SUPPORT_RATIONALE: Final = (
    "The identification-QC release was withheld because an upstream stage or signature "
    "verification did not satisfy the pinned release profile."
)
M0208_SENSITIVITY_NOTES: Final = (
    "No calibrated probability is produced by deterministic release packaging.",
    "Scientific, cryptographic, and release-authority validity remain external.",
)
M0208_UNCERTAINTY_RATIONALES: Final[dict[str, str]] = {
    "measurement": "Measurement uncertainty is preserved in packaged upstream results.",
    "sampling": "Sampling uncertainty is preserved in packaged upstream results.",
    "parameter": "Packaging has no estimated scientific parameter uncertainty.",
    "model_form": "M02-08 performs no scientific model inference.",
    "identification": "Identification uncertainty is preserved in packaged upstream results.",
    "support": "Support uncertainty is preserved in the packaged M02-07 result.",
    "transport": "External verifier, evidence, and authority issuers are not authenticated.",
}

_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_USTAR_NAME_BYTES: Final = 100
_USTAR_PREFIX_BYTES: Final = 155
_USTAR_PATH_BYTES: Final = 255
StageModuleId = Literal[
    "GLIO-PROTEOGEN-M02-01",
    "GLIO-PROTEOGEN-M02-02",
    "GLIO-PROTEOGEN-M02-03",
    "GLIO-PROTEOGEN-M02-04",
    "GLIO-PROTEOGEN-M02-05",
    "GLIO-PROTEOGEN-M02-06",
    "GLIO-PROTEOGEN-M02-07",
]
_EXPECTED_STAGE_MODULES: Final[tuple[StageModuleId, ...]] = (
    "GLIO-PROTEOGEN-M02-01",
    "GLIO-PROTEOGEN-M02-02",
    "GLIO-PROTEOGEN-M02-03",
    "GLIO-PROTEOGEN-M02-04",
    "GLIO-PROTEOGEN-M02-05",
    "GLIO-PROTEOGEN-M02-06",
    "GLIO-PROTEOGEN-M02-07",
)

CanonicalPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/-]+$"),
]
SignatureValue = Annotated[
    str,
    StringConstraints(min_length=1, max_length=16_384, pattern=r"^[A-Za-z0-9+/=_-]+$"),
]


class IdentificationReleaseArtifactRole(StrEnum):
    PARENT_PROTEIN_SUBTYPE = "parent_protein_subtype"
    M02_01_CONFORMANCE = "m02_01_conformance"
    M02_02_IDENTITY_LINEAGE = "m02_02_identity_lineage"
    M02_03_RAW_INGESTION = "m02_03_raw_ingestion"
    M02_04_QUALITY = "m02_04_quality"
    M02_05_ARTIFACT_DETECTION = "m02_05_artifact_detection"
    M02_06_HARMONIZATION = "m02_06_harmonization"
    M02_07_SUPPORT_ROUTE = "m02_07_support_route"


class IdentificationReleaseDisposition(StrEnum):
    RELEASED = "released"
    QUARANTINED = "quarantined"


class IdentificationSignatureVerificationReason(StrEnum):
    VERIFIED = "verified"
    NOT_ATTEMPTED = "not_attempted"
    STATEMENT_MISMATCH = "statement_mismatch"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFIER_REJECTED = "verifier_rejected"


class IdentificationReleaseQuarantineCode(StrEnum):
    UPSTREAM_NOT_RELEASABLE = "upstream_not_releasable"
    SIGNATURE_UNVERIFIED = "signature_unverified"


class IdentificationPackageVerificationReason(StrEnum):
    VERIFIED = "verified"
    DESCRIPTOR_MISMATCH = "descriptor_mismatch"
    PACKAGE_INVALID = "package_invalid"
    INVENTORY_MISMATCH = "inventory_mismatch"
    CONTENT_MISMATCH = "content_mismatch"
    PACKAGE_NOT_CANONICAL = "package_not_canonical"
    MANIFEST_MISMATCH = "manifest_mismatch"
    STATEMENT_MISMATCH = "statement_mismatch"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFIER_REJECTED = "verifier_rejected"


class IdentificationReleaseArtifact(FrozenModel):
    path: CanonicalPath
    role: IdentificationReleaseArtifactRole
    reference: ArtifactReference
    declared_size: int = Field(gt=0, le=M0208_MAX_ARTIFACT_BYTES)

    @model_validator(mode="after")
    def path_is_safe_ustar_member(self) -> IdentificationReleaseArtifact:
        _validate_member_path(self.path)
        if self.path.casefold().startswith("meta-inf/glio-proteogen-m02-08/"):
            raise ValueError("caller artifact cannot use the reserved M02-08 namespace")
        return self


class IdentificationParentProteinSubtypeReceipt(FrozenModel):
    """Minimal caller-owned parent receipt; M02-08 makes no subtype inference."""

    parent_target: Literal["protein_subtype"] = "protein_subtype"
    subject_binding_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest


class IdentificationSoftwareVersion(FrozenModel):
    software_id: Identifier
    version: SemanticVersion
    build_digest: Sha256Digest
    evidence: ArtifactReference


class IdentificationReferenceVersion(FrozenModel):
    reference_id: Identifier
    build_id: Identifier
    version: NonEmptyStr
    digest: Sha256Digest
    evidence: ArtifactReference


class IdentificationReproductionEvidence(FrozenModel):
    environment_lock: ArtifactReference
    build_recipe: ArtifactReference
    locked_tests: ArtifactReference
    benchmark: ArtifactReference
    traceability: ArtifactReference
    reviewer_signoff: ArtifactReference
    rollback: ArtifactReference

    @model_validator(mode="after")
    def seven_evidence_items_are_distinct(self) -> IdentificationReproductionEvidence:
        references = _reproduction_references(self)
        if len({item.digest for item in references}) != len(references):
            raise ValueError("reproduction evidence digests must be unique")
        return self


class IdentificationReleasePolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    max_total_bytes: int = Field(
        default=M0208_MAX_TOTAL_ARTIFACT_BYTES,
        gt=0,
        le=M0208_MAX_TOTAL_ARTIFACT_BYTES,
    )
    max_artifact_bytes: int = Field(
        default=M0208_MAX_ARTIFACT_BYTES,
        gt=0,
        le=M0208_MAX_ARTIFACT_BYTES,
    )
    fixed_mtime: Literal[0] = 0
    file_mode: Literal[420] = 0o644
    allowed_signature_algorithms: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    allowed_verifier_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def policy_sets_are_unique(self) -> IdentificationReleasePolicy:
        for values in (self.allowed_signature_algorithms, self.allowed_verifier_ids):
            if len(set(values)) != len(values):
                raise ValueError("release policy allowlists must be unique")
        return self


class ExternalIdentificationSignature(FrozenModel):
    signer_id: Identifier
    key_id: Identifier
    algorithm: Identifier
    claimed_statement_digest: Sha256Digest
    signature_value: SignatureValue
    issued_at: AwareDatetime
    evidence: ArtifactReference


class BuildIdentificationQcReleaseRequest(FrozenModel):
    operation: Literal["package_identification_release"] = "package_identification_release"
    contract_version: Literal["1.0.0"] = M0208_CONTRACT_VERSION
    context: ExecutionContext
    release_id: Identifier
    release_version: SemanticVersion
    artifacts: tuple[IdentificationReleaseArtifact, ...] = Field(
        min_length=M0208_CALLER_ARTIFACT_COUNT,
        max_length=M0208_CALLER_ARTIFACT_COUNT,
    )
    software_versions: tuple[IdentificationSoftwareVersion, ...] = Field(
        min_length=1,
        max_length=64,
    )
    reference_versions: tuple[IdentificationReferenceVersion, ...] = Field(
        min_length=1,
        max_length=64,
    )
    reproduction_evidence: IdentificationReproductionEvidence
    policy: IdentificationReleasePolicy
    signature: ExternalIdentificationSignature
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_bounded(self) -> BuildIdentificationQcReleaseRequest:
        _require_authorized_context(self.context)
        roles = [item.role for item in self.artifacts]
        paths = [item.path for item in self.artifacts]
        if len(set(roles)) != len(IdentificationReleaseArtifactRole) or set(roles) != set(
            IdentificationReleaseArtifactRole
        ):
            raise ValueError("release request requires each caller artifact role exactly once")
        if len(set(paths)) != len(paths) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("release artifact paths must be unique and alias-free")
        if any(item.declared_size > self.policy.max_artifact_bytes for item in self.artifacts):
            raise ValueError("release artifact exceeds the active per-artifact limit")
        if sum(item.declared_size for item in self.artifacts) > self.policy.max_total_bytes:
            raise ValueError("release artifact bytes exceed the active total limit")
        if self.signature.algorithm not in self.policy.allowed_signature_algorithms:
            raise ValueError("signature algorithm is not allowed by the release policy")
        if self.signature.issued_at > self.context.occurred_at:
            raise ValueError("signature cannot be issued after the release operation")
        if self.context.references.approved_configuration.evidence.digest != policy_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the release policy")
        _validate_unique_records(self)
        release_evidence_index(self)
        if len(canonical_json_bytes(normalized_request(self))) > M0208_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M02-08 request exceeds the public ingress limit")
        return self


class IdentificationStageProvenance(FrozenModel):
    module_id: StageModuleId
    module_version: SemanticVersion
    result_digest: Sha256Digest
    byte_digest: Sha256Digest
    disposition: Identifier
    generated_at: AwareDatetime
    configuration_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    analysis_lineage_digest: Sha256Digest
    bound_upstream_result_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=7)
    human_review_required: bool

    @model_validator(mode="after")
    def stage_vocabulary_is_closed(self) -> IdentificationStageProvenance:
        allowed = {
            "GLIO-PROTEOGEN-M02-01": {"conformant", "quarantined"},
            "GLIO-PROTEOGEN-M02-02": {"conformant", "quarantined", "abstained"},
            "GLIO-PROTEOGEN-M02-03": {"accepted", "quarantined", "rejected"},
            "GLIO-PROTEOGEN-M02-04": {"accepted", "quarantined"},
            "GLIO-PROTEOGEN-M02-05": {"accepted", "quarantined"},
            "GLIO-PROTEOGEN-M02-06": {"accepted", "quarantined", "abstained"},
            "GLIO-PROTEOGEN-M02-07": {"supported", "abstained"},
        }[self.module_id]
        if self.disposition not in allowed:
            raise ValueError("stage disposition contradicts its module")
        if len(set(self.bound_upstream_result_digests)) != len(self.bound_upstream_result_digests):
            raise ValueError("stage upstream result digests must be unique")
        return self


class IdentificationQcReproducibilityManifest(FrozenModel):
    release_id: Identifier
    release_version: SemanticVersion
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    artifacts: tuple[IdentificationReleaseArtifact, ...] = Field(
        min_length=M0208_CALLER_ARTIFACT_COUNT,
        max_length=M0208_CALLER_ARTIFACT_COUNT,
    )
    stages: tuple[IdentificationStageProvenance, ...] = Field(
        min_length=M0208_STAGE_COUNT,
        max_length=M0208_STAGE_COUNT,
    )
    software_versions: tuple[IdentificationSoftwareVersion, ...] = Field(
        min_length=1,
        max_length=64,
    )
    reference_versions: tuple[IdentificationReferenceVersion, ...] = Field(
        min_length=1,
        max_length=64,
    )
    reproduction_evidence: IdentificationReproductionEvidence
    reproduction_evidence_digest: Sha256Digest
    m0206_transformation_manifest_digest: Sha256Digest
    m0204_quality_disposition: Identifier
    m0207_support_disposition: Identifier
    subject_binding_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    policy_digest: Sha256Digest
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    fixed_mtime: Literal[0] = 0
    file_mode: Literal[420] = 0o644

    @model_validator(mode="after")
    def manifest_is_a_closed_stage_chain(  # noqa: PLR0912 - exact seven-stage closure.
        self,
    ) -> IdentificationQcReproducibilityManifest:
        roles = [item.role for item in self.artifacts]
        paths = [item.path.casefold() for item in self.artifacts]
        if set(roles) != set(IdentificationReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("manifest requires every caller artifact role exactly once")
        if len(set(paths)) != len(paths):
            raise ValueError("manifest artifact paths must be alias-free")
        if sum(item.declared_size for item in self.artifacts) > M0208_MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("manifest caller artifacts exceed the public byte ceiling")
        metadata_ids = (
            [item.software_id for item in self.software_versions],
            [item.reference_id for item in self.reference_versions],
        )
        if any(len(set(values)) != len(values) for values in metadata_ids):
            raise ValueError("manifest software and reference identifiers must be unique")
        modules = tuple(item.module_id for item in self.stages)
        if modules != _EXPECTED_STAGE_MODULES:
            raise ValueError("manifest stages must be ordered M02-01 through M02-07")
        if self.reproduction_evidence_digest != reproduction_evidence_digest(
            self.reproduction_evidence
        ):
            raise ValueError("manifest reproduction evidence digest is inconsistent")
        stage_by_module = {item.module_id: item for item in self.stages}
        role_by_module = {
            "GLIO-PROTEOGEN-M02-01": IdentificationReleaseArtifactRole.M02_01_CONFORMANCE,
            "GLIO-PROTEOGEN-M02-02": IdentificationReleaseArtifactRole.M02_02_IDENTITY_LINEAGE,
            "GLIO-PROTEOGEN-M02-03": IdentificationReleaseArtifactRole.M02_03_RAW_INGESTION,
            "GLIO-PROTEOGEN-M02-04": IdentificationReleaseArtifactRole.M02_04_QUALITY,
            "GLIO-PROTEOGEN-M02-05": IdentificationReleaseArtifactRole.M02_05_ARTIFACT_DETECTION,
            "GLIO-PROTEOGEN-M02-06": IdentificationReleaseArtifactRole.M02_06_HARMONIZATION,
            "GLIO-PROTEOGEN-M02-07": IdentificationReleaseArtifactRole.M02_07_SUPPORT_ROUTE,
        }
        artifact_by_role = {item.role: item for item in self.artifacts}
        if any(
            artifact_by_role[role_by_module[module]].reference.digest
            != stage_by_module[module].byte_digest
            for module in _EXPECTED_STAGE_MODULES
        ):
            raise ValueError("stage byte digests do not bind their declared caller artifacts")
        expected_m0206 = {
            stage_by_module[module].result_digest for module in _EXPECTED_STAGE_MODULES[:5]
        }
        expected_m0207 = {
            stage_by_module["GLIO-PROTEOGEN-M02-04"].result_digest,
            stage_by_module["GLIO-PROTEOGEN-M02-06"].result_digest,
        }
        if set(stage_by_module["GLIO-PROTEOGEN-M02-06"].bound_upstream_result_digests) != (
            expected_m0206
        ):
            raise ValueError("M02-06 stage does not bind the packaged M02-01 through M02-05 chain")
        if set(stage_by_module["GLIO-PROTEOGEN-M02-07"].bound_upstream_result_digests) != (
            expected_m0207
        ):
            raise ValueError("M02-07 stage does not bind the packaged M02-04 and M02-06 results")
        if any(
            item.bound_upstream_result_digests
            for item in self.stages
            if item.module_id not in {"GLIO-PROTEOGEN-M02-06", "GLIO-PROTEOGEN-M02-07"}
        ):
            raise ValueError("only M02-06 and M02-07 carry C02 result-chain bindings")
        m0204 = stage_by_module["GLIO-PROTEOGEN-M02-04"]
        m0206 = stage_by_module["GLIO-PROTEOGEN-M02-06"]
        m0207 = stage_by_module["GLIO-PROTEOGEN-M02-07"]
        if m0207.analysis_lineage_digest != m0206.result_digest:
            raise ValueError("M02-07 analysis lineage does not bind the packaged M02-06 result")
        if {
            m0204.identity_subject_digest,
            m0206.identity_subject_digest,
            m0207.identity_subject_digest,
            self.subject_binding_digest,
        } != {self.subject_binding_digest}:
            raise ValueError("release subject does not bind the M02-04, M02-06, and M02-07 lineage")
        if self.m0204_quality_disposition != stage_by_module["GLIO-PROTEOGEN-M02-04"].disposition:
            raise ValueError("manifest quality disposition is inconsistent")
        if self.m0207_support_disposition != m0207.disposition:
            raise ValueError("manifest support disposition is inconsistent")
        return self


class IdentificationSignatureVerification(FrozenModel):
    verifier_id: Identifier | None = None
    algorithm: Identifier
    key_id: Identifier
    statement_digest: Sha256Digest
    verified: bool
    reason_code: IdentificationSignatureVerificationReason

    @model_validator(mode="after")
    def outcome_is_closed(self) -> IdentificationSignatureVerification:
        if self.verified != (
            self.reason_code is IdentificationSignatureVerificationReason.VERIFIED
        ):
            raise ValueError("signature verified state contradicts its reason")
        verifier_required = self.reason_code in {
            IdentificationSignatureVerificationReason.VERIFIED,
            IdentificationSignatureVerificationReason.VERIFIER_REJECTED,
        }
        if verifier_required != (self.verifier_id is not None):
            raise ValueError("signature outcome has an inconsistent verifier identifier")
        return self


class IdentificationReleaseQuarantine(FrozenModel):
    code: IdentificationReleaseQuarantineCode
    stage_module_id: StageModuleId | None = None
    reason_code: Identifier
    remediation_code: Identifier

    @model_validator(mode="after")
    def reason_shape_matches_code(self) -> IdentificationReleaseQuarantine:
        if (self.code is IdentificationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE) != (
            self.stage_module_id is not None
        ):
            raise ValueError("only upstream quarantine reasons identify a stage module")
        if self.code is IdentificationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE:
            if self.remediation_code != "review_upstream_stage" or not (
                self.reason_code == "human_review_required"
                or self.reason_code.startswith("stage_disposition_")
            ):
                raise ValueError("upstream quarantine reason vocabulary is inconsistent")
        elif self.remediation_code != "provide_verified_signature" or self.reason_code not in {
            IdentificationSignatureVerificationReason.STATEMENT_MISMATCH.value,
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE.value,
            IdentificationSignatureVerificationReason.VERIFIER_REJECTED.value,
        }:
            raise ValueError("signature quarantine reason vocabulary is inconsistent")
        return self


class IdentificationReleaseMember(FrozenModel):
    path: CanonicalPath
    byte_size: int = Field(gt=0)
    digest: Sha256Digest
    role: IdentificationReleaseArtifactRole | None = None

    @model_validator(mode="after")
    def member_path_and_role_are_closed(self) -> IdentificationReleaseMember:
        _validate_member_path(self.path)
        generated = self.path in {M0208_MANIFEST_PATH, M0208_SIGNATURE_RECEIPT_PATH}
        if generated == (self.role is not None):
            raise ValueError("generated and caller package members require distinct role shapes")
        return self


class IdentificationReleasePackageDescriptor(FrozenModel):
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    byte_size: int = Field(gt=0)
    digest: Sha256Digest
    member_count: Literal[10] = M0208_ARCHIVE_MEMBER_COUNT
    members: tuple[IdentificationReleaseMember, ...] = Field(
        min_length=M0208_ARCHIVE_MEMBER_COUNT,
        max_length=M0208_ARCHIVE_MEMBER_COUNT,
    )

    @model_validator(mode="after")
    def inventory_is_exact_and_unique(self) -> IdentificationReleasePackageDescriptor:
        paths = [item.path for item in self.members]
        if len(set(paths)) != len(paths) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("package descriptor member paths must be alias-free")
        if set(paths) != {
            *(item.path for item in self.members if item.role is not None),
            M0208_MANIFEST_PATH,
            M0208_SIGNATURE_RECEIPT_PATH,
        }:
            raise ValueError("package descriptor requires both generated members")
        roles = [item.role for item in self.members if item.role is not None]
        if set(roles) != set(IdentificationReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("package descriptor requires all caller artifact roles")
        return self


class IdentificationQcReleaseResult(FrozenModel):
    output_type: Literal["identification_qc_release_result"] = "identification_qc_release_result"
    release_result_id: Identifier
    result_version: Literal["1.0.0"] = M0208_CONTRACT_VERSION
    request_digest: Sha256Digest
    context_digest: Sha256Digest
    context: ExecutionContext
    policy_digest: Sha256Digest
    policy: IdentificationReleasePolicy
    manifest_digest: Sha256Digest
    manifest: IdentificationQcReproducibilityManifest
    signature: ExternalIdentificationSignature
    signature_verification: IdentificationSignatureVerification
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: IdentificationReleaseDisposition
    package_descriptor: IdentificationReleasePackageDescriptor | None = None
    quarantine_reasons: tuple[IdentificationReleaseQuarantine, ...] = Field(
        default=(),
        max_length=8,
    )
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> IdentificationQcReleaseResult:
        _validate_result(self)
        expected = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected)
        elif self.result_digest != expected:
            raise ValueError("M02-08 result digest does not match its content")
        return self


class IdentificationReleaseVerification(FrozenModel):
    content_verified: bool
    authenticity_verified: bool
    verified: bool
    package_digest: Sha256Digest | None = None
    manifest_digest: Sha256Digest | None = None
    member_count: int = Field(ge=0, le=M0208_ARCHIVE_MEMBER_COUNT)
    signature_verification: IdentificationSignatureVerification
    reason_code: IdentificationPackageVerificationReason

    @model_validator(mode="after")
    def verification_outcome_is_closed(self) -> IdentificationReleaseVerification:
        if self.authenticity_verified != self.signature_verification.verified:
            raise ValueError("package authenticity contradicts signature verification")
        if self.verified != (self.content_verified and self.authenticity_verified):
            raise ValueError("package verified state contradicts its component checks")
        if self.verified != (self.reason_code is IdentificationPackageVerificationReason.VERIFIED):
            raise ValueError("package verified state contradicts its reason code")
        if self.content_verified and (
            self.package_digest is None
            or self.manifest_digest is None
            or self.member_count != M0208_ARCHIVE_MEMBER_COUNT
        ):
            raise ValueError("content-verified package requires complete content receipts")
        return self


def release_evidence_index(
    request: BuildIdentificationQcReleaseRequest,
) -> tuple[tuple[ArtifactReference, str], ...]:
    """Return the exact authority-safe evidence index for one request/result."""

    refs = request.context.references
    items: list[tuple[ArtifactReference, str]] = [
        (refs.approved_configuration.evidence, "Caller-approved release configuration."),
        (refs.identity_lineage.evidence, "Caller-resolved identification lineage."),
        (refs.provenance.evidence, "Caller-accepted provenance control."),
        (refs.consent.evidence, "Caller-granted consent control."),
        (refs.quality.evidence, "Caller-accepted quality control."),
        (refs.support.evidence, "Caller-accepted support control."),
        (refs.intended_use.evidence, "Caller-accepted intended-use control."),
        (request.policy.evidence, "Pinned M02-08 release policy."),
    ]
    items.extend(
        (item.reference, f"Declared {item.role.value} archive member.")
        for item in request.artifacts
    )
    items.extend(
        (item.evidence, f"Declared software build {item.software_id}.")
        for item in request.software_versions
    )
    items.extend(
        (item.evidence, f"Declared reference build {item.reference_id}.")
        for item in request.reference_versions
    )
    items.extend(
        (reference, f"Pinned reproduction evidence: {name}.")
        for name, reference in _named_reproduction_references(request.reproduction_evidence)
    )
    items.append((request.signature.evidence, "Caller-supplied external signature evidence."))
    digests = [reference.digest for reference, _ in items]
    if len(set(digests)) != len(digests):
        raise ValueError("M02-08 evidence sources must have unique content digests")
    return tuple(items)


def expected_release_quarantine_reasons(
    manifest: IdentificationQcReproducibilityManifest,
    verification: IdentificationSignatureVerification,
) -> tuple[IdentificationReleaseQuarantine, ...]:
    """Derive the exact typed reasons that prohibit release bytes."""

    accepted = {
        "GLIO-PROTEOGEN-M02-01": "conformant",
        "GLIO-PROTEOGEN-M02-02": "conformant",
        "GLIO-PROTEOGEN-M02-03": "accepted",
        "GLIO-PROTEOGEN-M02-04": "accepted",
        "GLIO-PROTEOGEN-M02-05": "accepted",
        "GLIO-PROTEOGEN-M02-06": "accepted",
        "GLIO-PROTEOGEN-M02-07": "supported",
    }
    reasons = [
        IdentificationReleaseQuarantine(
            code=IdentificationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
            stage_module_id=stage.module_id,
            reason_code=(
                "human_review_required"
                if stage.human_review_required
                else f"stage_disposition_{stage.disposition}"
            ),
            remediation_code="review_upstream_stage",
        )
        for stage in manifest.stages
        if stage.disposition != accepted[stage.module_id] or stage.human_review_required
    ]
    if not reasons and not verification.verified:
        reasons.append(
            IdentificationReleaseQuarantine(
                code=IdentificationReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                reason_code=verification.reason_code.value,
                remediation_code="provide_verified_signature",
            )
        )
    return tuple(sorted(reasons, key=canonical_json_bytes))


def _validate_result(  # noqa: PLR0912 - explicit release closure precedence.
    result: IdentificationQcReleaseResult,
) -> None:
    _require_authorized_context(result.context)
    if result.context_digest != context_digest(result.context):
        raise ValueError("M02-08 context digest is inconsistent")
    if result.policy_digest != policy_digest(result.policy):
        raise ValueError("M02-08 policy digest is inconsistent")
    manifest = result.manifest
    if manifest.policy_digest != result.policy_digest:
        raise ValueError("release manifest does not bind the result policy")
    if manifest.subject_binding_digest != result.context.references.identity_lineage.binding_digest:
        raise ValueError("release manifest does not bind the authorized identity subject")
    if (
        manifest.intended_use_evidence_digest
        != result.context.references.intended_use.evidence.digest
    ):
        raise ValueError("release manifest does not bind intended-use evidence")
    if result.manifest_digest != manifest_digest(manifest):
        raise ValueError("release manifest digest does not match its exact content")
    expected_statement = signing_statement_digest(
        active_manifest_digest=result.manifest_digest,
        active_policy_digest=result.policy_digest,
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        subject_binding_digest=manifest.subject_binding_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
    )
    verification = result.signature_verification
    if (
        verification.algorithm != result.signature.algorithm
        or verification.key_id != result.signature.key_id
        or verification.statement_digest != expected_statement
        or (
            verification.verifier_id is not None
            and verification.verifier_id not in result.policy.allowed_verifier_ids
        )
    ):
        raise ValueError("signature verification does not bind the release statement")
    accepted = {
        "GLIO-PROTEOGEN-M02-01": "conformant",
        "GLIO-PROTEOGEN-M02-02": "conformant",
        "GLIO-PROTEOGEN-M02-03": "accepted",
        "GLIO-PROTEOGEN-M02-04": "accepted",
        "GLIO-PROTEOGEN-M02-05": "accepted",
        "GLIO-PROTEOGEN-M02-06": "accepted",
        "GLIO-PROTEOGEN-M02-07": "supported",
    }
    upstream_releasable = all(
        stage.disposition == accepted[stage.module_id] and not stage.human_review_required
        for stage in manifest.stages
    )
    if not upstream_releasable and (
        verification.reason_code is not IdentificationSignatureVerificationReason.NOT_ATTEMPTED
    ):
        raise ValueError("unreleasable upstream chain must not invoke signature verification")
    if upstream_releasable:
        statement_matches = result.signature.claimed_statement_digest == expected_statement
        if statement_matches == (
            verification.reason_code is IdentificationSignatureVerificationReason.STATEMENT_MISMATCH
        ):
            raise ValueError("signature statement mismatch outcome is inconsistent")
        if (
            statement_matches
            and verification.reason_code is IdentificationSignatureVerificationReason.NOT_ATTEMPTED
        ):
            raise ValueError("releasable upstream chain requires a signature verification attempt")
    expected_reasons = expected_release_quarantine_reasons(manifest, verification)
    released = not expected_reasons
    if released != (result.disposition is IdentificationReleaseDisposition.RELEASED):
        raise ValueError("release disposition contradicts upstream and signature closure")
    if result.quarantine_reasons != expected_reasons:
        raise ValueError("release quarantine reasons are not exactly derived")
    if released != (result.package_descriptor is not None):
        raise ValueError("only a released result may carry a package descriptor")
    if released:
        _validate_package_descriptor(result)
    _validate_result_request_digest(result)
    _validate_result_envelope(result)


def _validate_result_request_digest(result: IdentificationQcReleaseResult) -> None:
    manifest = result.manifest
    request = BuildIdentificationQcReleaseRequest(
        context=result.context,
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        artifacts=manifest.artifacts,
        software_versions=manifest.software_versions,
        reference_versions=manifest.reference_versions,
        reproduction_evidence=manifest.reproduction_evidence,
        policy=result.policy,
        signature=result.signature,
        supersedes_result_digest=result.supersedes_result_digest,
    )
    if result.request_digest != canonical_request_digest(request):
        raise ValueError("M02-08 request digest is inconsistent")


def _validate_package_descriptor(result: IdentificationQcReleaseResult) -> None:
    descriptor = result.package_descriptor
    if descriptor is None:
        raise ValueError("released result requires a package descriptor")
    caller_by_role = {item.role: item for item in result.manifest.artifacts}
    members_by_path = {item.path: item for item in descriptor.members}
    for role, artifact in caller_by_role.items():
        member = members_by_path.get(artifact.path)
        if member is None or (
            member.role,
            member.byte_size,
            member.digest,
        ) != (role, artifact.declared_size, artifact.reference.digest):
            raise ValueError("package descriptor contradicts a caller artifact")
    manifest_member = members_by_path.get(M0208_MANIFEST_PATH)
    manifest_bytes = canonical_json_bytes(normalized_manifest(result.manifest))
    if manifest_member is None or (
        manifest_member.digest != result.manifest_digest
        or manifest_member.byte_size != len(manifest_bytes)
    ):
        raise ValueError("package descriptor does not bind the manifest member")
    receipt_member = members_by_path.get(M0208_SIGNATURE_RECEIPT_PATH)
    receipt_bytes = canonical_json_bytes(result.signature_verification.model_dump(mode="python"))
    if receipt_member is None or (
        receipt_member.digest != sha256_bytes(receipt_bytes)
        or receipt_member.byte_size != len(receipt_bytes)
    ):
        raise ValueError("package descriptor does not bind the verification receipt")


def _validate_result_envelope(result: IdentificationQcReleaseResult) -> None:
    expected_support = {
        IdentificationReleaseDisposition.RELEASED: (
            SupportStatus.LIMITED,
            "identification_release_packaged",
            M0208_RELEASED_SUPPORT_RATIONALE,
            False,
        ),
        IdentificationReleaseDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identification_release_quarantined",
            M0208_QUARANTINED_SUPPORT_RATIONALE,
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.support.rationale,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("M02-08 support envelope contradicts disposition")
    expected_limitations = {
        M0208_PACKAGE_LIMITATION_CODE: M0208_PACKAGE_LIMITATION_STATEMENT,
        M0208_AUTHORITY_LIMITATION_CODE: M0208_AUTHORITY_LIMITATION_STATEMENT,
    }
    if {item.code: item.statement for item in result.limitations} != expected_limitations:
        raise ValueError("M02-08 requires both exact limitation statements")
    _validate_uncertainty(result.uncertainty)
    suffix = result.request_digest.removeprefix("sha256:")
    if result.release_result_id != f"release.m0208.{suffix}":
        raise ValueError("release result identifier does not bind the request digest")
    provenance = result.provenance
    if (
        provenance.activity_id != f"activity.m0208.{suffix}"
        or provenance.actor_id != result.context.actor_id
        or provenance.module_id != M0208_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or result.completed_at != result.context.occurred_at
        or provenance.configuration_digest != result.policy_digest
    ):
        raise ValueError("M02-08 provenance envelope is inconsistent")
    request = BuildIdentificationQcReleaseRequest(
        context=result.context,
        release_id=result.manifest.release_id,
        release_version=result.manifest.release_version,
        artifacts=result.manifest.artifacts,
        software_versions=result.manifest.software_versions,
        reference_versions=result.manifest.reference_versions,
        reproduction_evidence=result.manifest.reproduction_evidence,
        policy=result.policy,
        signature=result.signature,
        supersedes_result_digest=result.supersedes_result_digest,
    )
    required = release_provenance_input_digests(
        request,
        result.manifest,
        request_digest=result.request_digest,
        context_digest=result.context_digest,
        policy_digest=result.policy_digest,
        manifest_digest=result.manifest_digest,
        controls=result.provenance.control_decisions,
    )
    if set(provenance.input_digests) != required or len(provenance.input_digests) != len(required):
        raise ValueError("M02-08 provenance must contain the exact unique input digest set")
    _validate_controls(result)
    expected_evidence = {
        reference.digest: (reference, "evidence", claim)
        for reference, claim in release_evidence_index(request)
    }
    actual_evidence = {
        item.reference.digest: (item.reference, item.role, item.claim) for item in result.evidence
    }
    if len(actual_evidence) != len(result.evidence) or actual_evidence != expected_evidence:
        raise ValueError("M02-08 evidence index or claims are inconsistent")


def release_provenance_input_digests(  # noqa: PLR0913 - exact digest receipt.
    request: BuildIdentificationQcReleaseRequest,
    manifest: IdentificationQcReproducibilityManifest,
    *,
    request_digest: Sha256Digest,
    context_digest: Sha256Digest,
    policy_digest: Sha256Digest,
    manifest_digest: Sha256Digest,
    controls: tuple[ControlDecisionRecord, ...],
) -> set[Sha256Digest]:
    return {
        request_digest,
        context_digest,
        policy_digest,
        manifest_digest,
        *(stage.result_digest for stage in manifest.stages),
        *(stage.byte_digest for stage in manifest.stages),
        *(item.reference.digest for item in request.artifacts),
        *(item.build_digest for item in request.software_versions),
        *(item.digest for item in request.reference_versions),
        *(reference.digest for reference, _ in release_evidence_index(request)),
        *(item.evidence_digest for item in controls),
    }


def _validate_controls(result: IdentificationQcReleaseResult) -> None:
    refs = result.context.references
    expected = {
        "approved_configuration": (
            refs.approved_configuration.decision_id,
            refs.approved_configuration.state.value,
            refs.approved_configuration.policy_version,
            refs.approved_configuration.evidence.digest,
            None,
        ),
        "identity_lineage": (
            refs.identity_lineage.decision_id,
            refs.identity_lineage.state.value,
            refs.identity_lineage.policy_version,
            refs.identity_lineage.evidence.digest,
            result.manifest.subject_binding_digest,
        ),
        "provenance": (
            refs.provenance.decision_id,
            refs.provenance.state.value,
            refs.provenance.policy_version,
            refs.provenance.evidence.digest,
            None,
        ),
        "consent": (
            refs.consent.decision_id,
            refs.consent.state.value,
            refs.consent.policy_version,
            refs.consent.evidence.digest,
            None,
        ),
        "quality": (
            refs.quality.decision_id,
            refs.quality.state.value,
            refs.quality.policy_version,
            refs.quality.evidence.digest,
            None,
        ),
        "support": (
            refs.support.decision_id,
            refs.support.state.value,
            refs.support.policy_version,
            refs.support.evidence.digest,
            None,
        ),
        "intended_use": (
            refs.intended_use.decision_id,
            refs.intended_use.state.value,
            refs.intended_use.policy_version,
            refs.intended_use.evidence.digest,
            None,
        ),
    }
    actual = {
        item.role.value: (
            item.decision_id,
            item.state,
            item.policy_version,
            item.evidence_digest,
            item.subject_digest,
        )
        for item in result.provenance.control_decisions
    }
    if actual != expected:
        raise ValueError("M02-08 control decisions do not match the embedded context")
    consent = refs.consent
    if (
        result.provenance.consent_decision_id,
        result.provenance.consent_state,
        result.provenance.consent_policy_version,
        result.provenance.consent_evidence_digest,
    ) != (
        consent.decision_id,
        consent.state,
        consent.policy_version,
        consent.evidence.digest,
    ):
        raise ValueError("M02-08 consent provenance is inconsistent")


def _validate_uncertainty(uncertainty: UncertaintyProfile) -> None:
    for dimension, rationale in M0208_UNCERTAINTY_RATIONALES.items():
        estimate = getattr(uncertainty, dimension)
        if (
            estimate.state is not EstimateState.NOT_ESTIMABLE
            or estimate.probability is not None
            or estimate.rationale != rationale
        ):
            raise ValueError("M02-08 uncertainty must remain deterministic and not estimable")
    if uncertainty.sensitivity_notes != M0208_SENSITIVITY_NOTES:
        raise ValueError("M02-08 uncertainty sensitivity notes are inconsistent")


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M02-08")
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage is not resolved")
    if any(
        item.state is not UpstreamDecisionState.ACCEPTED
        for item in (
            refs.approved_configuration,
            refs.provenance,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
    ):
        raise ValueError("upstream controls do not authorize M02-08")


def _validate_member_path(value: str) -> None:
    path = PurePosixPath(value)
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("release member path must be ASCII") from error
    parts = path.parts
    if (
        path.is_absolute()
        or "\\" in value
        or ":" in value
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in parts)
        or len(encoded) > _USTAR_PATH_BYTES
    ):
        raise ValueError("release member path must be canonical safe relative POSIX")
    name_bytes = len(path.name.encode("ascii"))
    prefix = "" if len(parts) == 1 else "/".join(parts[:-1])
    if name_bytes > _USTAR_NAME_BYTES or len(prefix.encode("ascii")) > _USTAR_PREFIX_BYTES:
        raise ValueError("release member path is not representable in USTAR")


def _validate_unique_records(request: BuildIdentificationQcReleaseRequest) -> None:
    groups = (
        [item.software_id for item in request.software_versions],
        [item.reference_id for item in request.reference_versions],
    )
    if any(len(set(values)) != len(values) for values in groups):
        raise ValueError("release metadata identifiers must be unique")


def _named_reproduction_references(
    evidence: IdentificationReproductionEvidence,
) -> tuple[tuple[str, ArtifactReference], ...]:
    return (
        ("environment_lock", evidence.environment_lock),
        ("build_recipe", evidence.build_recipe),
        ("locked_tests", evidence.locked_tests),
        ("benchmark", evidence.benchmark),
        ("traceability", evidence.traceability),
        ("reviewer_signoff", evidence.reviewer_signoff),
        ("rollback", evidence.rollback),
    )


def _reproduction_references(
    evidence: IdentificationReproductionEvidence,
) -> tuple[ArtifactReference, ...]:
    return tuple(reference for _, reference in _named_reproduction_references(evidence))


__all__ = [
    "M0208_ARCHIVE_MEMBER_COUNT",
    "M0208_AUTHORITY_LIMITATION_CODE",
    "M0208_AUTHORITY_LIMITATION_STATEMENT",
    "M0208_CALLER_ARTIFACT_COUNT",
    "M0208_CONTRACT_VERSION",
    "M0208_MANIFEST_PATH",
    "M0208_MAX_ARTIFACT_BYTES",
    "M0208_MAX_CANONICAL_REQUEST_BYTES",
    "M0208_MAX_TOTAL_ARTIFACT_BYTES",
    "M0208_MODULE_ID",
    "M0208_PACKAGE_LIMITATION_CODE",
    "M0208_PACKAGE_LIMITATION_STATEMENT",
    "M0208_QUARANTINED_SUPPORT_RATIONALE",
    "M0208_RELEASED_SUPPORT_RATIONALE",
    "M0208_SENSITIVITY_NOTES",
    "M0208_SIGNATURE_RECEIPT_PATH",
    "M0208_STAGE_COUNT",
    "M0208_UNCERTAINTY_RATIONALES",
    "BuildIdentificationQcReleaseRequest",
    "ExternalIdentificationSignature",
    "IdentificationPackageVerificationReason",
    "IdentificationParentProteinSubtypeReceipt",
    "IdentificationQcReleaseResult",
    "IdentificationQcReproducibilityManifest",
    "IdentificationReferenceVersion",
    "IdentificationReleaseArtifact",
    "IdentificationReleaseArtifactRole",
    "IdentificationReleaseDisposition",
    "IdentificationReleaseMember",
    "IdentificationReleasePackageDescriptor",
    "IdentificationReleasePolicy",
    "IdentificationReleaseQuarantine",
    "IdentificationReleaseQuarantineCode",
    "IdentificationReleaseVerification",
    "IdentificationReproductionEvidence",
    "IdentificationSignatureVerification",
    "IdentificationSignatureVerificationReason",
    "IdentificationSoftwareVersion",
    "IdentificationStageProvenance",
    "expected_release_quarantine_reasons",
    "release_evidence_index",
    "release_provenance_input_digests",
]
