"""Provisional M27-08 retirement, archival and knowledge-transfer contracts.

M27-08 owns retirement criteria, dependency migration, evidence preservation,
communication and long-term archive beneath the Search/quant workflow. The ABI
is provisional pending Computational biology owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m27_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
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

# PROVISIONAL ABI: inferred solely from dossier lines 9704-9744.
M2708_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-08"
M2708_OPERATION: Final = "retire_complex_activity_service"
M2708_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2708_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-08+json"
M2708_PARENT: Final = "complex activity"
M2708_OWNER: Final = "Computational biology"
M2708_SAFETY_CLASS: Final = "S3"
M2708_GATE: Final = "G5"
M2708_PROVISIONAL_ABI: Final = True
M2708_MAX_CRITERIA: Final = 128
M2708_MAX_MIGRATIONS: Final = 256
M2708_MAX_EVIDENCE: Final = 256
M2708_MAX_COMMUNICATIONS: Final = 128
M2708_MAX_FINDINGS: Final = 64
M2708_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2708_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2708_EVIDENCE_CLAIM: Final = (
    "Caller-declared M27-08 retirement, migration, preservation, communication "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)


class DependencyMigration(FrozenModel):
    migration_id: Identifier
    dependency_id: Identifier
    source_reference: NonEmptyStr
    target_reference: NonEmptyStr
    owner: NonEmptyStr
    status: MigrationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)


class EvidencePreservation(FrozenModel):
    preservation_id: Identifier
    artifact: ArtifactReference
    retention_class: NonEmptyStr
    checksum_verified: Literal[True] = True
    retrievable: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)


class LongTermArchive(FrozenModel):
    archive_id: Identifier
    archive_reference: NonEmptyStr
    retention_policy: NonEmptyStr
    manifest: ArtifactReference
    status: ArchiveStatus
    retrievable: bool
    immutable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)

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
    parent_target: Literal["complex activity"] = M2708_PARENT
    require_retirement_criteria: Literal[True] = True
    require_dependency_migration: Literal[True] = True
    require_evidence_preservation: Literal[True] = True
    require_communication: Literal[True] = True
    require_long_term_archive: Literal[True] = True
    require_retrievable_evidence: Literal[True] = True
    require_no_active_dependencies: Literal[True] = True
    signed_release_bundle_fallback: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2708_MAX_EVIDENCE)


class RetirementPackage(FrozenModel):
    """Retirement package, migration map and archived evidence."""

    package_id: Identifier
    version: SemanticVersion
    status: RetirementStatus
    criteria: tuple[RetirementCriterion, ...] = Field(min_length=1, max_length=M2708_MAX_CRITERIA)
    migrations: tuple[DependencyMigration, ...] = Field(
        min_length=1, max_length=M2708_MAX_MIGRATIONS
    )
    preserved_evidence: tuple[EvidencePreservation, ...] = Field(
        min_length=1, max_length=M2708_MAX_EVIDENCE
    )
    communications: tuple[CommunicationRecord, ...] = Field(
        min_length=1, max_length=M2708_MAX_COMMUNICATIONS
    )
    archive: LongTermArchive
    configuration: RetirementConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2708_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2708_MAX_EVIDENCE)


class RetireComplexActivityServiceRequest(FrozenModel):
    """Provisional request for retirement and long-term evidence preservation."""

    operation: Literal["retire_complex_activity_service"] = M2708_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2708_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    criteria: tuple[RetirementCriterion, ...] = Field(min_length=1, max_length=M2708_MAX_CRITERIA)
    migrations: tuple[DependencyMigration, ...] = Field(
        min_length=1, max_length=M2708_MAX_MIGRATIONS
    )
    preserved_evidence: tuple[EvidencePreservation, ...] = Field(
        min_length=1, max_length=M2708_MAX_EVIDENCE
    )
    communications: tuple[CommunicationRecord, ...] = Field(
        min_length=1, max_length=M2708_MAX_COMMUNICATIONS
    )
    archive: LongTermArchive
    configuration: RetirementConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2708_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None


class ComplexActivityRetirementResult(FrozenModel):
    """Retirement package and knowledge-transfer result with safe abstention."""

    output_type: Literal["complex_activity_retirement_package"] = (
        "complex_activity_retirement_package"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2708_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RetireComplexActivityServiceRequest
    status: RetirementRunStatus
    package: RetirementPackage | None = None
    findings: tuple[RetirementFinding, ...] = Field(default=(), max_length=M2708_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2708_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2708_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    def _provenance_is_closed(self) -> None:
        references = self.request.context.references
        expected_controls = tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=getattr(decision, "binding_digest", None),
            )
            for role, decision in (
                (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
                (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        )
        provenance_bindings = (
            (
                self.provenance.activity_id,
                "activity.m2708." + self.request_digest.removeprefix("sha256:"),
                "activity identity",
            ),
            (self.provenance.actor_id, self.request.context.actor_id, "actor identity"),
            (self.provenance.module_id, M2708_MODULE_ID, "module identity"),
            (self.provenance.module_version, M2708_CONTRACT_VERSION, "module version"),
            (self.provenance.generated_at, self.request.context.occurred_at, "generated time"),
            (
                self.provenance.input_digests,
                (self.request_digest, *(item.digest for item in self.request.source_artifacts)),
                "input digests",
            ),
            (
                self.provenance.configuration_digest,
                references.approved_configuration.evidence.digest,
                "configuration digest",
            ),
            (
                self.provenance.consent_decision_id,
                references.consent.decision_id,
                "consent decision",
            ),
            (self.provenance.consent_state, references.consent.state, "consent state"),
            (
                self.provenance.consent_policy_version,
                references.consent.policy_version,
                "consent policy version",
            ),
            (
                self.provenance.consent_evidence_digest,
                references.consent.evidence.digest,
                "consent evidence",
            ),
            (self.provenance.control_decisions, expected_controls, "control decisions"),
        )
        for actual, expected, label in provenance_bindings:
            if actual != expected:
                raise ValueError(f"provenance {label} does not bind the request")

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityRetirementResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        self._provenance_is_closed()
        if self.status is RetirementRunStatus.EXECUTED:
            if (
                self.package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("executed result requires a supported retirement package")
            if self.package.status is not RetirementStatus.EXECUTED:
                raise ValueError("executed result requires an executed retirement package")
            if (
                self.package.criteria != self.request.criteria
                or self.package.migrations != self.request.migrations
                or self.package.preserved_evidence != self.request.preserved_evidence
                or self.package.communications != self.request.communications
                or self.package.archive != self.request.archive
                or self.package.configuration != self.request.configuration
            ):
                raise ValueError("executed package must bind exact request retirement controls")
            expected_suffix = self.request_digest.removeprefix("sha256:")
            if (
                self.package.package_id != "package.m2708." + expected_suffix[:16]
                or self.package.version != "1.0.0"
                or self.package.locked is not True
            ):
                raise ValueError("executed package identity must bind the exact request digest")
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
    "M2708_CONTRACT_VERSION",
    "M2708_EVIDENCE_CLAIM",
    "M2708_GATE",
    "M2708_MAX_CANONICAL_REQUEST_BYTES",
    "M2708_MAX_CANONICAL_RESULT_BYTES",
    "M2708_MAX_COMMUNICATIONS",
    "M2708_MAX_CRITERIA",
    "M2708_MAX_EVIDENCE",
    "M2708_MAX_FINDINGS",
    "M2708_MAX_MIGRATIONS",
    "M2708_MODULE_ID",
    "M2708_OPERATION",
    "M2708_OUTPUT_MEDIA_TYPE",
    "M2708_OWNER",
    "M2708_PARENT",
    "M2708_PROVISIONAL_ABI",
    "M2708_SAFETY_CLASS",
    "ArchiveStatus",
    "CommunicationRecord",
    "ComplexActivityRetirementResult",
    "DependencyMigration",
    "EvidencePreservation",
    "LongTermArchive",
    "MigrationStatus",
    "RetireComplexActivityServiceRequest",
    "RetirementConfiguration",
    "RetirementCriterion",
    "RetirementFinding",
    "RetirementFindingCode",
    "RetirementPackage",
    "RetirementRunStatus",
    "RetirementStatus",
]
