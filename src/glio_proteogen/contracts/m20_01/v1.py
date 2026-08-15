"""Provisional M20-01 upstream contract resolver contracts.

M20-01 owns typed upstream discovery and compatibility beneath Biomarker-panel
translation. Candidate consent, intended use, support, provenance and
uncertainty remain visible; unknown or unsupported inputs never become
negative findings. The public ABI is provisional pending ML engineering owner
confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_01.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
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

# PROVISIONAL ABI: inferred solely from the M20-01 dossier slice.
M2001_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-01"
M2001_OPERATION: Final = "resolve_protein_subtype_upstream_contracts"
M2001_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2001_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-01+json"
M2001_PARENT: Final = "protein subtype"
M2001_OWNER: Final = "ML engineering"
M2001_SAFETY_CLASS: Final = "S2"
M2001_GATE: Final = "G0"
M2001_PROVISIONAL_ABI: Final = True
M2001_MAX_CANDIDATES: Final = 128
M2001_MAX_RULES: Final = 64
M2001_MAX_DECISIONS: Final = M2001_MAX_CANDIDATES
M2001_MAX_EVIDENCE: Final = 64
M2001_MAX_FINDINGS: Final = 64
M2001_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2001_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2001_EVIDENCE_CLAIM: Final = (
    "Caller-declared M20-01 upstream compatibility, consent, support and "
    "provenance material; issuer authority is not authenticated."
)


class UpstreamSourceKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PTM_ANNOTATION = "ptm_annotation"
    APPROVED_CONFIGURATION = "approved_configuration"
    IDENTITY_LINEAGE = "identity_lineage"
    PROVENANCE = "provenance"
    CONSENT = "consent"
    QUALITY = "quality"
    SUPPORT = "support"
    INTENDED_USE = "intended_use"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class ResolverStatus(StrEnum):
    VALIDATED = "validated"
    ABSTAINED = "abstained"


class ResolverFindingCode(StrEnum):
    INCOMPATIBLE_VERSION = "incompatible_version"
    MEDIA_TYPE_MISMATCH = "media_type_mismatch"
    CONSENT_NOT_GRANTED = "consent_not_granted"
    SUPPORT_NOT_AVAILABLE = "support_not_available"
    INTENDED_USE_MISMATCH = "intended_use_mismatch"
    PROVENANCE_MISSING = "provenance_missing"
    COMPATIBILITY_UNKNOWN = "compatibility_unknown"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class CompatibilityRule(FrozenModel):
    rule_id: Identifier
    name: NonEmptyStr
    required_source_kind: UpstreamSourceKind
    required_media_type: NonEmptyStr
    required_intended_use: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2001_MAX_EVIDENCE)


class UpstreamCandidate(FrozenModel):
    """A candidate artifact with caller-declared control states."""

    candidate_id: Identifier
    source_kind: UpstreamSourceKind
    artifact: ArtifactReference
    compatibility: CompatibilityStatus
    compatibility_reason: NonEmptyStr
    consent_state: ConsentState
    intended_use: NonEmptyStr
    support_status: SupportStatus
    provenance_artifact: ArtifactReference | None = None
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def compatible_candidate_is_safe(self) -> UpstreamCandidate:
        if self.compatibility is CompatibilityStatus.COMPATIBLE:
            if self.consent_state is not ConsentState.GRANTED:
                raise ValueError("compatible candidate requires granted consent")
            if self.support_status is not SupportStatus.SUPPORTED:
                raise ValueError("compatible candidate requires supported status")
            if self.provenance_artifact is None:
                raise ValueError("compatible candidate requires provenance evidence")
        return self


class CompatibilityDecision(FrozenModel):
    candidate_id: Identifier
    status: CompatibilityStatus
    reason_code: ResolverFindingCode
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2001_MAX_EVIDENCE)


class ResolverConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    rules: tuple[CompatibilityRule, ...] = Field(min_length=1, max_length=M2001_MAX_RULES)
    accepted_intended_uses: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)
    require_granted_consent: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> ResolverConfiguration:
        rule_ids = tuple(item.rule_id for item in self.rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("compatibility rule ids must be unique")
        return self


class CompatibilityReport(FrozenModel):
    """Immutable compatibility decisions preserving every candidate outcome."""

    report_id: Identifier
    version: SemanticVersion
    decisions: tuple[CompatibilityDecision, ...] = Field(
        min_length=1, max_length=M2001_MAX_DECISIONS
    )
    selected_candidate_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M2001_MAX_CANDIDATES
    )
    rejected_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M2001_MAX_CANDIDATES
    )
    unresolved_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M2001_MAX_CANDIDATES
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> CompatibilityReport:
        decision_ids = tuple(item.candidate_id for item in self.decisions)
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("compatibility decision candidate ids must be unique")
        groups = (
            self.selected_candidate_ids,
            self.rejected_candidate_ids,
            self.unresolved_candidate_ids,
        )
        flattened = tuple(candidate_id for group in groups for candidate_id in group)
        if len(flattened) != len(set(flattened)):
            raise ValueError("report candidate outcomes must be mutually exclusive")
        if set(flattened) != set(decision_ids):
            raise ValueError("report must classify every compatibility decision")
        return self


class ValidatedUpstreamBundle(FrozenModel):
    """Accepted, compatible candidates plus their immutable report."""

    bundle_id: Identifier
    version: SemanticVersion
    candidates: tuple[UpstreamCandidate, ...] = Field(min_length=1, max_length=M2001_MAX_CANDIDATES)
    compatibility_report: CompatibilityReport
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_supported(self) -> ValidatedUpstreamBundle:
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("validated candidate ids must be unique")
        if any(
            item.compatibility is not CompatibilityStatus.COMPATIBLE for item in self.candidates
        ):
            raise ValueError("validated bundle cannot include incompatible candidates")
        if set(candidate_ids) != set(self.compatibility_report.selected_candidate_ids):
            raise ValueError("validated bundle must match selected compatibility candidates")
        return self


class ResolverFinding(FrozenModel):
    finding_id: Identifier
    code: ResolverFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2001_MAX_EVIDENCE)


class ResolveProteinSubtypeUpstreamContractsRequest(FrozenModel):
    """Provisional request for typed upstream discovery and compatibility."""

    operation: Literal["resolve_protein_subtype_upstream_contracts"] = M2001_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2001_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    candidates: tuple[UpstreamCandidate, ...] = Field(
        min_length=1, max_length=M2001_MAX_CANDIDATES
    )
    configuration: ResolverConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2001_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> ResolveProteinSubtypeUpstreamContractsRequest:
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("request candidate ids must be unique")
        return self


class ProteinSubtypeUpstreamResolutionResult(FrozenModel):
    """Validated upstream bundle and compatibility report with safe abstention."""

    output_type: Literal["protein_subtype_upstream_resolution"] = (
        "protein_subtype_upstream_resolution"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2001_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ResolveProteinSubtypeUpstreamContractsRequest
    status: ResolverStatus
    bundle: ValidatedUpstreamBundle | None = None
    compatibility_report: CompatibilityReport
    findings: tuple[ResolverFinding, ...] = Field(default=(), max_length=M2001_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2001_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2001_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeUpstreamResolutionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        request_ids = {item.candidate_id for item in self.request.candidates}
        report_ids = {item.candidate_id for item in self.compatibility_report.decisions}
        if request_ids != report_ids:
            raise ValueError("compatibility report must classify every request candidate")
        if self.status is ResolverStatus.VALIDATED:
            if (
                self.bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("validated result requires a supported upstream bundle")
        elif (
            self.bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2001_CONTRACT_VERSION",
    "M2001_EVIDENCE_CLAIM",
    "M2001_GATE",
    "M2001_MAX_CANDIDATES",
    "M2001_MAX_CANONICAL_REQUEST_BYTES",
    "M2001_MAX_CANONICAL_RESULT_BYTES",
    "M2001_MAX_DECISIONS",
    "M2001_MAX_EVIDENCE",
    "M2001_MAX_FINDINGS",
    "M2001_MAX_RULES",
    "M2001_MODULE_ID",
    "M2001_OPERATION",
    "M2001_OUTPUT_MEDIA_TYPE",
    "M2001_OWNER",
    "M2001_PARENT",
    "M2001_PROVISIONAL_ABI",
    "M2001_SAFETY_CLASS",
    "CompatibilityDecision",
    "CompatibilityReport",
    "CompatibilityRule",
    "CompatibilityStatus",
    "ProteinSubtypeUpstreamResolutionResult",
    "ResolveProteinSubtypeUpstreamContractsRequest",
    "ResolverConfiguration",
    "ResolverFinding",
    "ResolverFindingCode",
    "ResolverStatus",
    "UpstreamCandidate",
    "UpstreamSourceKind",
    "ValidatedUpstreamBundle",
]
