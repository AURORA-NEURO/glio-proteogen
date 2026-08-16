"""Provisional M12-07 plausibility and negative-control contracts.

The M12-07 dossier requires orthogonal evidence, known controls, direction,
conservation, assay-physics and competing-mechanism checks, a plausibility
grade, and visible unresolved conflicts. Failed controls block release;
unsupported or unresolved cases abstain rather than becoming negative
findings. The public ABI is provisional pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m12_07.canonical import (
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
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M12-07 dossier slice.
M1207_MODULE_ID: Final = "GLIO-PROTEOGEN-M12-07"
M1207_OPERATION: Final = "adjudicate_biomarker_panel_plausibility"
M1207_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1207_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-07+json"
M1207_M1206_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-06+json"
M1207_PARENT: Final = "biomarker_panel"
M1207_OWNER: Final = "Computational biology"
M1207_SAFETY_CLASS: Final = "S2"
M1207_GATE: Final = "G3"
M1207_PROVISIONAL_ABI: Final = True
M1207_MAX_CONTROLS: Final = 128
M1207_MAX_EVALUATIONS: Final = M1207_MAX_CONTROLS
M1207_MAX_CONFLICTS: Final = 128
M1207_MAX_MECHANISMS: Final = 64
M1207_MAX_EVIDENCE: Final = 64
M1207_MAX_FINDINGS: Final = 64
M1207_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1207_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1207_EVIDENCE_CLAIM: Final = (
    "Caller-declared M12-06 mechanism and M12-07 control evidence; issuer "
    "authority is not authenticated."
)


class ControlKind(StrEnum):
    ORTHOGONAL_EVIDENCE = "orthogonal_evidence"
    KNOWN_CONTROL = "known_control"
    DIRECTION = "direction"
    CONSERVATION = "conservation"
    ASSAY_PHYSICS = "assay_physics"
    COMPETING_MECHANISM = "competing_mechanism"


class ControlOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class PlausibilityGrade(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class PlausibilityAdjudicationStatus(StrEnum):
    ADJUDICATED = "adjudicated"
    ABSTAINED = "abstained"


class PlausibilityFindingCode(StrEnum):
    CONTROL_FAILED = "control_failed"
    CONTROL_NOT_EVALUABLE = "control_not_evaluable"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class PlausibilityControl(FrozenModel):
    control_id: Identifier
    kind: ControlKind
    criterion: NonEmptyStr
    expected_direction: NonEmptyStr | None = None
    # The value is a caller-declared observation; opaque evidence artifacts are
    # never traversed or treated as authenticated measurements by this module.
    declared_outcome: ControlOutcome | None = None
    declared_observed_direction: NonEmptyStr | None = None
    required_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1207_MAX_EVIDENCE
    )
    release_blocking: Literal[True] = True


class ControlEvaluation(FrozenModel):
    control_id: Identifier
    outcome: ControlOutcome
    observed_direction: NonEmptyStr | None = None
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1207_MAX_EVIDENCE)


class UnresolvedConflict(FrozenModel):
    conflict_id: Identifier
    description: NonEmptyStr
    competing_mechanisms: tuple[NonEmptyStr, ...] = Field(
        min_length=2, max_length=M1207_MAX_MECHANISMS
    )
    release_blocking: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1207_MAX_EVIDENCE)


class PlausibilityFinding(FrozenModel):
    finding_id: Identifier
    code: PlausibilityFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1207_MAX_EVIDENCE)


class AdjudicateBiomarkerPanelPlausibilityRequest(FrozenModel):
    """Provisional request bound to the M12-06 mechanism result."""

    operation: Literal["adjudicate_biomarker_panel_plausibility"] = M1207_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1207_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mechanism_inference_result: ArtifactReference
    controls: tuple[PlausibilityControl, ...] = Field(min_length=1, max_length=M1207_MAX_CONTROLS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1207_MAX_EVIDENCE
    )
    declared_conflicts: tuple[UnresolvedConflict, ...] = Field(
        default=(), max_length=M1207_MAX_CONFLICTS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateBiomarkerPanelPlausibilityRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        if self.mechanism_inference_result.media_type != M1207_M1206_RESULT_MEDIA_TYPE:
            raise ValueError("plausibility request must bind the provisional M12-06 result")
        ids = tuple(item.control_id for item in self.controls)
        if len(ids) != len(set(ids)):
            raise ValueError("control ids must be unique")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact ids must be unique")
        if self.mechanism_inference_result.artifact_id in set(source_ids):
            raise ValueError("mechanism result must not be duplicated as a source artifact")
        conflict_ids = tuple(item.conflict_id for item in self.declared_conflicts)
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ValueError("declared conflict ids must be unique")
        return self


class BiomarkerPanelPlausibilityAdjudicationResult(FrozenModel):
    """Plausibility grade with complete controls and visible conflicts."""

    output_type: Literal["biomarker_panel_plausibility_adjudication"] = (
        "biomarker_panel_plausibility_adjudication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1207_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateBiomarkerPanelPlausibilityRequest
    status: PlausibilityAdjudicationStatus
    grade: PlausibilityGrade | None = None
    evaluations: tuple[ControlEvaluation, ...] = Field(default=(), max_length=M1207_MAX_EVALUATIONS)
    conflicts: tuple[UnresolvedConflict, ...] = Field(default=(), max_length=M1207_MAX_CONFLICTS)
    findings: tuple[PlausibilityFinding, ...] = Field(default=(), max_length=M1207_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M1207_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1207_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelPlausibilityAdjudicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        control_ids = {item.control_id for item in self.request.controls}
        evaluation_ids = tuple(item.control_id for item in self.evaluations)
        if set(evaluation_ids) != control_ids or len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("every control must have exactly one evaluation")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding ids must be unique")
        conflict_ids = tuple(item.conflict_id for item in self.conflicts)
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ValueError("conflict ids must be unique")
        blocking_outcomes = {
            ControlOutcome.FAILED,
            ControlOutcome.NOT_EVALUABLE,
            ControlOutcome.ABSTAINED,
        }
        has_blocking_outcome = any(item.outcome in blocking_outcomes for item in self.evaluations)
        if self.status is PlausibilityAdjudicationStatus.ADJUDICATED:
            if (
                self.grade is None
                or self.abstention_reason is not None
                or has_blocking_outcome
                or self.conflicts
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("adjudicated result requires all controls passed and no conflicts")
        elif (
            self.grade is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no grade and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1207_CONTRACT_VERSION",
    "M1207_EVIDENCE_CLAIM",
    "M1207_GATE",
    "M1207_M1206_RESULT_MEDIA_TYPE",
    "M1207_MAX_CANONICAL_REQUEST_BYTES",
    "M1207_MAX_CANONICAL_RESULT_BYTES",
    "M1207_MAX_CONFLICTS",
    "M1207_MAX_CONTROLS",
    "M1207_MAX_EVALUATIONS",
    "M1207_MAX_EVIDENCE",
    "M1207_MAX_FINDINGS",
    "M1207_MAX_MECHANISMS",
    "M1207_MODULE_ID",
    "M1207_OPERATION",
    "M1207_OUTPUT_MEDIA_TYPE",
    "M1207_OWNER",
    "M1207_PARENT",
    "M1207_PROVISIONAL_ABI",
    "M1207_SAFETY_CLASS",
    "AdjudicateBiomarkerPanelPlausibilityRequest",
    "BiomarkerPanelPlausibilityAdjudicationResult",
    "ControlEvaluation",
    "ControlKind",
    "ControlOutcome",
    "PlausibilityAdjudicationStatus",
    "PlausibilityControl",
    "PlausibilityFinding",
    "PlausibilityFindingCode",
    "PlausibilityGrade",
    "UnresolvedConflict",
]
