"""Provisional M05-07 PTM-localization support/abstention contracts.

The governing dossier gives M05-07 a behavioral brief but does not freeze an
operation name, schema names, media type, endpoint, or fixture matrix.  The
names and bounds in this file are therefore explicitly provisional.  They are
intended to make the M05-06 -> M05-07 handoff reviewable without claiming that
the implementation ABI is final.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m05_07.canonical import (
    canonical_request_digest,
    receipt_digest,
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

# PROVISIONAL ABI: the dossier does not supply implementation-level names.
M0507_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-07"
M0507_OPERATION: Final = "route_ptm_localization_support"
M0507_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0507_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-07+json"
M0507_PARENT: Final = "variant_peptide"
M0507_OWNER: Final = "Bioinformatics"
M0507_SAFETY_CLASS: Final = "S2"
M0507_GATE: Final = "G1"
M0507_DIMENSION_COUNT: Final = 8
M0507_MAX_FACTS: Final = M0507_DIMENSION_COUNT
M0507_MAX_REMEDIATION_PATHS: Final = 4
M0507_MAX_EVIDENCE: Final = 16
M0507_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0507_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0507_BENCHMARK_ITERATIONS: Final = 25
M0507_BENCHMARK_WARMUPS: Final = 1
M0507_MEAN_BUDGET_NS: Final = 2_000_000_000
M0507_P95_BUDGET_NS: Final = 3_000_000_000
M0507_M0506_RESULT_MEDIA_TYPE: Final = (
    "application/vnd.glio-proteogen.m05-06+json"
)
M0507_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for provisional M05-07 support routing; "
    "issuer authority is not authenticated."
)
M0507_UNCERTAINTY_RATIONALES: Final = (
    "Support routing does not estimate measurement uncertainty.",
    "Support routing does not estimate sampling uncertainty.",
    "Support routing does not estimate parameter uncertainty.",
    "Support routing does not estimate model-form uncertainty.",
    "Upstream identification uncertainty is not re-estimated.",
    "Support is categorical within the declared support domain.",
    "Transport beyond the reviewed support domain is not estimable.",
)


class PtmLocalizationSupportDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    DISEASE_CLASS = "disease_class"
    QUALITY = "quality"
    COMPLETENESS = "completeness"
    PLATFORM = "platform"
    REFERENCE = "reference"
    INTENDED_USE = "intended_use"


class PtmLocalizationDeclaredSupportState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"


class PtmLocalizationDimensionSupportDecision(StrEnum):
    SUPPORTED = "supported"
    OUTSIDE_DOMAIN = "outside_domain"
    INDETERMINATE = "indeterminate"


class PtmLocalizationSupportDisposition(StrEnum):
    SUPPORTED = "supported"
    ABSTAINED = "abstained"


class PtmLocalizationAbstentionCode(StrEnum):
    DIMENSION_OUTSIDE_DOMAIN = "dimension_outside_domain"
    DIMENSION_INDETERMINATE = "dimension_indeterminate"
    PREREQUISITE_UNRELEASABLE = "prerequisite_unreleasable"
    CRITICAL_CONTROL_UNRESOLVED = "critical_control_unresolved"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class PtmLocalizationRemediationPath(StrEnum):
    CORRECT_SUPPORT_DECLARATION = "correct_support_declaration"
    SUPPLY_REQUIRED_SUPPORT_EVIDENCE = "supply_required_support_evidence"
    RESOLVE_UPSTREAM_PREREQUISITE = "resolve_upstream_prerequisite"
    REQUEST_GOVERNED_SUPPORT_REVIEW = "request_governed_support_review"


class PtmLocalizationContextRole(StrEnum):
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    TREATMENT_HISTORY = "treatment_history"


_ALL_DIMENSIONS: Final[frozenset[PtmLocalizationSupportDimension]] = frozenset(
    PtmLocalizationSupportDimension
)


class PtmLocalizationSupportFact(FrozenModel):
    """One declared support decision for exactly one support dimension."""

    dimension: PtmLocalizationSupportDimension
    state: PtmLocalizationDeclaredSupportState
    decision: PtmLocalizationDimensionSupportDecision
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0507_MAX_EVIDENCE)

    @model_validator(mode="after")
    def state_and_decision_are_closed(self) -> PtmLocalizationSupportFact:
        if self.state is PtmLocalizationDeclaredSupportState.OBSERVED:
            if self.decision is PtmLocalizationDimensionSupportDecision.INDETERMINATE:
                raise ValueError("observed support cannot be indeterminate")
        elif self.decision is PtmLocalizationDimensionSupportDecision.SUPPORTED:
            raise ValueError("missing or unknown support cannot be supported")
        return self


class PtmLocalizationSupportPolicy(FrozenModel):
    """Provisional reviewed support policy; no policy authority is inferred."""

    policy_id: Identifier
    version: SemanticVersion
    dimensions: tuple[PtmLocalizationSupportDimension, ...] = Field(
        min_length=M0507_DIMENSION_COUNT,
        max_length=M0507_DIMENSION_COUNT,
    )
    reviewed_by: Identifier
    reviewed_at: AwareDatetime
    evidence: ArtifactReference
    never_infer_negative_from_missing: Literal[True] = True
    require_human_review_for_override: Literal[True] = True

    @field_validator("dimensions")
    @classmethod
    def dimensions_are_complete(
        cls,
        values: tuple[PtmLocalizationSupportDimension, ...],
    ) -> tuple[PtmLocalizationSupportDimension, ...]:
        if set(values) != _ALL_DIMENSIONS:
            raise ValueError("provisional policy must declare all eight support dimensions")
        return tuple(sorted(values, key=lambda item: item.value))


class PtmLocalizationSupportPrerequisites(FrozenModel):
    """Opaque M05-06 handoff until its concrete result contract is frozen."""

    harmonization_result: ArtifactReference
    quality_result: ArtifactReference | None = None
    raw_input_result: ArtifactReference | None = None

    @model_validator(mode="after")
    def harmonization_media_type_is_bound(
        self,
    ) -> PtmLocalizationSupportPrerequisites:
        if self.harmonization_result.media_type != M0507_M0506_RESULT_MEDIA_TYPE:
            raise ValueError(
                "M05-07 provisional prerequisite must bind the M05-06 result media type"
            )
        return self


class RoutePtmLocalizationSupportRequest(FrozenModel):
    """Provisional request ABI for M05-07 support/abstention routing."""

    operation: Literal["route_ptm_localization_support"] = M0507_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0507_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    prerequisites: PtmLocalizationSupportPrerequisites
    policy: PtmLocalizationSupportPolicy
    declared_facts: tuple[PtmLocalizationSupportFact, ...] = Field(
        min_length=M0507_MAX_FACTS,
        max_length=M0507_MAX_FACTS,
    )
    context_receipts: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M0507_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("declared_facts")
    @classmethod
    def facts_are_complete(
        cls,
        values: tuple[PtmLocalizationSupportFact, ...],
    ) -> tuple[PtmLocalizationSupportFact, ...]:
        dimensions = tuple(item.dimension for item in values)
        if len(set(dimensions)) != M0507_DIMENSION_COUNT or set(dimensions) != _ALL_DIMENSIONS:
            raise ValueError("request must contain exactly one fact for every support dimension")
        return tuple(sorted(values, key=lambda item: item.dimension.value))


class PtmLocalizationSupportReceipt(FrozenModel):
    """Auditable decision receipt for a provisional route."""

    request_digest: Sha256Digest
    disposition: PtmLocalizationSupportDisposition
    abstention_code: PtmLocalizationAbstentionCode | None = None
    remediation: tuple[PtmLocalizationRemediationPath, ...] = Field(
        default=(), max_length=M0507_MAX_REMEDIATION_PATHS
    )
    unsupported_dimensions: tuple[PtmLocalizationSupportDimension, ...] = Field(
        default=(), max_length=M0507_DIMENSION_COUNT
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0507_MAX_EVIDENCE)
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_closed(self) -> PtmLocalizationSupportReceipt:
        if self.disposition is PtmLocalizationSupportDisposition.SUPPORTED:
            if self.abstention_code is not None or self.remediation or self.unsupported_dimensions:
                raise ValueError("supported receipt cannot carry abstention material")
        elif (
            self.abstention_code is None
            or not self.remediation
            or not self.unsupported_dimensions
        ):
            raise ValueError("abstained receipt requires code, remediation, and dimensions")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("receipt digest does not match canonical receipt content")
        return self


class PtmLocalizationSupportRouteResult(FrozenModel):
    """Provisional result; an abstention is never represented as a valid finding."""

    output_type: Literal["ptm_localization_support_route"] = "ptm_localization_support_route"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0507_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RoutePtmLocalizationSupportRequest
    receipt: PtmLocalizationSupportReceipt
    support_decision: SupportDecision
    disposition: PtmLocalizationSupportDisposition
    abstention_code: PtmLocalizationAbstentionCode | None = None
    remediation: tuple[PtmLocalizationRemediationPath, ...] = Field(
        default=(), max_length=M0507_MAX_REMEDIATION_PATHS
    )
    parent_target: Literal["variant_peptide"] = M0507_PARENT
    emits_parent: Literal[False] = False
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0507_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> PtmLocalizationSupportRouteResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.receipt.request_digest != self.request_digest:
            raise ValueError("result receipt does not bind the exact request")
        if self.disposition is PtmLocalizationSupportDisposition.SUPPORTED:
            if self.abstention_code is not None or self.remediation:
                raise ValueError("supported result cannot carry abstention material")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("supported result requires supported status")
        elif self.abstention_code is None or not self.remediation:
            raise ValueError("abstained result requires typed remediation")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0507_BENCHMARK_ITERATIONS",
    "M0507_BENCHMARK_WARMUPS",
    "M0507_CONTRACT_VERSION",
    "M0507_DIMENSION_COUNT",
    "M0507_EVIDENCE_CLAIM",
    "M0507_GATE",
    "M0507_M0506_RESULT_MEDIA_TYPE",
    "M0507_MAX_CANONICAL_REQUEST_BYTES",
    "M0507_MAX_CANONICAL_RESULT_BYTES",
    "M0507_MAX_EVIDENCE",
    "M0507_MAX_FACTS",
    "M0507_MAX_REMEDIATION_PATHS",
    "M0507_MEAN_BUDGET_NS",
    "M0507_MODULE_ID",
    "M0507_OPERATION",
    "M0507_OUTPUT_MEDIA_TYPE",
    "M0507_OWNER",
    "M0507_P95_BUDGET_NS",
    "M0507_PARENT",
    "M0507_SAFETY_CLASS",
    "M0507_UNCERTAINTY_RATIONALES",
    "PtmLocalizationAbstentionCode",
    "PtmLocalizationContextRole",
    "PtmLocalizationDeclaredSupportState",
    "PtmLocalizationDimensionSupportDecision",
    "PtmLocalizationRemediationPath",
    "PtmLocalizationSupportDimension",
    "PtmLocalizationSupportDisposition",
    "PtmLocalizationSupportFact",
    "PtmLocalizationSupportPolicy",
    "PtmLocalizationSupportPrerequisites",
    "PtmLocalizationSupportReceipt",
    "PtmLocalizationSupportRouteResult",
    "RoutePtmLocalizationSupportRequest",
]
