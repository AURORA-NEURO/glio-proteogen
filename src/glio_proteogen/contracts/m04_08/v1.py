"""Strict M04-08 owned contracts for deterministic proteoform release packaging."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m04_07.v1 import (
    M0407_OUTPUT_MEDIA_TYPE,
    ProteoformSupportDisposition,
)
from glio_proteogen.contracts.m04_08.canonical import (
    canonical_request_digest,
    context_digest,
    manifest_digest,
    normalized_request,
    policy_digest,
    reproduction_evidence_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
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
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0408_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-08"
M0408_CONTRACT_VERSION: Final = "1.0.0"
M0408_OPERATION: Final = "package_proteoform_release"
M0408_PARENT: Final = "protein_rna_discordance"
M0408_CALLER_ARTIFACT_COUNT: Final = 8
M0408_STAGE_COUNT: Final = 7
M0408_ARCHIVE_MEMBER_COUNT: Final = 10
M0408_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0408_MAX_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
M0408_MAX_TOTAL_ARTIFACT_BYTES: Final = 64 * 1024 * 1024
M0408_MAX_PACKAGE_BYTES: Final = 72 * 1024 * 1024
M0408_MAX_SOFTWARE_VERSIONS: Final = 64
M0408_MAX_REFERENCE_VERSIONS: Final = 64
M0408_MAX_SIGNATURE_ALGORITHMS: Final = 16
M0408_MAX_VERIFIER_IDS: Final = 16
M0408_MAX_SIGNATURE_VALUE_CHARS: Final = 16_384
M0408_MAX_STAGE_UPSTREAM_DIGESTS: Final = 3
M0408_MAX_QUARANTINE_REASONS: Final = 8
M0408_MAX_EVIDENCE: Final = 192
M0408_MANIFEST_PATH: Final = "META-INF/glio-proteogen-m04-08/reproducibility-manifest.json"
M0408_SIGNATURE_RECEIPT_PATH: Final = "META-INF/glio-proteogen-m04-08/signature-verification.json"
M0408_PACKAGE_LIMITATION_CODE: Final = "deterministic_proteoform_packaging_only"
M0408_AUTHORITY_LIMITATION_CODE: Final = "external_signature_authority_unverified"
M0408_REPRODUCIBILITY_LIMITATION_CODE: Final = "scientific_reproducibility_not_validated"
M0408_PACKAGE_LIMITATION_STATEMENT: Final = (
    "M04-08 packages one closed proteoform/isoform chain without changing or interpreting "
    "its scientific content."
)
M0408_AUTHORITY_LIMITATION_STATEMENT: Final = (
    "Signature verification records one injected verifier outcome and does not establish "
    "signer identity, key custody, certificate validity, or release authority."
)
M0408_REPRODUCIBILITY_LIMITATION_STATEMENT: Final = (
    "The package records exact-byte reproduction inputs but does not validate scientific "
    "reproducibility or the external evidence issuers."
)
M0408_RELEASED_SUPPORT_RATIONALE: Final = (
    "The authorized proteoform/isoform chain and injected signature verification satisfied "
    "the pinned deterministic release profile."
)
M0408_QUARANTINED_SUPPORT_RATIONALE: Final = (
    "The proteoform/isoform release was withheld because an upstream stage or signature "
    "verification did not satisfy the pinned release profile."
)
M0408_SENSITIVITY_NOTES: Final = (
    "No calibrated probability is produced by deterministic release packaging.",
    "Scientific, cryptographic, and release-authority validity remain external.",
)
M0408_UNCERTAINTY_RATIONALES: Final[dict[str, str]] = {
    "measurement": "Measurement uncertainty is preserved in packaged upstream results.",
    "sampling": "Sampling uncertainty is preserved in packaged upstream results.",
    "parameter": "Packaging has no estimated scientific parameter uncertainty.",
    "model_form": "M04-08 performs no scientific model inference.",
    "identification": "Identification uncertainty is preserved in packaged upstream results.",
    "support": "Support uncertainty is preserved in the packaged M04-07 result.",
    "transport": "External verifier, evidence, and authority issuers are not authenticated.",
}

_USTAR_NAME_BYTES: Final = 100
_USTAR_PREFIX_BYTES: Final = 155
_USTAR_PATH_BYTES: Final = 255
_USTAR_BLOCK_BYTES: Final = 512
_USTAR_END_BYTES: Final = 2 * _USTAR_BLOCK_BYTES
_USTAR_RECORD_BYTES: Final = 10_240
_OPAQUE_IDENTIFIER: Final = re.compile(r"^[a-z][a-z0-9_]*\.[0-9a-f]{64}$")
_OWNED_MEDIA_TYPE: Final = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class M0408DependencyUnavailableError(RuntimeError):
    """Raised until the exact frozen M04-07 contract adapter is installed."""


class ProteoformStageModuleId(StrEnum):
    M04_01 = "GLIO-PROTEOGEN-M04-01"
    M04_02 = "GLIO-PROTEOGEN-M04-02"
    M04_03 = "GLIO-PROTEOGEN-M04-03"
    M04_04 = "GLIO-PROTEOGEN-M04-04"
    M04_05 = "GLIO-PROTEOGEN-M04-05"
    M04_06 = "GLIO-PROTEOGEN-M04-06"
    M04_07 = "GLIO-PROTEOGEN-M04-07"


_EXPECTED_STAGE_MODULES: Final = tuple(ProteoformStageModuleId)

CanonicalPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/-]+$"),
]
SignatureValue = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=M0408_MAX_SIGNATURE_VALUE_CHARS,
        pattern=r"^[A-Za-z0-9+/=_-]+$",
    ),
]


class ProteoformReleaseArtifactRole(StrEnum):
    PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF = "parent_protein_rna_discordance_handoff"
    M04_01_PROTOCOL_CONFORMANCE = "m04_01_protocol_conformance"
    M04_02_IDENTITY_LINEAGE = "m04_02_identity_lineage"
    M04_03_RAW_INGESTION = "m04_03_raw_ingestion"
    M04_04_QUALITY = "m04_04_quality"
    M04_05_ARTIFACT_DETECTION = "m04_05_artifact_detection"
    M04_06_HARMONIZATION = "m04_06_harmonization"
    M04_07_UPSTREAM_RESULT = "m04_07_upstream_result"


class ProteoformSignatureAlgorithm(StrEnum):
    ED25519 = "ed25519"
    ECDSA_P256_SHA256 = "ecdsa_p256_sha256"
    RSA_PSS_SHA256 = "rsa_pss_sha256"


class ProteoformReleaseDisposition(StrEnum):
    RELEASED = "released"
    QUARANTINED = "quarantined"


class ProteoformSignatureVerificationReason(StrEnum):
    VERIFIED = "verified"
    NOT_ATTEMPTED = "not_attempted"
    STATEMENT_MISMATCH = "statement_mismatch"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFIER_REJECTED = "verifier_rejected"


class ProteoformReleaseQuarantineCode(StrEnum):
    UPSTREAM_NOT_RELEASABLE = "upstream_not_releasable"
    SIGNATURE_UNVERIFIED = "signature_unverified"


class ProteoformPackageVerificationReason(StrEnum):
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


_ROLE_PATHS: Final[dict[ProteoformReleaseArtifactRole, str]] = {
    ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF: (
        "parent/protein-rna-discordance-handoff.json"
    ),
    ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE: (
        "stages/m04-01-protocol-conformance.json"
    ),
    ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE: ("stages/m04-02-identity-lineage.json"),
    ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION: "stages/m04-03-raw-ingestion.json",
    ProteoformReleaseArtifactRole.M04_04_QUALITY: "stages/m04-04-quality.json",
    ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION: (
        "stages/m04-05-artifact-detection.json"
    ),
    ProteoformReleaseArtifactRole.M04_06_HARMONIZATION: ("stages/m04-06-harmonization.json"),
    ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT: "stages/m04-07-upstream-result.json",
}

_KNOWN_ARTIFACT_SHAPES: Final[dict[ProteoformReleaseArtifactRole, tuple[re.Pattern[str], str]]] = {
    ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF: (
        re.compile(r"^parent\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.protein-rna-discordance-handoff+json",
    ),
    ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE: (
        re.compile(r"^result\.m0401\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-01+json",
    ),
    ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE: (
        re.compile(r"^result\.m0402\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-02+json",
    ),
    ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION: (
        re.compile(r"^result\.m0403\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-03+json",
    ),
    ProteoformReleaseArtifactRole.M04_04_QUALITY: (
        re.compile(r"^result\.m0404\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-04+json",
    ),
    ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION: (
        re.compile(r"^result\.m0405\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-05+json",
    ),
    ProteoformReleaseArtifactRole.M04_06_HARMONIZATION: (
        re.compile(r"^result\.m0406\.[0-9a-f]{64}$"),
        "application/vnd.glio-proteogen.m04-06+json",
    ),
}


@dataclass(frozen=True, slots=True)
class _M0407ContractBinding:
    artifact_id_pattern: re.Pattern[str]
    artifact_id_prefix: str
    media_type: str
    dispositions: frozenset[str]
    releasable_dispositions: frozenset[str]
    direct_upstream_modules: tuple[ProteoformStageModuleId, ...]


_M0407_BINDING: _M0407ContractBinding | None = None


def _bind_m0407_contract(  # noqa: PLR0913 - exact frozen dependency adapter.
    *,
    artifact_id_pattern: str,
    artifact_id_prefix: str,
    media_type: str,
    dispositions: frozenset[str],
    releasable_dispositions: frozenset[str],
    direct_upstream_modules: tuple[ProteoformStageModuleId, ...],
) -> None:
    """Install the exact final M04-07 ABI once; never guess or replace it."""

    global _M0407_BINDING  # noqa: PLW0603 - one immutable dependency freeze point.
    if _OWNED_MEDIA_TYPE.fullmatch(media_type) is None:
        raise ValueError("M04-07 result media type must be exact lowercase type/subtype syntax")
    if re.fullmatch(r"[a-z][a-z0-9_.]*\.", artifact_id_prefix) is None:
        raise ValueError("M04-07 result identifier prefix is not canonical")
    if not dispositions or not releasable_dispositions <= dispositions:
        raise ValueError("M04-07 disposition binding is not closed")
    candidate = _M0407ContractBinding(
        artifact_id_pattern=re.compile(artifact_id_pattern),
        artifact_id_prefix=artifact_id_prefix,
        media_type=media_type,
        dispositions=dispositions,
        releasable_dispositions=releasable_dispositions,
        direct_upstream_modules=direct_upstream_modules,
    )
    if _M0407_BINDING is not None and candidate != _M0407_BINDING:
        raise RuntimeError("M04-07 contract binding is immutable once installed")
    _M0407_BINDING = candidate


def _m0407_binding() -> _M0407ContractBinding:
    if _M0407_BINDING is None:
        raise M0408DependencyUnavailableError(
            "M04-08 executable validation awaits the frozen M04-07 public ABI"
        )
    return _M0407_BINDING


# The public M04-07 handoff is the sole dependency freeze point.  M04-08 never
# guesses this ABI: its identifier, media type, disposition vocabulary, and
# direct prerequisite set are copied from the published M04-07 contract.
_bind_m0407_contract(
    artifact_id_pattern=r"^route\.[0-9a-f]{64}$",
    artifact_id_prefix="route.",
    media_type=M0407_OUTPUT_MEDIA_TYPE,
    dispositions=frozenset(item.value for item in ProteoformSupportDisposition),
    releasable_dispositions=frozenset({ProteoformSupportDisposition.SUPPORTED.value}),
    direct_upstream_modules=(
        ProteoformStageModuleId.M04_04,
        ProteoformStageModuleId.M04_06,
    ),
)


def opaque_release_identifier(namespace: str, value: object) -> Identifier:
    if re.fullmatch(r"[a-z][a-z0-9_]*", namespace) is None:
        raise ValueError("opaque identifier namespace is not canonical")
    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _opaque_identifier(value: Identifier, namespace: str) -> Identifier:
    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {namespace} digest alias")
    return value


def _owned_evidence(value: ArtifactReference) -> ArtifactReference:
    _opaque_identifier(value.artifact_id, "evidence")
    if _OWNED_MEDIA_TYPE.fullmatch(value.media_type) is None:
        raise ValueError("M04-08 evidence media type must use lowercase type/subtype syntax")
    return value


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
    prefix = "" if len(parts) == 1 else "/".join(parts[:-1])
    if len(path.name.encode("ascii")) > _USTAR_NAME_BYTES or len(prefix.encode("ascii")) > (
        _USTAR_PREFIX_BYTES
    ):
        raise ValueError("release member path is not representable in USTAR")


class ProteoformReleaseArtifact(FrozenModel):
    path: CanonicalPath
    role: ProteoformReleaseArtifactRole
    reference: ArtifactReference
    declared_size: int = Field(gt=0, le=M0408_MAX_ARTIFACT_BYTES)

    @model_validator(mode="after")
    def path_and_reference_are_closed(self) -> ProteoformReleaseArtifact:
        _validate_member_path(self.path)
        if self.path.casefold().startswith("meta-inf/glio-proteogen-m04-08/"):
            raise ValueError("caller artifact cannot use the reserved M04-08 namespace")
        if self.path != _ROLE_PATHS[self.role]:
            raise ValueError("release artifact role requires its fixed canonical path")
        if self.role is ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT:
            binding = _m0407_binding()
            pattern, media_type = binding.artifact_id_pattern, binding.media_type
        else:
            pattern, media_type = _KNOWN_ARTIFACT_SHAPES[self.role]
        if (
            pattern.fullmatch(self.reference.artifact_id) is None
            or self.reference.media_type != media_type
        ):
            raise ValueError("release artifact reference contradicts its fixed role")
        return self


class ProteoformParentDiscordanceReceipt(FrozenModel):
    """Caller-owned parent receipt; M04-08 makes no discordance inference."""

    parent_target: Literal["protein_rna_discordance"] = M0408_PARENT
    identity_resolution_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    terminal_routing_result_digest: Sha256Digest
    emits_protein_rna_discordance: Literal[False] = False


class ProteoformSoftwareVersion(FrozenModel):
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


class ProteoformReferenceVersion(FrozenModel):
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


class ProteoformReproductionEvidence(FrozenModel):
    environment_lock: ArtifactReference
    build_recipe: ArtifactReference
    locked_tests: ArtifactReference
    benchmark: ArtifactReference
    traceability: ArtifactReference
    risk_control_verification: ArtifactReference
    data_model_reference_manifest: ArtifactReference
    reviewer_signoff: ArtifactReference
    rollback: ArtifactReference

    @field_validator(
        "environment_lock",
        "build_recipe",
        "locked_tests",
        "benchmark",
        "traceability",
        "risk_control_verification",
        "data_model_reference_manifest",
        "reviewer_signoff",
        "rollback",
    )
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)

    @model_validator(mode="after")
    def evidence_items_are_distinct(self) -> ProteoformReproductionEvidence:
        references = tuple(getattr(self, name) for name in self.__class__.model_fields)
        if len({item.digest for item in references}) != len(references):
            raise ValueError("reproduction evidence digests must be unique")
        return self


class ProteoformReleasePolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    max_total_bytes: int = Field(
        default=M0408_MAX_TOTAL_ARTIFACT_BYTES, gt=0, le=M0408_MAX_TOTAL_ARTIFACT_BYTES
    )
    max_artifact_bytes: int = Field(
        default=M0408_MAX_ARTIFACT_BYTES, gt=0, le=M0408_MAX_ARTIFACT_BYTES
    )
    allowed_signature_algorithms: tuple[ProteoformSignatureAlgorithm, ...] = Field(
        min_length=1, max_length=M0408_MAX_SIGNATURE_ALGORITHMS
    )
    allowed_verifier_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0408_MAX_VERIFIER_IDS
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
        cls, values: tuple[ProteoformSignatureAlgorithm, ...]
    ) -> tuple[ProteoformSignatureAlgorithm, ...]:
        return tuple(sorted(values, key=str))

    @field_validator("allowed_verifier_ids")
    @classmethod
    def verifier_ids_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
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
    def policy_sets_are_unique(self) -> ProteoformReleasePolicy:
        for values in (self.allowed_signature_algorithms, self.allowed_verifier_ids):
            if len(set(values)) != len(values):
                raise ValueError("release policy allowlists must be unique")
        return self


class ExternalProteoformSignature(FrozenModel):
    signer_id: Identifier
    key_id: Identifier
    algorithm: ProteoformSignatureAlgorithm
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


class BuildProteoformReleaseRequest(FrozenModel):
    operation: Literal["package_proteoform_release"] = M0408_OPERATION
    contract_version: Literal["1.0.0"] = M0408_CONTRACT_VERSION
    context: ExecutionContext
    release_id: Identifier
    release_version: SemanticVersion
    artifacts: tuple[ProteoformReleaseArtifact, ...] = Field(
        min_length=M0408_CALLER_ARTIFACT_COUNT,
        max_length=M0408_CALLER_ARTIFACT_COUNT,
    )
    software_versions: tuple[ProteoformSoftwareVersion, ...] = Field(
        min_length=1, max_length=M0408_MAX_SOFTWARE_VERSIONS
    )
    reference_versions: tuple[ProteoformReferenceVersion, ...] = Field(
        min_length=1, max_length=M0408_MAX_REFERENCE_VERSIONS
    )
    reproduction_evidence: ProteoformReproductionEvidence
    policy: ProteoformReleasePolicy
    signature: ExternalProteoformSignature
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("release_id")
    @classmethod
    def release_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "release")

    @field_validator("artifacts", "software_versions", "reference_versions")
    @classmethod
    def records_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def request_is_authorized_closed_and_bounded(  # noqa: PLR0912 - explicit closure.
        self,
    ) -> BuildProteoformReleaseRequest:
        _require_authorized_context(self.context)
        _validate_context_opacity(self.context)
        if self.context.references.identity_lineage.binding_digest is None:
            raise ValueError("M04-08 release requires an exact identity lineage binding")
        roles = [item.role for item in self.artifacts]
        paths = [item.path for item in self.artifacts]
        if set(roles) != set(ProteoformReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("release request requires every caller artifact role exactly once")
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
            raise ValueError("intended-use evidence cannot alias identity lineage")
        if len({item.software_id for item in self.software_versions}) != len(
            self.software_versions
        ):
            raise ValueError("release software identifiers must be unique")
        if len({item.reference_id for item in self.reference_versions}) != len(
            self.reference_versions
        ):
            raise ValueError("release reference identifiers must be unique")
        if len(canonical_json_bytes(normalized_request(self))) > M0408_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M04-08 request exceeds the public ingress limit")
        return self


_KNOWN_STAGE_DISPOSITIONS: Final[dict[ProteoformStageModuleId, frozenset[str]]] = {
    ProteoformStageModuleId.M04_01: frozenset({"conformant", "quarantined"}),
    ProteoformStageModuleId.M04_02: frozenset({"reconciled", "quarantined", "abstained"}),
    ProteoformStageModuleId.M04_03: frozenset({"validated", "quarantined", "abstained"}),
    ProteoformStageModuleId.M04_04: frozenset({"qualified", "quarantined", "abstained"}),
    ProteoformStageModuleId.M04_05: frozenset({"cleared", "quarantined", "abstained"}),
    ProteoformStageModuleId.M04_06: frozenset({"accepted", "quarantined", "abstained"}),
}
_KNOWN_RELEASABLE_DISPOSITIONS: Final[dict[ProteoformStageModuleId, frozenset[str]]] = {
    ProteoformStageModuleId.M04_01: frozenset({"conformant"}),
    ProteoformStageModuleId.M04_02: frozenset({"reconciled"}),
    ProteoformStageModuleId.M04_03: frozenset({"validated"}),
    ProteoformStageModuleId.M04_04: frozenset({"qualified"}),
    ProteoformStageModuleId.M04_05: frozenset({"cleared"}),
    ProteoformStageModuleId.M04_06: frozenset({"accepted"}),
}


class ProteoformStageProvenance(FrozenModel):
    module_id: ProteoformStageModuleId
    module_version: SemanticVersion
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    byte_digest: Sha256Digest
    disposition: Identifier
    generated_at: AwareDatetime
    configuration_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    bound_upstream_result_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=M0408_MAX_STAGE_UPSTREAM_DIGESTS
    )
    human_review_required: bool

    @field_validator("bound_upstream_result_digests")
    @classmethod
    def upstream_digests_are_canonical(
        cls, values: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def vocabulary_is_closed(self) -> ProteoformStageProvenance:
        if self.module_version != M0408_CONTRACT_VERSION:
            raise ValueError("packaged stage module version must be exactly 1.0.0")
        allowed = (
            _m0407_binding().dispositions
            if self.module_id is ProteoformStageModuleId.M04_07
            else _KNOWN_STAGE_DISPOSITIONS[self.module_id]
        )
        if self.disposition not in allowed:
            raise ValueError("stage disposition contradicts its module")
        if len(set(self.bound_upstream_result_digests)) != len(self.bound_upstream_result_digests):
            raise ValueError("stage upstream result digests must be unique")
        return self


class ProteoformReproducibilityManifest(FrozenModel):
    release_id: Identifier
    release_version: SemanticVersion
    parent_target: Literal["protein_rna_discordance"] = M0408_PARENT
    reproduction_mode: Literal["exact_bytes"] = "exact_bytes"
    artifacts: tuple[ProteoformReleaseArtifact, ...] = Field(
        min_length=M0408_CALLER_ARTIFACT_COUNT,
        max_length=M0408_CALLER_ARTIFACT_COUNT,
    )
    stages: tuple[ProteoformStageProvenance, ...] = Field(
        min_length=M0408_STAGE_COUNT,
        max_length=M0408_STAGE_COUNT,
    )
    software_versions: tuple[ProteoformSoftwareVersion, ...] = Field(
        min_length=1, max_length=M0408_MAX_SOFTWARE_VERSIONS
    )
    reference_versions: tuple[ProteoformReferenceVersion, ...] = Field(
        min_length=1, max_length=M0408_MAX_REFERENCE_VERSIONS
    )
    reproduction_evidence: ProteoformReproductionEvidence
    reproduction_evidence_digest: Sha256Digest
    m0406_transformation_manifest_digest: Sha256Digest | None = None
    m0406_analysis_digest: Sha256Digest | None = None
    m0404_quality_disposition: Identifier
    m0405_artifact_disposition: Identifier
    m0406_harmonization_disposition: Identifier
    terminal_routing_disposition: Identifier
    identity_resolution_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    terminal_routing_result_digest: Sha256Digest
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
    def manifest_is_owned_and_closed(  # noqa: PLR0912 - explicit stage closure.
        self,
    ) -> ProteoformReproducibilityManifest:
        binding = _m0407_binding()
        roles = [item.role for item in self.artifacts]
        if set(roles) != set(ProteoformReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("manifest requires every caller artifact role exactly once")
        modules = tuple(item.module_id for item in self.stages)
        if modules != _EXPECTED_STAGE_MODULES:
            raise ValueError("manifest stages must be ordered M04-01 through M04-07")
        if tuple(item.generated_at for item in self.stages) != tuple(
            sorted(item.generated_at for item in self.stages)
        ):
            raise ValueError("manifest stages must have nondecreasing completion times")
        if self.reproduction_evidence_digest != reproduction_evidence_digest(
            self.reproduction_evidence
        ):
            raise ValueError("manifest reproduction evidence digest is inconsistent")
        stage_by_module = {item.module_id: item for item in self.stages}
        role_by_module = {
            ProteoformStageModuleId.M04_01: (
                ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE
            ),
            ProteoformStageModuleId.M04_02: ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE,
            ProteoformStageModuleId.M04_03: ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION,
            ProteoformStageModuleId.M04_04: ProteoformReleaseArtifactRole.M04_04_QUALITY,
            ProteoformStageModuleId.M04_05: ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION,
            ProteoformStageModuleId.M04_06: ProteoformReleaseArtifactRole.M04_06_HARMONIZATION,
            ProteoformStageModuleId.M04_07: ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT,
        }
        artifact_by_role = {item.role: item for item in self.artifacts}
        for module in _EXPECTED_STAGE_MODULES:
            stage = stage_by_module[module]
            artifact = artifact_by_role[role_by_module[module]]
            if artifact.reference.digest != stage.byte_digest:
                raise ValueError("stage byte digest does not bind its caller artifact")
            prefix = (
                binding.artifact_id_prefix
                if module is ProteoformStageModuleId.M04_07
                else f"result.m04{module.value[-2:]}."
            )
            expected_id = f"{prefix}{stage.request_digest.removeprefix('sha256:')}"
            if artifact.reference.artifact_id != expected_id:
                raise ValueError("stage artifact identity does not bind its request digest")
        dependencies = {
            ProteoformStageModuleId.M04_01: (),
            ProteoformStageModuleId.M04_02: (ProteoformStageModuleId.M04_01,),
            ProteoformStageModuleId.M04_03: (
                ProteoformStageModuleId.M04_01,
                ProteoformStageModuleId.M04_02,
            ),
            ProteoformStageModuleId.M04_04: (
                ProteoformStageModuleId.M04_01,
                ProteoformStageModuleId.M04_02,
                ProteoformStageModuleId.M04_03,
            ),
            ProteoformStageModuleId.M04_05: (ProteoformStageModuleId.M04_04,),
            ProteoformStageModuleId.M04_06: (
                ProteoformStageModuleId.M04_04,
                ProteoformStageModuleId.M04_05,
            ),
            ProteoformStageModuleId.M04_07: binding.direct_upstream_modules,
        }
        for module, upstream_modules in dependencies.items():
            expected = {stage_by_module[item].result_digest for item in upstream_modules}
            if set(stage_by_module[module].bound_upstream_result_digests) != expected:
                raise ValueError("stage does not bind its exact direct upstream result set")
        if {item.identity_resolution_digest for item in self.stages} != {
            self.identity_resolution_digest
        }:
            raise ValueError("release identity does not bind the complete stage lineage")
        if (
            self.terminal_routing_result_digest
            != stage_by_module[ProteoformStageModuleId.M04_07].result_digest
        ):
            raise ValueError("terminal routing result digest is inconsistent")
        expected_dispositions = (
            (ProteoformStageModuleId.M04_04, self.m0404_quality_disposition),
            (ProteoformStageModuleId.M04_05, self.m0405_artifact_disposition),
            (ProteoformStageModuleId.M04_06, self.m0406_harmonization_disposition),
            (ProteoformStageModuleId.M04_07, self.terminal_routing_disposition),
        )
        if any(
            stage_by_module[module].disposition != value for module, value in expected_dispositions
        ):
            raise ValueError("manifest stage dispositions are inconsistent")
        m0406_digests = (
            self.m0406_transformation_manifest_digest,
            self.m0406_analysis_digest,
        )
        if self.m0406_harmonization_disposition == "accepted":
            if any(value is None for value in m0406_digests):
                raise ValueError("accepted M04-06 result requires both owned output digests")
        elif any(value is not None for value in m0406_digests):
            raise ValueError("non-accepted M04-06 result cannot claim owned output digests")
        return self


class ProteoformSignatureVerification(FrozenModel):
    verifier_id: Identifier | None = None
    algorithm: ProteoformSignatureAlgorithm
    key_id: Identifier
    statement_digest: Sha256Digest
    verified: bool
    reason_code: ProteoformSignatureVerificationReason

    @field_validator("verifier_id")
    @classmethod
    def verifier_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else _opaque_identifier(value, "verifier")

    @field_validator("key_id")
    @classmethod
    def key_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "key")

    @model_validator(mode="after")
    def outcome_is_closed(self) -> ProteoformSignatureVerification:
        if self.verified != (self.reason_code is ProteoformSignatureVerificationReason.VERIFIED):
            raise ValueError("signature verified state contradicts its reason")
        verifier_required = self.reason_code in {
            ProteoformSignatureVerificationReason.VERIFIED,
            ProteoformSignatureVerificationReason.VERIFIER_REJECTED,
        }
        if verifier_required != (self.verifier_id is not None):
            raise ValueError("signature outcome has an inconsistent verifier identifier")
        return self


class ProteoformReleaseQuarantine(FrozenModel):
    code: ProteoformReleaseQuarantineCode
    stage_module_id: ProteoformStageModuleId | None = None
    reason_code: Identifier
    remediation_code: Identifier

    @model_validator(mode="after")
    def reason_shape_matches_code(self) -> ProteoformReleaseQuarantine:
        upstream = self.code is ProteoformReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE
        if upstream != (self.stage_module_id is not None):
            raise ValueError("only upstream quarantine reasons identify a stage module")
        return self


class ProteoformReleaseMember(FrozenModel):
    path: CanonicalPath
    byte_size: int = Field(gt=0, le=M0408_MAX_PACKAGE_BYTES)
    digest: Sha256Digest
    role: ProteoformReleaseArtifactRole | None = None

    @model_validator(mode="after")
    def member_path_and_role_are_closed(self) -> ProteoformReleaseMember:
        _validate_member_path(self.path)
        generated = self.path in {M0408_MANIFEST_PATH, M0408_SIGNATURE_RECEIPT_PATH}
        if generated == (self.role is not None):
            raise ValueError("generated and caller package members require distinct role shapes")
        if self.role is not None and self.path != _ROLE_PATHS[self.role]:
            raise ValueError("package member role requires its fixed canonical path")
        return self


class ProteoformReleasePackageDescriptor(FrozenModel):
    archive_format: Literal["canonical_ustar"] = "canonical_ustar"
    byte_size: int = Field(gt=0, le=M0408_MAX_PACKAGE_BYTES)
    digest: Sha256Digest
    member_count: Literal[10] = M0408_ARCHIVE_MEMBER_COUNT
    members: tuple[ProteoformReleaseMember, ...] = Field(
        min_length=M0408_ARCHIVE_MEMBER_COUNT,
        max_length=M0408_ARCHIVE_MEMBER_COUNT,
    )

    @field_validator("members")
    @classmethod
    def members_are_canonical(
        cls, values: tuple[ProteoformReleaseMember, ...]
    ) -> tuple[ProteoformReleaseMember, ...]:
        return tuple(sorted(values, key=lambda item: item.path))

    @model_validator(mode="after")
    def inventory_is_exact_and_unique(self) -> ProteoformReleasePackageDescriptor:
        paths = [item.path for item in self.members]
        if len(set(paths)) != len(paths) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("package descriptor member paths must be alias-free")
        if M0408_MANIFEST_PATH not in paths or M0408_SIGNATURE_RECEIPT_PATH not in paths:
            raise ValueError("package descriptor requires both generated members")
        roles = [item.role for item in self.members if item.role is not None]
        if set(roles) != set(ProteoformReleaseArtifactRole) or len(set(roles)) != len(roles):
            raise ValueError("package descriptor requires every caller artifact role")
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


class ProteoformReleaseResult(FrozenModel):
    output_type: Literal["proteoform_release_result"] = "proteoform_release_result"
    release_result_id: Identifier
    result_version: Literal["1.0.0"] = M0408_CONTRACT_VERSION
    request_digest: Sha256Digest
    context_digest: Sha256Digest
    context: ExecutionContext
    policy_digest: Sha256Digest
    policy: ProteoformReleasePolicy
    manifest_digest: Sha256Digest
    manifest: ProteoformReproducibilityManifest
    signature: ExternalProteoformSignature
    signature_verification: ProteoformSignatureVerification
    result_digest: Sha256Digest
    disposition: ProteoformReleaseDisposition
    package_descriptor: ProteoformReleasePackageDescriptor | None = None
    quarantine_reasons: tuple[ProteoformReleaseQuarantine, ...] = Field(
        default=(), max_length=M0408_MAX_QUARANTINE_REASONS
    )
    parent_target: Literal["protein_rna_discordance"] = M0408_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    signs_release: Literal[False] = False
    authenticates_signer: Literal[False] = False
    establishes_release_authority: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0408_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("release_result_id")
    @classmethod
    def result_id_has_exact_shape(cls, value: Identifier) -> Identifier:
        if re.fullmatch(r"result\.m0408\.[0-9a-f]{64}", value) is None:
            raise ValueError("release result identifier must be an opaque M04-08 result alias")
        return value

    @field_validator("quarantine_reasons", "evidence", "limitations")
    @classmethod
    def result_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def owned_result_regions_are_closed(self) -> ProteoformReleaseResult:
        if self.context_digest != context_digest(self.context):
            raise ValueError("M04-08 result context digest is inconsistent")
        if self.policy_digest != policy_digest(self.policy):
            raise ValueError("M04-08 result policy digest is inconsistent")
        if self.manifest_digest != manifest_digest(self.manifest):
            raise ValueError("M04-08 result manifest digest is inconsistent")
        statement = signing_statement_digest(
            active_manifest_digest=self.manifest_digest,
            active_policy_digest=self.policy_digest,
            release_id=self.manifest.release_id,
            release_version=self.manifest.release_version,
            identity_resolution_digest=self.manifest.identity_resolution_digest,
            intended_use_evidence_digest=self.manifest.intended_use_evidence_digest,
            terminal_routing_result_digest=self.manifest.terminal_routing_result_digest,
        )
        if (
            self.signature.claimed_statement_digest != statement
            or self.signature_verification.statement_digest != statement
            or self.signature_verification.algorithm is not self.signature.algorithm
            or self.signature_verification.key_id != self.signature.key_id
        ):
            raise ValueError("M04-08 signature regions do not bind the exact manifest statement")
        binding = _m0407_binding()
        stage_by_module = {item.module_id: item for item in self.manifest.stages}
        upstream_releasable = all(
            stage_by_module[module].disposition in allowed
            for module, allowed in _KNOWN_RELEASABLE_DISPOSITIONS.items()
        ) and (
            stage_by_module[ProteoformStageModuleId.M04_07].disposition
            in binding.releasable_dispositions
        )
        released = self.disposition is ProteoformReleaseDisposition.RELEASED
        if released != (self.signature_verification.verified and upstream_releasable):
            raise ValueError("release disposition contradicts stage and signature closure")
        if released != (self.package_descriptor is not None):
            raise ValueError("only a released result can expose a package descriptor")
        if released == bool(self.quarantine_reasons):
            raise ValueError("release disposition contradicts quarantine reasons")
        if released == self.human_review_required:
            raise ValueError("release disposition contradicts human review routing")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M04-08 result digest does not match its content")
        return self


class ProteoformReleaseVerification(FrozenModel):
    content_verified: bool
    authenticity_verified: bool
    verified: bool
    package_digest: Sha256Digest | None = None
    manifest_digest: Sha256Digest | None = None
    member_count: int = Field(ge=0, le=M0408_ARCHIVE_MEMBER_COUNT)
    signature_verification: ProteoformSignatureVerification
    reason_code: ProteoformPackageVerificationReason

    @model_validator(mode="after")
    def verification_outcome_is_closed(self) -> ProteoformReleaseVerification:
        if self.authenticity_verified != self.signature_verification.verified:
            raise ValueError("package authenticity contradicts signature verification")
        if self.verified != (self.content_verified and self.authenticity_verified):
            raise ValueError("package verified state contradicts component checks")
        if self.verified != (self.reason_code is ProteoformPackageVerificationReason.VERIFIED):
            raise ValueError("package verified state contradicts its reason")
        if self.content_verified and (
            self.package_digest is None
            or self.manifest_digest is None
            or self.member_count != M0408_ARCHIVE_MEMBER_COUNT
        ):
            raise ValueError("content-verified package requires complete content receipts")
        return self


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M04-08")
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
        raise ValueError("upstream controls do not authorize M04-08")


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


def _named_reproduction_references(
    evidence: ProteoformReproductionEvidence,
) -> tuple[tuple[str, ArtifactReference], ...]:
    return tuple(
        (name, getattr(evidence, name))
        for name in (
            "environment_lock",
            "build_recipe",
            "locked_tests",
            "benchmark",
            "traceability",
            "risk_control_verification",
            "data_model_reference_manifest",
            "reviewer_signoff",
            "rollback",
        )
    )


def release_evidence_index(
    request: BuildProteoformReleaseRequest,
) -> tuple[tuple[ArtifactReference, str], ...]:
    """Return the exact authority-safe evidence index for a release request."""

    refs = request.context.references
    items: list[tuple[ArtifactReference, str]] = [
        (refs.approved_configuration.evidence, "Caller-approved release configuration."),
        (refs.identity_lineage.evidence, "Caller-resolved identity lineage."),
        (refs.provenance.evidence, "Caller-accepted provenance control."),
        (refs.consent.evidence, "Caller-granted consent control."),
        (refs.quality.evidence, "Caller-accepted quality control."),
        (refs.support.evidence, "Caller-accepted support control."),
        (refs.intended_use.evidence, "Caller-accepted intended-use control."),
        (request.policy.evidence, "Pinned M04-08 release policy."),
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
    for reference, _claim in items:
        identity = (reference.artifact_id, reference.version)
        existing = by_identity.get(identity)
        if existing is not None and existing != reference:
            raise ValueError("one evidence identity cannot carry conflicting metadata")
        by_identity[identity] = reference
    unique: dict[tuple[str, str, str, str], tuple[ArtifactReference, str]] = {}
    for reference, claim in items:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        existing_item = unique.get(key)
        if existing_item is None or claim < existing_item[1]:
            unique[key] = (reference, claim)
    return tuple(unique[key] for key in sorted(unique, key=canonical_json_bytes))


def expected_release_quarantine_reasons(
    manifest: ProteoformReproducibilityManifest,
    verification: ProteoformSignatureVerification,
) -> tuple[ProteoformReleaseQuarantine, ...]:
    """Derive the only typed reasons that can prevent release bytes."""

    accepted = {
        ProteoformStageModuleId.M04_01: "conformant",
        ProteoformStageModuleId.M04_02: "reconciled",
        ProteoformStageModuleId.M04_03: "validated",
        ProteoformStageModuleId.M04_04: "qualified",
        ProteoformStageModuleId.M04_05: "cleared",
        ProteoformStageModuleId.M04_06: "accepted",
        ProteoformStageModuleId.M04_07: "supported",
    }
    reasons = [
        ProteoformReleaseQuarantine(
            code=ProteoformReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
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
            ProteoformReleaseQuarantine(
                code=ProteoformReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                reason_code=verification.reason_code.value,
                remediation_code="provide_verified_signature",
            )
        )
    return tuple(sorted(reasons, key=canonical_json_bytes))


def release_provenance_input_digests(  # noqa: PLR0913 - exact provenance closure inputs.
    request: BuildProteoformReleaseRequest,
    manifest: ProteoformReproducibilityManifest,
    *,
    request_digest: Sha256Digest,
    context_digest: Sha256Digest,
    policy_digest: Sha256Digest,
    manifest_digest: Sha256Digest,
    controls: tuple[ControlDecisionRecord, ...],
) -> set[Sha256Digest]:
    digests: set[Sha256Digest] = {
        request_digest,
        context_digest,
        policy_digest,
        manifest_digest,
        request.signature.claimed_statement_digest,
        manifest.reproduction_evidence_digest,
        manifest.identity_resolution_digest,
        manifest.intended_use_evidence_digest,
        manifest.terminal_routing_result_digest,
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
        manifest.m0406_transformation_manifest_digest,
        manifest.m0406_analysis_digest,
        request.supersedes_result_digest,
    ):
        if optional_digest is not None:
            digests.add(optional_digest)
    return digests


__all__ = [
    "M0408_ARCHIVE_MEMBER_COUNT",
    "M0408_AUTHORITY_LIMITATION_CODE",
    "M0408_AUTHORITY_LIMITATION_STATEMENT",
    "M0408_CALLER_ARTIFACT_COUNT",
    "M0408_CONTRACT_VERSION",
    "M0408_MANIFEST_PATH",
    "M0408_MAX_ARTIFACT_BYTES",
    "M0408_MAX_CANONICAL_REQUEST_BYTES",
    "M0408_MAX_EVIDENCE",
    "M0408_MAX_PACKAGE_BYTES",
    "M0408_MAX_QUARANTINE_REASONS",
    "M0408_MAX_REFERENCE_VERSIONS",
    "M0408_MAX_SIGNATURE_ALGORITHMS",
    "M0408_MAX_SIGNATURE_VALUE_CHARS",
    "M0408_MAX_SOFTWARE_VERSIONS",
    "M0408_MAX_STAGE_UPSTREAM_DIGESTS",
    "M0408_MAX_TOTAL_ARTIFACT_BYTES",
    "M0408_MAX_VERIFIER_IDS",
    "M0408_MODULE_ID",
    "M0408_OPERATION",
    "M0408_PACKAGE_LIMITATION_CODE",
    "M0408_PACKAGE_LIMITATION_STATEMENT",
    "M0408_PARENT",
    "M0408_QUARANTINED_SUPPORT_RATIONALE",
    "M0408_RELEASED_SUPPORT_RATIONALE",
    "M0408_REPRODUCIBILITY_LIMITATION_CODE",
    "M0408_REPRODUCIBILITY_LIMITATION_STATEMENT",
    "M0408_SENSITIVITY_NOTES",
    "M0408_SIGNATURE_RECEIPT_PATH",
    "M0408_STAGE_COUNT",
    "M0408_UNCERTAINTY_RATIONALES",
    "BuildProteoformReleaseRequest",
    "ExternalProteoformSignature",
    "M0408DependencyUnavailableError",
    "ProteoformPackageVerificationReason",
    "ProteoformParentDiscordanceReceipt",
    "ProteoformReferenceVersion",
    "ProteoformReleaseArtifact",
    "ProteoformReleaseArtifactRole",
    "ProteoformReleaseDisposition",
    "ProteoformReleaseMember",
    "ProteoformReleasePackageDescriptor",
    "ProteoformReleasePolicy",
    "ProteoformReleaseQuarantine",
    "ProteoformReleaseQuarantineCode",
    "ProteoformReleaseResult",
    "ProteoformReleaseVerification",
    "ProteoformReproducibilityManifest",
    "ProteoformReproductionEvidence",
    "ProteoformSignatureAlgorithm",
    "ProteoformSignatureVerification",
    "ProteoformSignatureVerificationReason",
    "ProteoformSoftwareVersion",
    "ProteoformStageModuleId",
    "ProteoformStageProvenance",
    "canonical_request_digest",
    "expected_release_quarantine_reasons",
    "opaque_release_identifier",
    "release_evidence_index",
    "release_provenance_input_digests",
]
