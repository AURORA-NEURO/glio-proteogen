"""Provisional M16-01 upstream contract resolver contracts.

The dossier requires typed upstream discovery, version compatibility, consent,
intended-use, support, provenance, and uncertainty preservation.  The public
ABI is not frozen; this contract emits only a validated bundle and auditable
compatibility report for the protein-RNA discordance parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_01.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5436-5479.
M1601_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-01"
M1601_OPERATION: Final = "resolve_protein_rna_discordance_upstream_contracts"
M1601_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1601_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-01+json"
M1601_PARENT: Final = "protein_rna_discordance"
M1601_OWNER: Final = "Platform engineering"
M1601_SAFETY_CLASS: Final = "S2"
M1601_GATE: Final = "G0"
M1601_PROVISIONAL_ABI: Final = True
M1601_MAX_CANDIDATES: Final = 128
M1601_MAX_ACCEPTED: Final = 128
M1601_MAX_ISSUES: Final = 128
M1601_MAX_EVIDENCE: Final = 64
M1601_MAX_REQUIRED_KINDS: Final = 16
M1601_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1601_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class UpstreamObjectKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATION = "ptm_annotation"
    APPROVED_CONFIGURATION = "approved_configuration"
    IDENTITY_LINEAGE = "identity_lineage"
    PROVENANCE = "provenance"
    CONSENT = "consent"
    QUALITY = "quality"
    SUPPORT = "support"
    INTENDED_USE = "intended_use"


class CompatibilityStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"


class ResolverStatus(StrEnum):
    RESOLVED = "resolved"
    ABSTAINED = "abstained"


class CompatibilityIssueCode(StrEnum):
    VERSION_MISMATCH = "version_mismatch"
    MEDIA_TYPE_MISMATCH = "media_type_mismatch"
    CONSENT_REQUIRED = "consent_required"
    INTENDED_USE_MISMATCH = "intended_use_mismatch"
    SUPPORT_MISSING = "support_missing"
    PROVENANCE_MISSING = "provenance_missing"
    IDENTITY_UNRESOLVED = "identity_unresolved"
    UNIT_MISMATCH = "unit_mismatch"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class UpstreamCandidate(FrozenModel):
    candidate_id: Identifier
    kind: UpstreamObjectKind
    artifact: ArtifactReference
    contract_version: SemanticVersion
    required_media_type: NonEmptyStr
    declared_consent: Literal[True]
    declared_support: Literal[True]
    declared_provenance: Literal[True]
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)


class CompatibilityIssue(FrozenModel):
    issue_id: Identifier
    code: CompatibilityIssueCode
    candidate_id: Identifier | None = None
    message: NonEmptyStr
    blocking: bool = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)


class CompatibilityReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    status: CompatibilityStatus
    accepted_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1601_MAX_ACCEPTED
    )
    issues: tuple[CompatibilityIssue, ...] = Field(default=(), max_length=M1601_MAX_ISSUES)
    all_rejections_typed: Literal[True] = True
    auditable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def accepted_ids_are_unique(self) -> CompatibilityReport:
        if len(set(self.accepted_candidate_ids)) != len(self.accepted_candidate_ids):
            raise ValueError("accepted candidate ids must be unique")
        return self


class ResolverConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    policy_reference: ArtifactReference
    locked: Literal[True] = True
    consent_required: Literal[True] = True
    support_required: Literal[True] = True
    provenance_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)


class ResolverPolicy(FrozenModel):
    required_kinds: tuple[UpstreamObjectKind, ...] = Field(
        min_length=1, max_length=M1601_MAX_REQUIRED_KINDS
    )
    reject_incompatible: Literal[True] = True
    preserve_uncertainty: Literal[True] = True
    configuration: ResolverConfiguration

    @model_validator(mode="after")
    def required_kinds_are_unique(self) -> ResolverPolicy:
        if len(set(self.required_kinds)) != len(self.required_kinds):
            raise ValueError("required upstream kinds must be unique")
        return self


class ValidatedUpstreamBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    accepted_candidates: tuple[UpstreamCandidate, ...] = Field(
        min_length=1, max_length=M1601_MAX_ACCEPTED
    )
    compatibility_report: CompatibilityReport
    consent_preserved: Literal[True] = True
    provenance_preserved: Literal[True] = True
    uncertainty_preserved: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_matches_report(self) -> ValidatedUpstreamBundle:
        ids = tuple(item.candidate_id for item in self.accepted_candidates)
        if len(ids) != len(set(ids)):
            raise ValueError("bundle candidate ids must be unique")
        if set(ids) != set(self.compatibility_report.accepted_candidate_ids):
            raise ValueError("bundle candidates must match compatibility report")
        if self.compatibility_report.status is not CompatibilityStatus.ACCEPTED:
            raise ValueError("bundle requires an accepted compatibility report")
        return self


class ResolverFinding(FrozenModel):
    finding_id: Identifier
    code: CompatibilityIssueCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)


class ResolveProteinRnaDiscordanceUpstreamRequest(FrozenModel):
    """Provisional request for validated upstream discovery and compatibility."""

    operation: Literal["resolve_protein_rna_discordance_upstream_contracts"] = M1601_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1601_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    candidates: tuple[UpstreamCandidate, ...] = Field(
        min_length=1, max_length=M1601_MAX_CANDIDATES
    )
    policy: ResolverPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1601_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_candidates_are_unique_and_complete(
        self,
    ) -> ResolveProteinRnaDiscordanceUpstreamRequest:
        ids = tuple(item.candidate_id for item in self.candidates)
        if len(ids) != len(set(ids)):
            raise ValueError("request candidate ids must be unique")
        kinds = {item.kind for item in self.candidates}
        if not set(self.policy.required_kinds).issubset(kinds):
            raise ValueError("request is missing a required upstream kind")
        return self


class ProteinRnaDiscordanceUpstreamResolutionResult(FrozenModel):
    """Validated upstream bundle and typed compatibility report with abstention."""

    output_type: Literal["protein_rna_discordance_upstream_resolution"] = (
        "protein_rna_discordance_upstream_resolution"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1601_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ResolveProteinRnaDiscordanceUpstreamRequest
    status: ResolverStatus
    bundle: ValidatedUpstreamBundle | None = None
    compatibility_report: CompatibilityReport
    findings: tuple[ResolverFinding, ...] = Field(default=(), max_length=M1601_MAX_ISSUES)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1601_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1601_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ResolverStatus.RESOLVED:
            if (
                self.bundle is None
                or self.compatibility_report.status is not CompatibilityStatus.ACCEPTED
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("resolved result requires a supported accepted bundle")
        elif (
            self.bundle is not None
            or self.abstention_reason is None
            or self.compatibility_report.status is CompatibilityStatus.ACCEPTED
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1601_CONTRACT_VERSION",
    "M1601_GATE",
    "M1601_MAX_ACCEPTED",
    "M1601_MAX_CANDIDATES",
    "M1601_MAX_CANONICAL_REQUEST_BYTES",
    "M1601_MAX_CANONICAL_RESULT_BYTES",
    "M1601_MAX_EVIDENCE",
    "M1601_MAX_ISSUES",
    "M1601_MAX_REQUIRED_KINDS",
    "M1601_MODULE_ID",
    "M1601_OPERATION",
    "M1601_OUTPUT_MEDIA_TYPE",
    "M1601_OWNER",
    "M1601_PARENT",
    "M1601_PROVISIONAL_ABI",
    "M1601_SAFETY_CLASS",
    "CompatibilityIssue",
    "CompatibilityIssueCode",
    "CompatibilityReport",
    "CompatibilityStatus",
    "ProteinRnaDiscordanceUpstreamResolutionResult",
    "ResolveProteinRnaDiscordanceUpstreamRequest",
    "ResolverConfiguration",
    "ResolverFinding",
    "ResolverPolicy",
    "ResolverStatus",
    "UpstreamCandidate",
    "UpstreamObjectKind",
    "ValidatedUpstreamBundle",
]
