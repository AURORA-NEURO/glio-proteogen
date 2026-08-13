"""Strict M03-08 contracts for deterministic protein-inference release packaging."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m03_08.canonical import (
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
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

M0308_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-08"
M0308_CONTRACT_VERSION: Final = "1.0.0"
M0308_OPERATION: Final = "package_protein_inference_release"
M0308_PARENT: Final = "complex_activity"
M0308_CALLER_ARTIFACT_COUNT: Final = 8
M0308_STAGE_COUNT: Final = 7
M0308_ARCHIVE_MEMBER_COUNT: Final = 10
M0308_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0308_MAX_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
M0308_MAX_TOTAL_ARTIFACT_BYTES: Final = 64 * 1024 * 1024
M0308_MAX_PACKAGE_BYTES: Final = 72 * 1024 * 1024
M0308_MAX_SOFTWARE_VERSIONS: Final = 64
M0308_MAX_REFERENCE_VERSIONS: Final = 64
M0308_MAX_SIGNATURE_ALGORITHMS: Final = 16
M0308_MAX_VERIFIER_IDS: Final = 16
M0308_MAX_SIGNATURE_VALUE_CHARS: Final = 16_384
M0308_MAX_STAGE_UPSTREAM_DIGESTS: Final = 3
M0308_MAX_QUARANTINE_REASONS: Final = 8
M0308_MAX_EVIDENCE: Final = 152
M0308_MANIFEST_PATH: Final = "META-INF/glio-proteogen-m03-08/reproducibility-manifest.json"
M0308_SIGNATURE_RECEIPT_PATH: Final = "META-INF/glio-proteogen-m03-08/signature-verification.json"
M0308_PACKAGE_LIMITATION_CODE: Final = "deterministic_protein_inference_packaging_only"
M0308_AUTHORITY_LIMITATION_CODE: Final = "external_signature_authority_unverified"
M0308_REPRODUCIBILITY_LIMITATION_CODE: Final = "scientific_reproducibility_not_validated"
M0308_PACKAGE_LIMITATION_STATEMENT: Final = (
    "M03-08 packages one closed protein-inference chain without changing or interpreting "
    "its scientific content."
)
M0308_AUTHORITY_LIMITATION_STATEMENT: Final = (
    "Signature verification records one injected verifier outcome and does not establish "
    "signer identity, key custody, certificate validity, or release authority."
)
M0308_REPRODUCIBILITY_LIMITATION_STATEMENT: Final = (
    "The package records exact-byte reproduction inputs but does not validate scientific "
    "reproducibility or the external evidence issuers."
)
M0308_RELEASED_SUPPORT_RATIONALE: Final = (
    "The authorized protein-inference chain and injected signature verification satisfied "
    "the pinned deterministic release profile."
)
M0308_QUARANTINED_SUPPORT_RATIONALE: Final = (
    "The protein-inference release was withheld because an upstream stage or signature "
    "verification did not satisfy the pinned release profile."
)
M0308_SENSITIVITY_NOTES: Final = (
    "No calibrated probability is produced by deterministic release packaging.",
    "Scientific, cryptographic, and release-authority validity remain external.",
)
M0308_UNCERTAINTY_RATIONALES: Final[dict[str, str]] = {
    "measurement": "Measurement uncertainty is preserved in packaged upstream results.",
    "sampling": "Sampling uncertainty is preserved in packaged upstream results.",
    "parameter": "Packaging has no estimated scientific parameter uncertainty.",
    "model_form": "M03-08 performs no scientific model inference.",
    "identification": "Identification uncertainty is preserved in packaged upstream results.",
    "support": "Support uncertainty is preserved in the packaged M03-07 result.",
    "transport": "External verifier, evidence, and authority issuers are not authenticated.",
}

_USTAR_NAME_BYTES: Final = 100
_USTAR_PREFIX_BYTES: Final = 155
_USTAR_PATH_BYTES: Final = 255
_USTAR_BLOCK_BYTES: Final = 512
_USTAR_END_BYTES: Final = 2 * _USTAR_BLOCK_BYTES
_USTAR_RECORD_BYTES: Final = 10_240


class ProteinInferenceStageModuleId(StrEnum):
    M03_01 = "GLIO-PROTEOGEN-M03-01"
    M03_02 = "GLIO-PROTEOGEN-M03-02"
    M03_03 = "GLIO-PROTEOGEN-M03-03"
    M03_04 = "GLIO-PROTEOGEN-M03-04"
    M03_05 = "GLIO-PROTEOGEN-M03-05"
    M03_06 = "GLIO-PROTEOGEN-M03-06"
    M03_07 = "GLIO-PROTEOGEN-M03-07"


_EXPECTED_STAGE_MODULES: Final[tuple[ProteinInferenceStageModuleId, ...]] = (
    ProteinInferenceStageModuleId.M03_01,
    ProteinInferenceStageModuleId.M03_02,
    ProteinInferenceStageModuleId.M03_03,
    ProteinInferenceStageModuleId.M03_04,
    ProteinInferenceStageModuleId.M03_05,
    ProteinInferenceStageModuleId.M03_06,
    ProteinInferenceStageModuleId.M03_07,
)

CanonicalPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/-]+$"),
]
SignatureValue = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=M0308_MAX_SIGNATURE_VALUE_CHARS,
        pattern=r"^[A-Za-z0-9+/=_-]+$",
    ),
]


class ProteinInferenceReleaseArtifactRole(StrEnum):
    PARENT_COMPLEX_ACTIVITY_HANDOFF = "parent_complex_activity_handoff"
    M03_01_PROTOCOL_CONFORMANCE = "m03_01_protocol_conformance"
    M03_02_IDENTITY_LINEAGE = "m03_02_identity_lineage"
    M03_03_RAW_INGESTION = "m03_03_raw_ingestion"
    M03_04_QUALITY = "m03_04_quality"
    M03_05_ARTIFACT_DETECTION = "m03_05_artifact_detection"
    M03_06_HARMONIZATION = "m03_06_harmonization"
    M03_07_SUPPORT_ROUTE = "m03_07_support_route"


class ProteinInferenceSignatureAlgorithm(StrEnum):
    ED25519 = "ed25519"
    ECDSA_P256_SHA256 = "ecdsa_p256_sha256"
    RSA_PSS_SHA256 = "rsa_pss_sha256"


_ROLE_PATHS: Final[dict[ProteinInferenceReleaseArtifactRole, str]] = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        "parent/complex-activity-handoff.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE: (
        "stages/m03-01-protocol-conformance.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE: (
        "stages/m03-02-identity-lineage.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION: ("stages/m03-03-raw-ingestion.json"),
    ProteinInferenceReleaseArtifactRole.M03_04_QUALITY: "stages/m03-04-quality.json",
    ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION: (
        "stages/m03-05-artifact-detection.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION: ("stages/m03-06-harmonization.json"),
    ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE: ("stages/m03-07-support-route.json"),
}
ProteinInferenceReleaseIdentifierNamespace = Literal[
    "request",
    "actor",
    "decision",
    "release",
    "policy",
    "software",
    "reference",
    "build",
    "signer",
    "key",
    "verifier",
    "evidence",
    "reviewer",
    "parent",
]
_OPAQUE_IDENTIFIER: Final = re.compile(r"^[a-z][a-z0-9_]*\.[0-9a-f]{64}$")
_OWNED_MEDIA_TYPE: Final = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
_ARTIFACT_REFERENCE_SHAPES: Final[
    dict[ProteinInferenceReleaseArtifactRole, tuple[re.Pattern[str], str]]
] = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        re.compile(r"^parent\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.complex-activity-handoff+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE: (
        re.compile(r"^result\.m0301\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-01+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE: (
        re.compile(r"^result\.m0302\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-02+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION: (
        re.compile(r"^result\.m0303\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-03+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_04_QUALITY: (
        re.compile(r"^result\.m0304\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-04+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION: (
        re.compile(r"^result\.m0305\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-05+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION: (
        re.compile(r"^result\.m0306\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-06+json",
    ),
    ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE: (
        re.compile(r"^route\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m03-07+json",
    ),
}


def opaque_release_identifier(
    namespace: ProteinInferenceReleaseIdentifierNamespace,
    value: object,
) -> Identifier:
    """Return one namespaced opaque identifier derived from canonical content."""

    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _opaque_identifier(value: Identifier, namespace: str) -> Identifier:
    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {namespace} digest alias")
    return value


def _owned_evidence(value: ArtifactReference) -> ArtifactReference:
    _opaque_identifier(value.artifact_id, "evidence")
    if _OWNED_MEDIA_TYPE.fullmatch(value.media_type) is None:
        raise ValueError("M03-08 evidence media type must use lowercase type/subtype syntax")
    return value


class ProteinInferenceReleaseDisposition(StrEnum):
    RELEASED = "released"
    QUARANTINED = "quarantined"


class ProteinInferenceSignatureVerificationReason(StrEnum):
    VERIFIED = "verified"
    NOT_ATTEMPTED = "not_attempted"
    STATEMENT_MISMATCH = "statement_mismatch"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFIER_REJECTED = "verifier_rejected"


class ProteinInferenceReleaseQuarantineCode(StrEnum):
    UPSTREAM_NOT_RELEASABLE = "upstream_not_releasable"
    SIGNATURE_UNVERIFIED = "signature_unverified"


class ProteinInferencePackageVerificationReason(StrEnum):
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


class ProteinInferenceReleaseArtifact(FrozenModel):
    path: CanonicalPath
    role: ProteinInferenceReleaseArtifactRole
    reference: ArtifactReference
    declared_size: int = Field(gt=0, le=M0308_MAX_ARTIFACT_BYTES)

    @model_validator(mode="after")
    def path_is_safe_ustar_member(self) -> ProteinInferenceReleaseArtifact:
        _validate_member_path(self.path)
        if self.path.casefold().startswith("meta-inf/glio-proteogen-m03-08/"):
            raise ValueError("caller artifact cannot use the reserved M03-08 namespace")
        if self.path != _ROLE_PATHS[self.role]:
            raise ValueError("release artifact role requires its fixed canonical path")
        artifact_pattern, media_type = _ARTIFACT_REFERENCE_SHAPES[self.role]
        if (
            artifact_pattern.fullmatch(self.reference.artifact_id) is None
            or self.reference.media_type != media_type
        ):
            raise ValueError("release artifact reference contradicts its fixed role")
        return self


class ProteinInferenceParentComplexActivityReceipt(FrozenModel):
    """Minimal caller-owned parent receipt; M03-08 makes no activity inference."""

    parent_target: Literal["complex_activity"] = M0308_PARENT
    identity_resolution_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    support_route_result_digest: Sha256Digest
    emits_complex_activity: Literal[False] = False


class ProteinInferenceSoftwareVersion(FrozenModel):
    software_id: Identifier
    version: SemanticVersion
    build_digest: Sha256Digest
    evidence: ArtifactReference

    @field_validator("software_id")
    @classmethod
    def software_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "software")

    @field_validator("evidence")
    @classmethod
    def software_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class ProteinInferenceReferenceVersion(FrozenModel):
    reference_id: Identifier
    build_id: Identifier
    version: NonEmptyStr
    digest: Sha256Digest
    evidence: ArtifactReference

    @field_validator("reference_id")
    @classmethod
    def reference_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "reference")

    @field_validator("build_id")
    @classmethod
    def build_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "build")

    @field_validator("evidence")
    @classmethod
    def reference_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class ProteinInferenceReproductionEvidence(FrozenModel):
    environment_lock: ArtifactReference
    build_recipe: ArtifactReference
    locked_tests: ArtifactReference
    benchmark: ArtifactReference
    traceability: ArtifactReference
    reviewer_signoff: ArtifactReference
    rollback: ArtifactReference

    @field_validator(
        "environment_lock",
        "build_recipe",
        "locked_tests",
        "benchmark",
        "traceability",
        "reviewer_signoff",
        "rollback",
    )
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)

    @model_validator(mode="after")
    def seven_evidence_items_are_distinct(self) -> ProteinInferenceReproductionEvidence:
        references = _reproduction_references(self)
        if len({item.digest for item in references}) != len(references):
            raise ValueError("reproduction evidence digests must be unique")
        return self


class ProteinInferenceReleasePolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    max_total_bytes: int = Field(
        default=M0308_MAX_TOTAL_ARTIFACT_BYTES,
        gt=0,
        le=M0308_MAX_TOTAL_ARTIFACT_BYTES,
    )
    max_artifact_bytes: int = Field(
        default=M0308_MAX_ARTIFACT_BYTES,
        gt=0,
        le=M0308_MAX_ARTIFACT_BYTES,
    )
    fixed_mtime: Literal[0] = 0
    file_mode: Literal[420] = 0o644
    allowed_signature_algorithms: tuple[ProteinInferenceSignatureAlgorithm, ...] = Field(
        min_length=1, max_length=M0308_MAX_SIGNATURE_ALGORITHMS
    )
    allowed_verifier_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0308_MAX_VERIFIER_IDS
    )
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("policy_id")
    @classmethod
    def policy_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "policy")

    @field_validator("allowed_signature_algorithms")
    @classmethod
    def algorithms_are_canonical(
        cls, values: tuple[ProteinInferenceSignatureAlgorithm, ...]
    ) -> tuple[ProteinInferenceSignatureAlgorithm, ...]:
        return tuple(sorted(values, key=str))

    @field_validator("allowed_verifier_ids")
    @classmethod
    def verifier_ids_are_opaque(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(_opaque_identifier(item, "verifier") for item in values))

    @field_validator("evidence")
    @classmethod
    def policy_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "reviewer")

    @model_validator(mode="after")
    def policy_sets_are_unique(self) -> ProteinInferenceReleasePolicy:
        for values in (self.allowed_signature_algorithms, self.allowed_verifier_ids):
            if len(set(values)) != len(values):
                raise ValueError("release policy allowlists must be unique")
        return self


class ExternalProteinInferenceSignature(FrozenModel):
    signer_id: Identifier
    key_id: Identifier
    algorithm: ProteinInferenceSignatureAlgorithm
    claimed_statement_digest: Sha256Digest
    signature_value: SignatureValue
    issued_at: AwareDatetime
    evidence: ArtifactReference

    @field_validator("signer_id")
    @classmethod
    def signer_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "signer")

    @field_validator("key_id")
    @classmethod
    def key_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "key")

    @field_validator("evidence")
    @classmethod
    def signature_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class BuildProteinInferenceReleaseRequest(FrozenModel):
    operation: Literal["package_protein_inference_release"] = M0308_OPERATION
    contract_version: Literal["1.0.0"] = M0308_CONTRACT_VERSION
    context: ExecutionContext
    release_id: Identifier
    release_version: SemanticVersion
    artifacts: tuple[ProteinInferenceReleaseArtifact, ...] = Field(
        min_length=M0308_CALLER_ARTIFACT_COUNT,
        max_length=M0308_CALLER_ARTIFACT_COUNT,
    )
    software_versions: tuple[ProteinInferenceSoftwareVersion, ...] = Field(
        min_length=1,
        max_length=M0308_MAX_SOFTWARE_VERSIONS,
    )
    reference_versions: tuple[ProteinInferenceReferenceVersion, ...] = Field(
        min_length=1,
        max_length=M0308_MAX_REFERENCE_VERSIONS,
    )
    reproduction_evidence: ProteinInferenceReproductionEvidence
    policy: ProteinInferenceReleasePolicy
    signature: ExternalProteinInferenceSignature
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("release_id")
    @classmethod
    def release_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "release")

    @field_validator("artifacts", "software_versions", "reference_versions")
    @classmethod
    def records_are_canonical[T](cls, values: tuple[T, ...]) -> tuple[T, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def request_is_authorized_closed_and_bounded(self) -> BuildProteinInferenceReleaseRequest:
        _require_authorized_context(self.context)
        _validate_context_opacity(self.context)
        if self.context.references.identity_lineage.binding_digest is None:
            raise ValueError("M03-08 release requires an exact identity lineage binding")
        roles = [item.role for item in self.artifacts]
        paths = [item.path for item in self.artifacts]
        if len(set(roles)) != len(ProteinInferenceReleaseArtifactRole) or set(roles) != set(
            ProteinInferenceReleaseArtifactRole
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
        if self.policy.reviewed_at > self.signature.issued_at:
            raise ValueError("release policy must be reviewed before the external signature")
        if self.context.references.approved_configuration.evidence.digest != policy_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the release policy")
        if self.context.references.intended_use.evidence.digest == (
            self.context.references.identity_lineage.binding_digest
        ):
            raise ValueError("intended-use evidence cannot alias the identity lineage digest")
        _validate_unique_records(self)
        release_evidence_index(self)
        if len(canonical_json_bytes(normalized_request(self))) > M0308_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M03-08 request exceeds the public ingress limit")
        return self


class ProteinInferenceStageProvenance(FrozenModel):
    module_id: ProteinInferenceStageModuleId
    module_version: SemanticVersion
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    byte_digest: Sha256Digest
    disposition: Identifier
    generated_at: AwareDatetime
    configuration_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    bound_upstream_result_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=M0308_MAX_STAGE_UPSTREAM_DIGESTS
    )
    human_review_required: bool

    @field_validator("bound_upstream_result_digests")
    @classmethod
    def upstream_digests_are_canonical(
        cls, values: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def stage_vocabulary_is_closed(self) -> ProteinInferenceStageProvenance:
        if self.module_version != M0308_CONTRACT_VERSION:
            raise ValueError("packaged stage module version must be exactly 1.0.0")
        allowed = {
            ProteinInferenceStageModuleId.M03_01: {"conformant", "quarantined"},
            ProteinInferenceStageModuleId.M03_02: {
                "reconciled",
                "quarantined",
                "abstained",
            },
            ProteinInferenceStageModuleId.M03_03: {
                "validated",
                "quarantined",
                "abstained",
                "rejected",
            },
            ProteinInferenceStageModuleId.M03_04: {
                "qualified",
                "quarantined",
                "abstained",
                "rejected",
            },
            ProteinInferenceStageModuleId.M03_05: {
                "cleared",
                "quarantined",
                "abstained",
                "rejected",
            },
            ProteinInferenceStageModuleId.M03_06: {
                "accepted",
                "quarantined",
                "abstained",
                "rejected",
            },
            ProteinInferenceStageModuleId.M03_07: {"supported", "abstained"},
        }[self.module_id]
        if self.disposition not in allowed:
            raise ValueError("stage disposition contradicts its module")
        if len(set(self.bound_upstream_result_digests)) != len(self.bound_upstream_result_digests):
            raise ValueError("stage upstream result digests must be unique")
        return self


class ProteinInferenceReproducibilityManifest(FrozenModel):
    release_id: Identifier
    release_version: SemanticVersion
    parent_target: Literal["complex_activity"] = M0308_PARENT
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    artifacts: tuple[ProteinInferenceReleaseArtifact, ...] = Field(
        min_length=M0308_CALLER_ARTIFACT_COUNT,
        max_length=M0308_CALLER_ARTIFACT_COUNT,
    )
    stages: tuple[ProteinInferenceStageProvenance, ...] = Field(
        min_length=M0308_STAGE_COUNT,
        max_length=M0308_STAGE_COUNT,
    )
    software_versions: tuple[ProteinInferenceSoftwareVersion, ...] = Field(
        min_length=1,
        max_length=M0308_MAX_SOFTWARE_VERSIONS,
    )
    reference_versions: tuple[ProteinInferenceReferenceVersion, ...] = Field(
        min_length=1,
        max_length=M0308_MAX_REFERENCE_VERSIONS,
    )
    reproduction_evidence: ProteinInferenceReproductionEvidence
    reproduction_evidence_digest: Sha256Digest
    m0306_transformation_manifest_digest: Sha256Digest | None = None
    m0306_analysis_digest: Sha256Digest | None = None
    m0304_quality_disposition: Identifier
    m0305_artifact_disposition: Identifier
    m0306_harmonization_disposition: Identifier
    m0307_support_disposition: Identifier
    identity_resolution_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    support_route_result_digest: Sha256Digest
    policy_digest: Sha256Digest
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    fixed_mtime: Literal[0] = 0
    file_mode: Literal[420] = 0o644

    @field_validator("release_id")
    @classmethod
    def release_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "release")

    @field_validator("artifacts", "software_versions", "reference_versions")
    @classmethod
    def records_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def manifest_is_a_closed_stage_chain(  # noqa: PLR0912, PLR0915 - exact closure.
        self,
    ) -> ProteinInferenceReproducibilityManifest:
        roles = [item.role for item in self.artifacts]
        paths = [item.path.casefold() for item in self.artifacts]
        if set(roles) != set(ProteinInferenceReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("manifest requires every caller artifact role exactly once")
        if len(set(paths)) != len(paths):
            raise ValueError("manifest artifact paths must be alias-free")
        if sum(item.declared_size for item in self.artifacts) > M0308_MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("manifest caller artifacts exceed the public byte ceiling")
        metadata_ids = (
            [item.software_id for item in self.software_versions],
            [item.reference_id for item in self.reference_versions],
        )
        if any(len(set(values)) != len(values) for values in metadata_ids):
            raise ValueError("manifest software and reference identifiers must be unique")
        modules = tuple(item.module_id for item in self.stages)
        if modules != _EXPECTED_STAGE_MODULES:
            raise ValueError("manifest stages must be ordered M03-01 through M03-07")
        stage_times = tuple(item.generated_at for item in self.stages)
        if stage_times != tuple(sorted(stage_times)):
            raise ValueError("manifest stages must have nondecreasing completion times")
        if self.reproduction_evidence_digest != reproduction_evidence_digest(
            self.reproduction_evidence
        ):
            raise ValueError("manifest reproduction evidence digest is inconsistent")
        stage_by_module = {item.module_id: item for item in self.stages}
        for values in (
            [item.result_digest for item in self.stages],
            [item.request_digest for item in self.stages],
            [item.byte_digest for item in self.stages],
        ):
            if len(set(values)) != len(values):
                raise ValueError("manifest stage digests must be unique by digest role")
        role_by_module = {
            ProteinInferenceStageModuleId.M03_01: (
                ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE
            ),
            ProteinInferenceStageModuleId.M03_02: (
                ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE
            ),
            ProteinInferenceStageModuleId.M03_03: (
                ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION
            ),
            ProteinInferenceStageModuleId.M03_04: (
                ProteinInferenceReleaseArtifactRole.M03_04_QUALITY
            ),
            ProteinInferenceStageModuleId.M03_05: (
                ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION
            ),
            ProteinInferenceStageModuleId.M03_06: (
                ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION
            ),
            ProteinInferenceStageModuleId.M03_07: (
                ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE
            ),
        }
        artifact_by_role = {item.role: item for item in self.artifacts}
        if any(
            artifact_by_role[role_by_module[module]].reference.digest
            != stage_by_module[module].byte_digest
            for module in _EXPECTED_STAGE_MODULES
        ):
            raise ValueError("stage byte digests do not bind their declared caller artifacts")
        for module in _EXPECTED_STAGE_MODULES:
            stage = stage_by_module[module]
            artifact = artifact_by_role[role_by_module[module]]
            suffix = stage.request_digest.removeprefix("sha256:")
            expected_artifact_id = (
                f"route.{suffix}"
                if module is ProteinInferenceStageModuleId.M03_07
                else f"result.m03{module.value[-2:]}.{suffix}"
            )
            if artifact.reference.artifact_id != expected_artifact_id:
                raise ValueError("stage artifact identity does not bind its request digest")
        dependency_modules: dict[
            ProteinInferenceStageModuleId,
            tuple[ProteinInferenceStageModuleId, ...],
        ] = {
            ProteinInferenceStageModuleId.M03_01: (),
            ProteinInferenceStageModuleId.M03_02: (ProteinInferenceStageModuleId.M03_01,),
            ProteinInferenceStageModuleId.M03_03: (
                ProteinInferenceStageModuleId.M03_01,
                ProteinInferenceStageModuleId.M03_02,
            ),
            ProteinInferenceStageModuleId.M03_04: (
                ProteinInferenceStageModuleId.M03_01,
                ProteinInferenceStageModuleId.M03_02,
                ProteinInferenceStageModuleId.M03_03,
            ),
            ProteinInferenceStageModuleId.M03_05: (ProteinInferenceStageModuleId.M03_04,),
            ProteinInferenceStageModuleId.M03_06: (
                ProteinInferenceStageModuleId.M03_04,
                ProteinInferenceStageModuleId.M03_05,
            ),
            ProteinInferenceStageModuleId.M03_07: (
                ProteinInferenceStageModuleId.M03_04,
                ProteinInferenceStageModuleId.M03_06,
            ),
        }
        for module, dependencies in dependency_modules.items():
            expected = {stage_by_module[item].result_digest for item in dependencies}
            if set(stage_by_module[module].bound_upstream_result_digests) != expected:
                raise ValueError("stage does not bind its exact direct upstream result set")
        if {item.identity_resolution_digest for item in self.stages} != {
            self.identity_resolution_digest
        }:
            raise ValueError("release identity does not bind the complete stage lineage")
        if (
            self.support_route_result_digest
            != stage_by_module[ProteinInferenceStageModuleId.M03_07].result_digest
        ):
            raise ValueError("manifest support route digest is inconsistent")
        if (
            self.m0304_quality_disposition
            != stage_by_module[ProteinInferenceStageModuleId.M03_04].disposition
        ):
            raise ValueError("manifest quality disposition is inconsistent")
        if (
            self.m0305_artifact_disposition
            != stage_by_module[ProteinInferenceStageModuleId.M03_05].disposition
        ):
            raise ValueError("manifest artifact disposition is inconsistent")
        if (
            self.m0306_harmonization_disposition
            != stage_by_module[ProteinInferenceStageModuleId.M03_06].disposition
        ):
            raise ValueError("manifest harmonization disposition is inconsistent")
        m0306_accepted = self.m0306_harmonization_disposition == "accepted"
        m0306_digests = (
            self.m0306_transformation_manifest_digest,
            self.m0306_analysis_digest,
        )
        m0306_digests_present = tuple(value is not None for value in m0306_digests)
        if len(set(m0306_digests_present)) != 1 or (
            m0306_accepted and not all(m0306_digests_present)
        ):
            raise ValueError("M03-06 manifest digests contradict harmonization disposition")
        if (
            self.m0307_support_disposition
            != stage_by_module[ProteinInferenceStageModuleId.M03_07].disposition
        ):
            raise ValueError("manifest support disposition is inconsistent")
        return self


class ProteinInferenceSignatureVerification(FrozenModel):
    verifier_id: Identifier | None = None
    algorithm: ProteinInferenceSignatureAlgorithm
    key_id: Identifier
    statement_digest: Sha256Digest
    verified: bool
    reason_code: ProteinInferenceSignatureVerificationReason

    @field_validator("verifier_id")
    @classmethod
    def verifier_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else _opaque_identifier(value, "verifier")

    @field_validator("key_id")
    @classmethod
    def key_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "key")

    @model_validator(mode="after")
    def outcome_is_closed(self) -> ProteinInferenceSignatureVerification:
        if self.verified != (
            self.reason_code is ProteinInferenceSignatureVerificationReason.VERIFIED
        ):
            raise ValueError("signature verified state contradicts its reason")
        verifier_required = self.reason_code in {
            ProteinInferenceSignatureVerificationReason.VERIFIED,
            ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED,
        }
        if verifier_required != (self.verifier_id is not None):
            raise ValueError("signature outcome has an inconsistent verifier identifier")
        return self


class ProteinInferenceReleaseQuarantine(FrozenModel):
    code: ProteinInferenceReleaseQuarantineCode
    stage_module_id: ProteinInferenceStageModuleId | None = None
    reason_code: Identifier
    remediation_code: Identifier

    @model_validator(mode="after")
    def reason_shape_matches_code(self) -> ProteinInferenceReleaseQuarantine:
        if (self.code is ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE) != (
            self.stage_module_id is not None
        ):
            raise ValueError("only upstream quarantine reasons identify a stage module")
        if self.code is ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE:
            if self.remediation_code != "review_upstream_stage" or not (
                self.reason_code == "human_review_required"
                or self.reason_code.startswith("stage_disposition_")
            ):
                raise ValueError("upstream quarantine reason vocabulary is inconsistent")
        elif self.remediation_code != "provide_verified_signature" or self.reason_code not in {
            ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH.value,
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE.value,
            ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED.value,
        }:
            raise ValueError("signature quarantine reason vocabulary is inconsistent")
        return self


class ProteinInferenceReleaseMember(FrozenModel):
    path: CanonicalPath
    byte_size: int = Field(gt=0, le=M0308_MAX_PACKAGE_BYTES)
    digest: Sha256Digest
    role: ProteinInferenceReleaseArtifactRole | None = None

    @model_validator(mode="after")
    def member_path_and_role_are_closed(self) -> ProteinInferenceReleaseMember:
        _validate_member_path(self.path)
        generated = self.path in {M0308_MANIFEST_PATH, M0308_SIGNATURE_RECEIPT_PATH}
        if generated == (self.role is not None):
            raise ValueError("generated and caller package members require distinct role shapes")
        if self.role is not None and self.path != _ROLE_PATHS[self.role]:
            raise ValueError("package member role requires its fixed canonical path")
        return self


class ProteinInferenceReleasePackageDescriptor(FrozenModel):
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    byte_size: int = Field(gt=0, le=M0308_MAX_PACKAGE_BYTES)
    digest: Sha256Digest
    member_count: Literal[10] = M0308_ARCHIVE_MEMBER_COUNT
    members: tuple[ProteinInferenceReleaseMember, ...] = Field(
        min_length=M0308_ARCHIVE_MEMBER_COUNT,
        max_length=M0308_ARCHIVE_MEMBER_COUNT,
    )

    @field_validator("members")
    @classmethod
    def members_are_canonical(
        cls, values: tuple[ProteinInferenceReleaseMember, ...]
    ) -> tuple[ProteinInferenceReleaseMember, ...]:
        return tuple(sorted(values, key=lambda item: item.path))

    @model_validator(mode="after")
    def inventory_is_exact_and_unique(self) -> ProteinInferenceReleasePackageDescriptor:
        paths = [item.path for item in self.members]
        if len(set(paths)) != len(paths) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("package descriptor member paths must be alias-free")
        if set(paths) != {
            *(item.path for item in self.members if item.role is not None),
            M0308_MANIFEST_PATH,
            M0308_SIGNATURE_RECEIPT_PATH,
        }:
            raise ValueError("package descriptor requires both generated members")
        roles = [item.role for item in self.members if item.role is not None]
        if set(roles) != set(ProteinInferenceReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("package descriptor requires all caller artifact roles")
        payload_bytes = sum(
            _USTAR_BLOCK_BYTES
            + ((item.byte_size + _USTAR_BLOCK_BYTES - 1) // _USTAR_BLOCK_BYTES) * _USTAR_BLOCK_BYTES
            for item in self.members
        )
        unpadded_size = payload_bytes + _USTAR_END_BYTES
        expected_size = (
            (unpadded_size + _USTAR_RECORD_BYTES - 1) // _USTAR_RECORD_BYTES
        ) * _USTAR_RECORD_BYTES
        if self.byte_size != expected_size:
            raise ValueError("package descriptor byte size contradicts canonical USTAR framing")
        return self


class ProteinInferenceReleaseResult(FrozenModel):
    output_type: Literal["protein_inference_release_result"] = "protein_inference_release_result"
    release_result_id: Identifier
    result_version: Literal["1.0.0"] = M0308_CONTRACT_VERSION
    request_digest: Sha256Digest
    context_digest: Sha256Digest
    context: ExecutionContext
    policy_digest: Sha256Digest
    policy: ProteinInferenceReleasePolicy
    manifest_digest: Sha256Digest
    manifest: ProteinInferenceReproducibilityManifest
    signature: ExternalProteinInferenceSignature
    signature_verification: ProteinInferenceSignatureVerification
    result_digest: Sha256Digest
    disposition: ProteinInferenceReleaseDisposition
    package_descriptor: ProteinInferenceReleasePackageDescriptor | None = None
    quarantine_reasons: tuple[ProteinInferenceReleaseQuarantine, ...] = Field(
        default=(),
        max_length=M0308_MAX_QUARANTINE_REASONS,
    )
    parent_target: Literal["complex_activity"] = M0308_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    signs_release: Literal[False] = False
    authenticates_signer: Literal[False] = False
    establishes_release_authority: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0308_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("release_result_id")
    @classmethod
    def result_id_has_exact_shape(cls, value: Identifier) -> Identifier:
        if not re.fullmatch(r"result\.m0308\.[0-9a-f]{64}", value):
            raise ValueError("release result identifier must be an opaque M03-08 result alias")
        return value

    @field_validator("quarantine_reasons", "evidence", "limitations")
    @classmethod
    def result_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("provenance")
    @classmethod
    def provenance_is_canonical(cls, value: ProvenanceRecord) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_is_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteinInferenceReleaseResult:
        _validate_result(self)
        expected = result_payload_digest(self)
        if self.result_digest != expected:
            raise ValueError("M03-08 result digest does not match its content")
        return self


class ProteinInferenceReleaseVerification(FrozenModel):
    content_verified: bool
    authenticity_verified: bool
    verified: bool
    package_digest: Sha256Digest | None = None
    manifest_digest: Sha256Digest | None = None
    member_count: int = Field(ge=0, le=M0308_ARCHIVE_MEMBER_COUNT)
    signature_verification: ProteinInferenceSignatureVerification
    reason_code: ProteinInferencePackageVerificationReason

    @model_validator(mode="after")
    def verification_outcome_is_closed(self) -> ProteinInferenceReleaseVerification:
        if self.authenticity_verified != self.signature_verification.verified:
            raise ValueError("package authenticity contradicts signature verification")
        if self.verified != (self.content_verified and self.authenticity_verified):
            raise ValueError("package verified state contradicts its component checks")
        if self.verified != (
            self.reason_code is ProteinInferencePackageVerificationReason.VERIFIED
        ):
            raise ValueError("package verified state contradicts its reason code")
        if self.content_verified and (
            self.package_digest is None
            or self.manifest_digest is None
            or self.member_count != M0308_ARCHIVE_MEMBER_COUNT
        ):
            raise ValueError("content-verified package requires complete content receipts")
        content_failures = {
            ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH,
            ProteinInferencePackageVerificationReason.PACKAGE_INVALID,
            ProteinInferencePackageVerificationReason.INVENTORY_MISMATCH,
            ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
            ProteinInferencePackageVerificationReason.PACKAGE_NOT_CANONICAL,
            ProteinInferencePackageVerificationReason.MANIFEST_MISMATCH,
        }
        authenticity_failures = {
            ProteinInferencePackageVerificationReason.STATEMENT_MISMATCH,
            ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE,
            ProteinInferencePackageVerificationReason.VERIFIER_REJECTED,
        }
        if not self.content_verified and self.reason_code not in content_failures:
            raise ValueError("content failure requires an exact content reason")
        if not self.content_verified and (
            self.authenticity_verified
            or self.package_digest is not None
            or self.manifest_digest is not None
            or self.member_count != 0
            or self.signature_verification.verifier_id is not None
            or self.signature_verification.reason_code
            is not ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
        ):
            raise ValueError("content failure must short-circuit authenticity verification")
        if self.content_verified and not self.authenticity_verified:
            if self.reason_code not in authenticity_failures:
                raise ValueError("authenticity failure requires an exact signature reason")
            if self.reason_code.value != self.signature_verification.reason_code.value:
                raise ValueError("package and signature verification reasons disagree")
        return self


def release_evidence_index(
    request: BuildProteinInferenceReleaseRequest,
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
        (request.policy.evidence, "Pinned M03-08 release policy."),
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
    by_identity: dict[tuple[str, str], ArtifactReference] = {}
    for reference, _ in items:
        identity = (reference.artifact_id, reference.version)
        existing = by_identity.get(identity)
        if existing is not None and existing != reference:
            raise ValueError("one evidence identity cannot carry conflicting metadata")
        by_identity[identity] = reference
    unique: dict[tuple[str, str, str, str], tuple[ArtifactReference, str]] = {}
    for reference, claim in items:
        key = (
            reference.artifact_id,
            reference.version,
            reference.digest,
            reference.media_type,
        )
        existing_item = unique.get(key)
        if existing_item is None or claim < existing_item[1]:
            unique[key] = (reference, claim)
    return tuple(unique[key] for key in sorted(unique, key=canonical_json_bytes))


def expected_release_quarantine_reasons(
    manifest: ProteinInferenceReproducibilityManifest,
    verification: ProteinInferenceSignatureVerification,
) -> tuple[ProteinInferenceReleaseQuarantine, ...]:
    """Derive the exact typed reasons that prohibit release bytes."""

    accepted = {
        ProteinInferenceStageModuleId.M03_01: "conformant",
        ProteinInferenceStageModuleId.M03_02: "reconciled",
        ProteinInferenceStageModuleId.M03_03: "validated",
        ProteinInferenceStageModuleId.M03_04: "qualified",
        ProteinInferenceStageModuleId.M03_05: "cleared",
        ProteinInferenceStageModuleId.M03_06: "accepted",
        ProteinInferenceStageModuleId.M03_07: "supported",
    }
    reasons = [
        ProteinInferenceReleaseQuarantine(
            code=ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
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
            ProteinInferenceReleaseQuarantine(
                code=ProteinInferenceReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                reason_code=verification.reason_code.value,
                remediation_code="provide_verified_signature",
            )
        )
    return tuple(sorted(reasons, key=canonical_json_bytes))


def _validate_result(  # noqa: PLR0912 - explicit release closure precedence.
    result: ProteinInferenceReleaseResult,
) -> None:
    _require_authorized_context(result.context)
    if result.context_digest != context_digest(result.context):
        raise ValueError("M03-08 context digest is inconsistent")
    if result.policy_digest != policy_digest(result.policy):
        raise ValueError("M03-08 policy digest is inconsistent")
    manifest = result.manifest
    stage_times = tuple(stage.generated_at for stage in manifest.stages)
    if stage_times != tuple(sorted(stage_times)):
        raise ValueError("release stages must have nondecreasing completion times")
    if stage_times[-1] > result.signature.issued_at:
        raise ValueError("external signature cannot precede a packaged stage")
    if result.signature.issued_at > result.context.occurred_at:
        raise ValueError("external signature cannot postdate release execution")
    if result.policy.reviewed_at > result.signature.issued_at:
        raise ValueError("release policy review cannot postdate the external signature")
    if manifest.policy_digest != result.policy_digest:
        raise ValueError("release manifest does not bind the result policy")
    if (
        manifest.identity_resolution_digest
        != result.context.references.identity_lineage.binding_digest
    ):
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
        identity_resolution_digest=manifest.identity_resolution_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
        support_route_result_digest=manifest.support_route_result_digest,
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
        ProteinInferenceStageModuleId.M03_01: "conformant",
        ProteinInferenceStageModuleId.M03_02: "reconciled",
        ProteinInferenceStageModuleId.M03_03: "validated",
        ProteinInferenceStageModuleId.M03_04: "qualified",
        ProteinInferenceStageModuleId.M03_05: "cleared",
        ProteinInferenceStageModuleId.M03_06: "accepted",
        ProteinInferenceStageModuleId.M03_07: "supported",
    }
    upstream_releasable = all(
        stage.disposition == accepted[stage.module_id] and not stage.human_review_required
        for stage in manifest.stages
    )
    if not upstream_releasable and (
        verification.reason_code is not ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
    ):
        raise ValueError("unreleasable upstream chain must not invoke signature verification")
    if upstream_releasable:
        statement_matches = result.signature.claimed_statement_digest == expected_statement
        if statement_matches == (
            verification.reason_code
            is ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH
        ):
            raise ValueError("signature statement mismatch outcome is inconsistent")
        if (
            statement_matches
            and verification.reason_code
            is ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
        ):
            raise ValueError("releasable upstream chain requires a signature verification attempt")
    expected_reasons = expected_release_quarantine_reasons(manifest, verification)
    released = not expected_reasons
    if released != (result.disposition is ProteinInferenceReleaseDisposition.RELEASED):
        raise ValueError("release disposition contradicts upstream and signature closure")
    if result.quarantine_reasons != expected_reasons:
        raise ValueError("release quarantine reasons are not exactly derived")
    if released != (result.package_descriptor is not None):
        raise ValueError("only a released result may carry a package descriptor")
    if released:
        _validate_package_descriptor(result)
    _validate_result_request_digest(result)
    _validate_result_envelope(result)


def _validate_result_request_digest(result: ProteinInferenceReleaseResult) -> None:
    manifest = result.manifest
    request = BuildProteinInferenceReleaseRequest(
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
        raise ValueError("M03-08 request digest is inconsistent")


def _validate_package_descriptor(result: ProteinInferenceReleaseResult) -> None:
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
    manifest_member = members_by_path.get(M0308_MANIFEST_PATH)
    manifest_bytes = canonical_json_bytes(normalized_manifest(result.manifest))
    if manifest_member is None or (
        manifest_member.digest != result.manifest_digest
        or manifest_member.byte_size != len(manifest_bytes)
    ):
        raise ValueError("package descriptor does not bind the manifest member")
    receipt_member = members_by_path.get(M0308_SIGNATURE_RECEIPT_PATH)
    receipt_bytes = canonical_json_bytes(result.signature_verification.model_dump(mode="python"))
    if receipt_member is None or (
        receipt_member.digest != sha256_bytes(receipt_bytes)
        or receipt_member.byte_size != len(receipt_bytes)
    ):
        raise ValueError("package descriptor does not bind the verification receipt")


def _validate_result_envelope(result: ProteinInferenceReleaseResult) -> None:
    expected_support = {
        ProteinInferenceReleaseDisposition.RELEASED: (
            SupportStatus.LIMITED,
            "protein_inference_release_packaged",
            M0308_RELEASED_SUPPORT_RATIONALE,
            False,
        ),
        ProteinInferenceReleaseDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "protein_inference_release_quarantined",
            M0308_QUARANTINED_SUPPORT_RATIONALE,
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.support.rationale,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("M03-08 support envelope contradicts disposition")
    expected_limitations = {
        M0308_PACKAGE_LIMITATION_CODE: M0308_PACKAGE_LIMITATION_STATEMENT,
        M0308_AUTHORITY_LIMITATION_CODE: M0308_AUTHORITY_LIMITATION_STATEMENT,
        M0308_REPRODUCIBILITY_LIMITATION_CODE: (M0308_REPRODUCIBILITY_LIMITATION_STATEMENT),
    }
    if {item.code: item.statement for item in result.limitations} != expected_limitations:
        raise ValueError("M03-08 requires all three exact limitation statements")
    _validate_uncertainty(result.uncertainty)
    suffix = result.request_digest.removeprefix("sha256:")
    if result.release_result_id != f"result.m0308.{suffix}":
        raise ValueError("release result identifier does not bind the request digest")
    provenance = result.provenance
    if (
        provenance.activity_id != f"activity.m0308.{suffix}"
        or provenance.actor_id != result.context.actor_id
        or provenance.module_id != M0308_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or result.completed_at != result.context.occurred_at
        or provenance.configuration_digest != result.policy_digest
    ):
        raise ValueError("M03-08 provenance envelope is inconsistent")
    request = BuildProteinInferenceReleaseRequest(
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
        raise ValueError("M03-08 provenance must contain the exact unique input digest set")
    _validate_controls(result)
    expected_evidence = {
        (
            reference.artifact_id,
            reference.version,
            reference.digest,
            reference.media_type,
        ): (reference, "evidence", claim)
        for reference, claim in release_evidence_index(request)
    }
    actual_evidence = {
        (
            item.reference.artifact_id,
            item.reference.version,
            item.reference.digest,
            item.reference.media_type,
        ): (item.reference, item.role, item.claim)
        for item in result.evidence
    }
    if len(actual_evidence) != len(result.evidence) or actual_evidence != expected_evidence:
        raise ValueError("M03-08 evidence index or claims are inconsistent")


def release_provenance_input_digests(  # noqa: PLR0913 - exact digest receipt.
    request: BuildProteinInferenceReleaseRequest,
    manifest: ProteinInferenceReproducibilityManifest,
    *,
    request_digest: Sha256Digest,
    context_digest: Sha256Digest,
    policy_digest: Sha256Digest,
    manifest_digest: Sha256Digest,
    controls: tuple[ControlDecisionRecord, ...],
) -> set[Sha256Digest]:
    digests = {
        request_digest,
        context_digest,
        policy_digest,
        manifest_digest,
        request.signature.claimed_statement_digest,
        manifest.reproduction_evidence_digest,
        manifest.identity_resolution_digest,
        manifest.intended_use_evidence_digest,
        manifest.support_route_result_digest,
        *(stage.result_digest for stage in manifest.stages),
        *(stage.request_digest for stage in manifest.stages),
        *(stage.configuration_digest for stage in manifest.stages),
        *(stage.byte_digest for stage in manifest.stages),
        *(item.reference.digest for item in request.artifacts),
        *(item.build_digest for item in request.software_versions),
        *(item.digest for item in request.reference_versions),
        *(reference.digest for reference, _ in release_evidence_index(request)),
        *(item.evidence_digest for item in controls),
    }
    for optional_digest in (
        manifest.m0306_transformation_manifest_digest,
        manifest.m0306_analysis_digest,
        request.supersedes_result_digest,
    ):
        if optional_digest is not None:
            digests.add(optional_digest)
    return digests


def _validate_controls(result: ProteinInferenceReleaseResult) -> None:
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
            result.manifest.identity_resolution_digest,
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
        raise ValueError("M03-08 control decisions do not match the embedded context")
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
        raise ValueError("M03-08 consent provenance is inconsistent")


def _validate_uncertainty(uncertainty: UncertaintyProfile) -> None:
    for dimension, rationale in M0308_UNCERTAINTY_RATIONALES.items():
        estimate = getattr(uncertainty, dimension)
        if (
            estimate.state is not EstimateState.NOT_ESTIMABLE
            or estimate.probability is not None
            or estimate.rationale != rationale
        ):
            raise ValueError("M03-08 uncertainty must remain deterministic and not estimable")
    if uncertainty.sensitivity_notes != M0308_SENSITIVITY_NOTES:
        raise ValueError("M03-08 uncertainty sensitivity notes are inconsistent")


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M03-08")
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
        raise ValueError("upstream controls do not authorize M03-08")


def _validate_context_opacity(context: ExecutionContext) -> None:
    _opaque_identifier(context.request_id, "request")
    _opaque_identifier(context.actor_id, "actor")
    refs = context.references
    controls = (
        refs.approved_configuration,
        refs.identity_lineage,
        refs.provenance,
        refs.consent,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    for control in controls:
        _opaque_identifier(control.decision_id, "decision")
        _owned_evidence(control.evidence)


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


def _validate_unique_records(request: BuildProteinInferenceReleaseRequest) -> None:
    groups = (
        [item.software_id for item in request.software_versions],
        [item.reference_id for item in request.reference_versions],
    )
    if any(len(set(values)) != len(values) for values in groups):
        raise ValueError("release metadata identifiers must be unique")


def _named_reproduction_references(
    evidence: ProteinInferenceReproductionEvidence,
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
    evidence: ProteinInferenceReproductionEvidence,
) -> tuple[ArtifactReference, ...]:
    return tuple(reference for _, reference in _named_reproduction_references(evidence))


__all__ = [
    "M0308_ARCHIVE_MEMBER_COUNT",
    "M0308_AUTHORITY_LIMITATION_CODE",
    "M0308_AUTHORITY_LIMITATION_STATEMENT",
    "M0308_CALLER_ARTIFACT_COUNT",
    "M0308_CONTRACT_VERSION",
    "M0308_MANIFEST_PATH",
    "M0308_MAX_ARTIFACT_BYTES",
    "M0308_MAX_CANONICAL_REQUEST_BYTES",
    "M0308_MAX_EVIDENCE",
    "M0308_MAX_PACKAGE_BYTES",
    "M0308_MAX_QUARANTINE_REASONS",
    "M0308_MAX_REFERENCE_VERSIONS",
    "M0308_MAX_SIGNATURE_ALGORITHMS",
    "M0308_MAX_SIGNATURE_VALUE_CHARS",
    "M0308_MAX_SOFTWARE_VERSIONS",
    "M0308_MAX_STAGE_UPSTREAM_DIGESTS",
    "M0308_MAX_TOTAL_ARTIFACT_BYTES",
    "M0308_MAX_VERIFIER_IDS",
    "M0308_MODULE_ID",
    "M0308_OPERATION",
    "M0308_PACKAGE_LIMITATION_CODE",
    "M0308_PACKAGE_LIMITATION_STATEMENT",
    "M0308_PARENT",
    "M0308_QUARANTINED_SUPPORT_RATIONALE",
    "M0308_RELEASED_SUPPORT_RATIONALE",
    "M0308_REPRODUCIBILITY_LIMITATION_CODE",
    "M0308_REPRODUCIBILITY_LIMITATION_STATEMENT",
    "M0308_SENSITIVITY_NOTES",
    "M0308_SIGNATURE_RECEIPT_PATH",
    "M0308_STAGE_COUNT",
    "M0308_UNCERTAINTY_RATIONALES",
    "BuildProteinInferenceReleaseRequest",
    "ExternalProteinInferenceSignature",
    "ProteinInferencePackageVerificationReason",
    "ProteinInferenceParentComplexActivityReceipt",
    "ProteinInferenceReferenceVersion",
    "ProteinInferenceReleaseArtifact",
    "ProteinInferenceReleaseArtifactRole",
    "ProteinInferenceReleaseDisposition",
    "ProteinInferenceReleaseIdentifierNamespace",
    "ProteinInferenceReleaseMember",
    "ProteinInferenceReleasePackageDescriptor",
    "ProteinInferenceReleasePolicy",
    "ProteinInferenceReleaseQuarantine",
    "ProteinInferenceReleaseQuarantineCode",
    "ProteinInferenceReleaseResult",
    "ProteinInferenceReleaseVerification",
    "ProteinInferenceReproducibilityManifest",
    "ProteinInferenceReproductionEvidence",
    "ProteinInferenceSignatureAlgorithm",
    "ProteinInferenceSignatureVerification",
    "ProteinInferenceSignatureVerificationReason",
    "ProteinInferenceSoftwareVersion",
    "ProteinInferenceStageModuleId",
    "ProteinInferenceStageProvenance",
    "expected_release_quarantine_reasons",
    "opaque_release_identifier",
    "release_evidence_index",
    "release_provenance_input_digests",
]
