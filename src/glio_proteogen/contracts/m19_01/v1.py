"""Provisional M19-01 upstream contract resolver contracts.

M19-01 owns typed upstream discovery and compatibility beneath
Immunopeptidomic evidence. Candidate consent, intended use, support,
provenance and uncertainty remain visible; unknown or unsupported inputs
never become negative findings. The public ABI is provisional pending
Bioinformatics owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_01.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M19-01 dossier slice.
M1901_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-01"
M1901_OPERATION: Final = "resolve_proteotype_upstream_contracts"
M1901_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1901_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-01+json"
M1901_PARENT: Final = "proteotype"
M1901_OWNER: Final = "Bioinformatics"
M1901_SAFETY_CLASS: Final = "S2"
M1901_GATE: Final = "G0"
M1901_PROVISIONAL_ABI: Final = True
M1901_MAX_CANDIDATES: Final = 128
M1901_MAX_RULES: Final = 64
M1901_MAX_DECISIONS: Final = M1901_MAX_CANDIDATES
M1901_MAX_EVIDENCE: Final = 64
M1901_MAX_FINDINGS: Final = 64
M1901_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1901_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1901_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-01 upstream compatibility, consent, support and "
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
    COMPATIBLE_ACCEPTED = "compatible_accepted"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_references_are_unique(self) -> CompatibilityRule:
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("compatibility rule evidence digests must be unique")
        return self


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def compatible_candidate_is_safe(self) -> UpstreamCandidate:
        if self.compatibility is CompatibilityStatus.COMPATIBLE:
            if self.consent_state is not ConsentState.GRANTED:
                raise ValueError("compatible candidate requires granted consent")
            if self.support_status is not SupportStatus.SUPPORTED:
                raise ValueError("compatible candidate requires supported status")
            if self.provenance_artifact is None:
                raise ValueError("compatible candidate requires provenance evidence")
        references = (self.artifact.digest,) + (
            (self.provenance_artifact.digest,) if self.provenance_artifact is not None else ()
        )
        if len(references) != len(set(references)):
            raise ValueError("candidate artifact and provenance digests must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("candidate evidence digests must be unique")
        if self.artifact.digest not in set(evidence_digests):
            raise ValueError("candidate evidence must bind the candidate artifact")
        if self.provenance_artifact is not None and self.provenance_artifact.digest not in set(
            evidence_digests
        ):
            raise ValueError("candidate evidence must bind the provenance artifact")
        return self


class CompatibilityDecision(FrozenModel):
    candidate_id: Identifier
    status: CompatibilityStatus
    reason_code: ResolverFindingCode
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def reason_code_matches_status(self) -> CompatibilityDecision:
        compatible_codes = {
            ResolverFindingCode.COMPATIBLE_ACCEPTED,
            ResolverFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        }
        incompatible_codes = {
            ResolverFindingCode.INCOMPATIBLE,
            ResolverFindingCode.INCOMPATIBLE_VERSION,
            ResolverFindingCode.MEDIA_TYPE_MISMATCH,
            ResolverFindingCode.CONSENT_NOT_GRANTED,
            ResolverFindingCode.SUPPORT_NOT_AVAILABLE,
            ResolverFindingCode.INTENDED_USE_MISMATCH,
            ResolverFindingCode.PROVENANCE_MISSING,
        }
        unknown_codes = {
            ResolverFindingCode.UNKNOWN,
            ResolverFindingCode.COMPATIBILITY_UNKNOWN,
            ResolverFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        }
        allowed = {
            CompatibilityStatus.COMPATIBLE: compatible_codes,
            CompatibilityStatus.INCOMPATIBLE: incompatible_codes,
            CompatibilityStatus.UNKNOWN: unknown_codes,
        }[self.status]
        if self.reason_code not in allowed:
            raise ValueError("compatibility decision reason code does not match status")
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("compatibility decision evidence digests must be unique")
        return self


class ResolverConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    rules: tuple[CompatibilityRule, ...] = Field(min_length=1, max_length=M1901_MAX_RULES)
    accepted_intended_uses: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)
    require_granted_consent: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> ResolverConfiguration:
        rule_ids = tuple(item.rule_id for item in self.rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("compatibility rule ids must be unique")
        intended_uses = tuple(self.accepted_intended_uses)
        if len(intended_uses) != len(set(intended_uses)):
            raise ValueError("accepted intended uses must be unique")
        rule_uses = tuple(item.required_intended_use for item in self.rules)
        if any(use not in set(intended_uses) for use in rule_uses):
            raise ValueError("every compatibility rule must use an accepted intended use")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("configuration evidence digests must be unique")
        return self


class CompatibilityReport(FrozenModel):
    """Immutable compatibility decisions preserving every candidate outcome."""

    report_id: Identifier
    version: SemanticVersion
    decisions: tuple[CompatibilityDecision, ...] = Field(
        min_length=1, max_length=M1901_MAX_DECISIONS
    )
    selected_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1901_MAX_CANDIDATES
    )
    rejected_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1901_MAX_CANDIDATES
    )
    unresolved_candidate_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1901_MAX_CANDIDATES
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1901_MAX_EVIDENCE)

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
        by_id = {item.candidate_id: item.status for item in self.decisions}
        if set(self.selected_candidate_ids) != {
            candidate_id
            for candidate_id, status in by_id.items()
            if status is CompatibilityStatus.COMPATIBLE
        }:
            raise ValueError("selected candidates must match compatible decisions")
        if set(self.rejected_candidate_ids) != {
            candidate_id
            for candidate_id, status in by_id.items()
            if status is CompatibilityStatus.INCOMPATIBLE
        }:
            raise ValueError("rejected candidates must match incompatible decisions")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("compatibility report evidence digests must be unique")
        return self


class ValidatedUpstreamBundle(FrozenModel):
    """Accepted, compatible candidates plus their immutable report."""

    bundle_id: Identifier
    version: SemanticVersion
    candidates: tuple[UpstreamCandidate, ...] = Field(min_length=1, max_length=M1901_MAX_CANDIDATES)
    compatibility_report: CompatibilityReport
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1901_MAX_EVIDENCE)

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
        if any(item.consent_state is not ConsentState.GRANTED for item in self.candidates):
            raise ValueError("validated bundle candidates require granted consent")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("validated bundle evidence digests must be unique")
        return self


class ResolverFinding(FrozenModel):
    finding_id: Identifier
    code: ResolverFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1901_MAX_EVIDENCE)


class ResolveProteotypeUpstreamContractsRequest(FrozenModel):
    """Provisional request for typed upstream discovery and compatibility."""

    operation: Literal["resolve_proteotype_upstream_contracts"] = M1901_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1901_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    candidates: tuple[UpstreamCandidate, ...] = Field(min_length=1, max_length=M1901_MAX_CANDIDATES)
    configuration: ResolverConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1901_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> ResolveProteotypeUpstreamContractsRequest:
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("request candidate ids must be unique")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        source_digests = tuple(item.digest for item in self.source_artifacts)
        if len(source_digests) != len(set(source_digests)):
            raise ValueError("request source artifact digests must be unique")
        source_digest_set = set(source_digests)
        required_digests = {
            digest
            for candidate in self.candidates
            for digest in (
                candidate.artifact.digest,
                candidate.provenance_artifact.digest
                if candidate.provenance_artifact is not None
                else None,
                *(evidence.reference.digest for evidence in candidate.evidence),
            )
            if digest is not None
        }
        required_digests.update(
            evidence.reference.digest
            for rule in self.configuration.rules
            for evidence in rule.evidence
        )
        required_digests.update(
            evidence.reference.digest for evidence in self.configuration.evidence
        )
        if not required_digests <= source_digest_set:
            raise ValueError("request source artifacts must bind all resolver evidence")
        return self


class ProteotypeUpstreamResolutionResult(FrozenModel):
    """Validated upstream bundle and compatibility report with safe abstention."""

    output_type: Literal["proteotype_upstream_resolution"] = "proteotype_upstream_resolution"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1901_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ResolveProteotypeUpstreamContractsRequest
    status: ResolverStatus
    bundle: ValidatedUpstreamBundle | None = None
    compatibility_report: CompatibilityReport
    findings: tuple[ResolverFinding, ...] = Field(default=(), max_length=M1901_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1901_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1901_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeUpstreamResolutionResult:  # noqa: PLR0912
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        request_ids = {item.candidate_id for item in self.request.candidates}
        report_ids = {item.candidate_id for item in self.compatibility_report.decisions}
        if request_ids != report_ids:
            raise ValueError("compatibility report must classify every request candidate")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if self.provenance.module_id != M1901_MODULE_ID:
            raise ValueError("result provenance must identify M19-01")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("result evidence digests must be unique")
        if self.status is ResolverStatus.VALIDATED:
            if (
                self.bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("validated result requires a supported upstream bundle")
            if not self.compatibility_report.selected_candidate_ids:
                raise ValueError("validated result requires at least one selected candidate")
            if self.human_review_required:
                raise ValueError("validated result cannot require human review")
            if self.bundle.compatibility_report != self.compatibility_report:
                raise ValueError("validated result report must match the validated bundle report")
        elif (
            self.bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {
                SupportStatus.LIMITED,
                SupportStatus.UNSUPPORTED,
                SupportStatus.REVIEW_REQUIRED,
            }
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        elif not self.findings or not self.human_review_required:
            raise ValueError("abstained result requires typed findings and human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1901_CONTRACT_VERSION",
    "M1901_EVIDENCE_CLAIM",
    "M1901_GATE",
    "M1901_MAX_CANDIDATES",
    "M1901_MAX_CANONICAL_REQUEST_BYTES",
    "M1901_MAX_CANONICAL_RESULT_BYTES",
    "M1901_MAX_DECISIONS",
    "M1901_MAX_EVIDENCE",
    "M1901_MAX_FINDINGS",
    "M1901_MAX_RULES",
    "M1901_MODULE_ID",
    "M1901_OPERATION",
    "M1901_OUTPUT_MEDIA_TYPE",
    "M1901_OWNER",
    "M1901_PARENT",
    "M1901_PROVISIONAL_ABI",
    "M1901_SAFETY_CLASS",
    "CompatibilityDecision",
    "CompatibilityReport",
    "CompatibilityRule",
    "CompatibilityStatus",
    "ProteotypeUpstreamResolutionResult",
    "ResolveProteotypeUpstreamContractsRequest",
    "ResolverConfiguration",
    "ResolverFinding",
    "ResolverFindingCode",
    "ResolverStatus",
    "UpstreamCandidate",
    "UpstreamSourceKind",
    "ValidatedUpstreamBundle",
]
