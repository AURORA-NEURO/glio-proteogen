"""Provisional M26-08 retirement, archival and knowledge-transfer contracts.

M26-08 owns retirement criteria, dependency migration, evidence preservation,
communication and long-term archive beneath the Proteomics standards registry.
The ABI is provisional pending Scientific engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m26_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
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
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from dossier lines 9344-9384.
M2608_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-08"
M2608_OPERATION: Final = "retire_protein_subtype_service"
M2608_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2608_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-08+json"
M2608_PARENT: Final = "protein subtype"
M2608_OWNER: Final = "Scientific engineering"
M2608_SAFETY_CLASS: Final = "S3"
M2608_GATE: Final = "G5"
M2608_PROVISIONAL_ABI: Final = True
M2608_MAX_CRITERIA: Final = 128
M2608_MAX_MIGRATIONS: Final = 256
M2608_MAX_EVIDENCE: Final = 256
M2608_MAX_COMMUNICATIONS: Final = 128
M2608_MAX_FINDINGS: Final = 64
M2608_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2608_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2608_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-08 retirement, migration, preservation, communication "
    "and archival material; issuer authority is not authenticated."
)


class RetirementStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTED = "executed"
    ABSTAINED = "abstained"


class MigrationStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ArchiveStatus(StrEnum):
    PRESERVED = "preserved"
    VERIFIED = "verified"
    UNRETRIEVABLE = "unretrievable"


class RetirementRunStatus(StrEnum):
    EXECUTED = "executed"
    ABSTAINED = "abstained"


class RetirementFindingCode(StrEnum):
    CRITERION_UNSATISFIED = "criterion_unsatisfied"
    DEPENDENCY_MIGRATION_INCOMPLETE = "dependency_migration_incomplete"
    EVIDENCE_NOT_RETRIEVABLE = "evidence_not_retrievable"
    COMMUNICATION_UNACKNOWLEDGED = "communication_unacknowledged"
    ARCHIVE_UNVERIFIED = "archive_unverified"
    ACTIVE_DEPENDENCY = "active_dependency"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class RetirementCriterion(FrozenModel):
    criterion_id: Identifier
    statement: NonEmptyStr
    satisfied: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)


class DependencyMigration(FrozenModel):
    migration_id: Identifier
    dependency_id: Identifier
    source_reference: NonEmptyStr
    target_reference: NonEmptyStr
    owner: NonEmptyStr
    status: MigrationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)


class EvidencePreservation(FrozenModel):
    preservation_id: Identifier
    artifact: ArtifactReference
    retention_class: NonEmptyStr
    checksum_verified: Literal[True] = True
    retrievable: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def verified_checksum_is_retrievable(self) -> EvidencePreservation:
        if self.checksum_verified and not self.retrievable:
            raise ValueError("checksum-verified preservation must remain retrievable")
        return self


class CommunicationRecord(FrozenModel):
    communication_id: Identifier
    audience: NonEmptyStr
    message: NonEmptyStr
    acknowledged: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)


class LongTermArchive(FrozenModel):
    archive_id: Identifier
    archive_reference: NonEmptyStr
    retention_policy: NonEmptyStr
    manifest: ArtifactReference
    status: ArchiveStatus
    retrievable: bool
    immutable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def archive_status_matches_retrievability(self) -> LongTermArchive:
        if self.status is ArchiveStatus.VERIFIED and not self.retrievable:
            raise ValueError("verified archive must be retrievable")
        if self.status is ArchiveStatus.UNRETRIEVABLE and self.retrievable:
            raise ValueError("unretrievable archive cannot be marked retrievable")
        return self


class RetirementConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["protein subtype"] = M2608_PARENT
    require_retirement_criteria: Literal[True] = True
    require_dependency_migration: Literal[True] = True
    require_evidence_preservation: Literal[True] = True
    require_communication: Literal[True] = True
    require_long_term_archive: Literal[True] = True
    require_retrievable_evidence: Literal[True] = True
    require_no_active_dependencies: Literal[True] = True
    signed_release_bundle_fallback: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2608_MAX_EVIDENCE)


class RetirementPackage(FrozenModel):
    """Retirement package, migration map and archived evidence."""

    package_id: Identifier
    version: SemanticVersion
    status: RetirementStatus
    criteria: tuple[RetirementCriterion, ...] = Field(min_length=1, max_length=M2608_MAX_CRITERIA)
    migrations: tuple[DependencyMigration, ...] = Field(
        min_length=1, max_length=M2608_MAX_MIGRATIONS
    )
    preserved_evidence: tuple[EvidencePreservation, ...] = Field(
        min_length=1, max_length=M2608_MAX_EVIDENCE
    )
    communications: tuple[CommunicationRecord, ...] = Field(
        min_length=1, max_length=M2608_MAX_COMMUNICATIONS
    )
    archive: LongTermArchive
    configuration: RetirementConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def package_is_closed(self) -> RetirementPackage:
        criterion_ids = tuple(item.criterion_id for item in self.criteria)
        migration_ids = tuple(item.migration_id for item in self.migrations)
        preservation_ids = tuple(item.preservation_id for item in self.preserved_evidence)
        communication_ids = tuple(item.communication_id for item in self.communications)
        groups = (criterion_ids, migration_ids, preservation_ids, communication_ids)
        if any(len(ids) != len(set(ids)) for ids in groups):
            raise ValueError("retirement package identifiers must be unique")
        if self.status is RetirementStatus.EXECUTED:
            if any(not item.satisfied for item in self.criteria):
                raise ValueError("executed package cannot contain unsatisfied criteria")
            if any(item.status is not MigrationStatus.COMPLETED for item in self.migrations):
                raise ValueError("executed package requires completed dependency migrations")
            if any(not item.retrievable for item in self.preserved_evidence):
                raise ValueError("executed package requires retrievable preserved evidence")
            if any(not item.acknowledged for item in self.communications):
                raise ValueError("executed package requires acknowledged communications")
            if self.archive.status is not ArchiveStatus.VERIFIED:
                raise ValueError("executed package requires a verified archive")
        return self


class RetirementFinding(FrozenModel):
    finding_id: Identifier
    code: RetirementFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2608_MAX_EVIDENCE)


class RetireProteinSubtypeServiceRequest(FrozenModel):
    """Provisional request for retirement and long-term evidence preservation."""

    operation: Literal["retire_protein_subtype_service"] = M2608_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2608_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    criteria: tuple[RetirementCriterion, ...] = Field(min_length=1, max_length=M2608_MAX_CRITERIA)
    migrations: tuple[DependencyMigration, ...] = Field(
        min_length=1, max_length=M2608_MAX_MIGRATIONS
    )
    preserved_evidence: tuple[EvidencePreservation, ...] = Field(
        min_length=1, max_length=M2608_MAX_EVIDENCE
    )
    communications: tuple[CommunicationRecord, ...] = Field(
        min_length=1, max_length=M2608_MAX_COMMUNICATIONS
    )
    archive: LongTermArchive
    configuration: RetirementConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2608_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None


class ProteinSubtypeRetirementResult(FrozenModel):
    """Retirement package and knowledge-transfer result with safe abstention."""

    output_type: Literal["protein_subtype_retirement_package"] = (
        "protein_subtype_retirement_package"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2608_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RetireProteinSubtypeServiceRequest
    status: RetirementRunStatus
    package: RetirementPackage | None = None
    findings: tuple[RetirementFinding, ...] = Field(default=(), max_length=M2608_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2608_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2608_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeRetirementResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is RetirementRunStatus.EXECUTED:
            if (
                self.package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("executed result requires a supported retirement package")
        elif (
            self.package is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no package and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2608_CONTRACT_VERSION",
    "M2608_EVIDENCE_CLAIM",
    "M2608_GATE",
    "M2608_MAX_CANONICAL_REQUEST_BYTES",
    "M2608_MAX_CANONICAL_RESULT_BYTES",
    "M2608_MAX_COMMUNICATIONS",
    "M2608_MAX_CRITERIA",
    "M2608_MAX_EVIDENCE",
    "M2608_MAX_FINDINGS",
    "M2608_MAX_MIGRATIONS",
    "M2608_MODULE_ID",
    "M2608_OPERATION",
    "M2608_OUTPUT_MEDIA_TYPE",
    "M2608_OWNER",
    "M2608_PARENT",
    "M2608_PROVISIONAL_ABI",
    "M2608_SAFETY_CLASS",
    "ArchiveStatus",
    "CommunicationRecord",
    "DependencyMigration",
    "EvidencePreservation",
    "LongTermArchive",
    "MigrationStatus",
    "ProteinSubtypeRetirementResult",
    "RetireProteinSubtypeServiceRequest",
    "RetirementConfiguration",
    "RetirementCriterion",
    "RetirementFinding",
    "RetirementFindingCode",
    "RetirementPackage",
    "RetirementRunStatus",
    "RetirementStatus",
]
