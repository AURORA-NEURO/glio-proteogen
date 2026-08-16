"""Provisional M15-02 context and subtype stratifier contracts.

M15-02 owns a typed context profile and applicable mechanism set beneath the
longitudinal recurrence proteotype.  The dossier does not freeze the public
operation, model representation, or media type, so this ABI is provisional
pending Platform engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M15-02 dossier slice.
M1502_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-02"
M1502_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M1502_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:5120-5160"
M1502_OPERATION: Final = "stratify_context_and_subtype"
M1502_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1502_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-02+json"
M1502_M1501_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-01+json"
M1502_PARENT: Final = "complex_activity"
M1502_OWNER: Final = "Platform engineering"
M1502_SAFETY_CLASS: Final = "S2"
M1502_GATE: Final = "G1"
M1502_PROVISIONAL_ABI: Final = True
M1502_MAX_ATTRIBUTES: Final = 64
M1502_MAX_MECHANISMS: Final = 128
M1502_MAX_EVALUATIONS: Final = M1502_MAX_ATTRIBUTES
M1502_MAX_EVIDENCE: Final = 64
M1502_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1502_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1502_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-02 context, subtype, mechanism and support material; "
    "issuer authority is not authenticated."
)


class ContextDimension(StrEnum):
    DISEASE_CLASS = "disease_class"
    SUBTYPE = "subtype"
    AGE = "age"
    TERRITORY = "territory"
    TREATMENT_ERA = "treatment_era"
    SPECIMEN = "specimen"
    PLATFORM = "platform"
    BIOLOGICAL_CONTEXT = "biological_context"


class ContextValueStatus(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ContextEvaluationStatus(StrEnum):
    SUPPORTED = "supported"
    CONFLICTED = "conflicted"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ContextStratificationStatus(StrEnum):
    STRATIFIED = "stratified"
    ABSTAINED = "abstained"


class ContextFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    CONFLICTING_CONTEXT = "conflicting_context"
    UNSUPPORTED_CONTEXT = "unsupported_context"
    PROHIBITED_PROXY = "prohibited_proxy"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ContextAttribute(FrozenModel):
    """One context or subtype value with explicit support state."""

    attribute_id: Identifier
    dimension: ContextDimension
    value: NonEmptyStr
    status: ContextValueStatus
    support_basis: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)


class ApplicableMechanism(FrozenModel):
    """A mechanism applicable to the declared context, never a treatment claim."""

    mechanism_id: Identifier
    mechanism_class: NonEmptyStr
    context_attribute_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1502_MAX_ATTRIBUTES
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)


class ContextProfile(FrozenModel):
    """Locked, versioned context profile and applicable mechanism set."""

    profile_id: Identifier
    version: SemanticVersion
    attributes: tuple[ContextAttribute, ...] = Field(min_length=1, max_length=M1502_MAX_ATTRIBUTES)
    mechanisms: tuple[ApplicableMechanism, ...] = Field(
        min_length=1, max_length=M1502_MAX_MECHANISMS
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)

    @model_validator(mode="after")
    def profile_ids_are_closed(self) -> ContextProfile:
        attribute_ids = tuple(item.attribute_id for item in self.attributes)
        mechanism_ids = tuple(item.mechanism_id for item in self.mechanisms)
        if len(attribute_ids) != len(set(attribute_ids)):
            raise ValueError("context attribute ids must be unique")
        if len(mechanism_ids) != len(set(mechanism_ids)):
            raise ValueError("mechanism ids must be unique")
        allowed = set(attribute_ids)
        if any(
            attribute_id not in allowed
            for mechanism in self.mechanisms
            for attribute_id in mechanism.context_attribute_ids
        ):
            raise ValueError("mechanisms must reference declared context attributes")
        return self


class ContextEvaluation(FrozenModel):
    attribute_id: Identifier
    status: ContextEvaluationStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)


class ContextFinding(FrozenModel):
    finding_id: Identifier
    code: ContextFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)


class StratifyContextAndSubtypeRequest(FrozenModel):
    """Provisional request bound to the M15-01 hypothesis registry result."""

    operation: Literal["stratify_context_and_subtype"] = M1502_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1502_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    attributes: tuple[ContextAttribute, ...] = Field(min_length=1, max_length=M1502_MAX_ATTRIBUTES)
    mechanisms: tuple[ApplicableMechanism, ...] = Field(
        min_length=1, max_length=M1502_MAX_MECHANISMS
    )
    reviewer_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1502_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> StratifyContextAndSubtypeRequest:
        if self.upstream_result.media_type != M1502_M1501_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M15-01 registry result")
        attribute_ids = tuple(item.attribute_id for item in self.attributes)
        mechanism_ids = tuple(item.mechanism_id for item in self.mechanisms)
        if len(attribute_ids) != len(set(attribute_ids)):
            raise ValueError("request context attribute ids must be unique")
        if len(mechanism_ids) != len(set(mechanism_ids)):
            raise ValueError("request mechanism ids must be unique")
        allowed = set(attribute_ids)
        if any(
            attribute_id not in allowed
            for mechanism in self.mechanisms
            for attribute_id in mechanism.context_attribute_ids
        ):
            raise ValueError("request mechanisms must reference declared attributes")
        return self


class LongitudinalRecurrenceContextStratificationResult(FrozenModel):
    """Typed context profile with safe abstention and preserved uncertainty."""

    output_type: Literal["longitudinal_recurrence_context_stratification"] = (
        "longitudinal_recurrence_context_stratification"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1502_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: StratifyContextAndSubtypeRequest
    status: ContextStratificationStatus
    profile: ContextProfile | None = None
    evaluations: tuple[ContextEvaluation, ...] = Field(default=(), max_length=M1502_MAX_EVALUATIONS)
    findings: tuple[ContextFinding, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1502_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1502_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> LongitudinalRecurrenceContextStratificationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        attribute_ids = {item.attribute_id for item in self.request.attributes}
        evaluation_ids = tuple(item.attribute_id for item in self.evaluations)
        if set(evaluation_ids) != attribute_ids or len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("every context attribute must have exactly one evaluation")
        unsafe = {
            ContextEvaluationStatus.CONFLICTED,
            ContextEvaluationStatus.NOT_EVALUABLE,
            ContextEvaluationStatus.ABSTAINED,
        }
        if self.status is ContextStratificationStatus.STRATIFIED:
            if (
                self.profile is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in unsafe for item in self.evaluations)
            ):
                raise ValueError("stratified result requires supported context attributes")
        elif (
            self.profile is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no profile and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1502_CONTRACT_VERSION",
    "M1502_DOSSIER_SHA256",
    "M1502_DOSSIER_SLICE",
    "M1502_EVIDENCE_CLAIM",
    "M1502_GATE",
    "M1502_M1501_INPUT_MEDIA_TYPE",
    "M1502_MAX_ATTRIBUTES",
    "M1502_MAX_CANONICAL_REQUEST_BYTES",
    "M1502_MAX_CANONICAL_RESULT_BYTES",
    "M1502_MAX_EVALUATIONS",
    "M1502_MAX_EVIDENCE",
    "M1502_MAX_MECHANISMS",
    "M1502_MODULE_ID",
    "M1502_OPERATION",
    "M1502_OUTPUT_MEDIA_TYPE",
    "M1502_OWNER",
    "M1502_PARENT",
    "M1502_PROVISIONAL_ABI",
    "M1502_SAFETY_CLASS",
    "ApplicableMechanism",
    "ContextAttribute",
    "ContextDimension",
    "ContextEvaluation",
    "ContextEvaluationStatus",
    "ContextFinding",
    "ContextFindingCode",
    "ContextProfile",
    "ContextStratificationStatus",
    "ContextValueStatus",
    "LongitudinalRecurrenceContextStratificationResult",
    "StratifyContextAndSubtypeRequest",
]
