"""Provisional M15-07 plausibility and negative-control contracts.

The M15-07 dossier requires orthogonal controls, direction and conservation
checks, assay-physics checks, competing-mechanism checks, a plausibility grade,
and visible unresolved conflicts.  Failed controls block release; unsupported
or unresolved cases abstain rather than becoming negative findings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
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
    UncertaintyEstimate,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M15-07 dossier slice.
M1507_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-07"
M1507_OPERATION: Final = "adjudicate_complex_activity_plausibility"
M1507_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1507_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-07+json"
M1507_M1506_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-06+json"
M1507_PARENT: Final = "complex_activity"
M1507_OWNER: Final = "Quality engineering"
M1507_SAFETY_CLASS: Final = "S2"
M1507_GATE: Final = "G3"
M1507_PROVISIONAL_ABI: Final = True
M1507_MAX_CONTROLS: Final = 128
M1507_MAX_EVALUATIONS: Final = M1507_MAX_CONTROLS
M1507_MAX_CONFLICTS: Final = 128
M1507_MAX_MECHANISMS: Final = 64
M1507_MAX_EVIDENCE: Final = 64
M1507_MAX_FINDINGS: Final = 64
M1507_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1507_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1507_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-06 sensitivity and M15-07 control evidence; issuer authority "
    "is not authenticated."
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
    required_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1507_MAX_EVIDENCE
    )
    release_blocking: Literal[True] = True


class ControlEvaluation(FrozenModel):
    control_id: Identifier
    outcome: ControlOutcome
    observed_direction: NonEmptyStr | None = None
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1507_MAX_EVIDENCE)


class UnresolvedConflict(FrozenModel):
    conflict_id: Identifier
    description: NonEmptyStr
    competing_mechanisms: tuple[NonEmptyStr, ...] = Field(
        min_length=2, max_length=M1507_MAX_MECHANISMS
    )
    release_blocking: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1507_MAX_EVIDENCE)


class PlausibilityFinding(FrozenModel):
    finding_id: Identifier
    code: PlausibilityFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1507_MAX_EVIDENCE)


class AdjudicateComplexActivityPlausibilityRequest(FrozenModel):
    """Provisional request bound to the M15-06 sensitivity result."""

    operation: Literal["adjudicate_complex_activity_plausibility"] = M1507_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1507_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    sensitivity_result: ArtifactReference
    controls: tuple[PlausibilityControl, ...] = Field(min_length=1, max_length=M1507_MAX_CONTROLS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1507_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateComplexActivityPlausibilityRequest:
        if self.sensitivity_result.media_type != M1507_M1506_RESULT_MEDIA_TYPE:
            raise ValueError("plausibility request must bind the provisional M15-06 result")
        ids = tuple(item.control_id for item in self.controls)
        if len(ids) != len(set(ids)):
            raise ValueError("control ids must be unique")
        return self


class ComplexActivityPlausibilityAdjudicationResult(FrozenModel):
    """Plausibility grade with complete controls and visible conflicts."""

    output_type: Literal["complex_activity_plausibility_adjudication"] = (
        "complex_activity_plausibility_adjudication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1507_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateComplexActivityPlausibilityRequest
    status: PlausibilityAdjudicationStatus
    grade: PlausibilityGrade | None = None
    evaluations: tuple[ControlEvaluation, ...] = Field(default=(), max_length=M1507_MAX_EVALUATIONS)
    conflicts: tuple[UnresolvedConflict, ...] = Field(default=(), max_length=M1507_MAX_CONFLICTS)
    findings: tuple[PlausibilityFinding, ...] = Field(default=(), max_length=M1507_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1507_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1507_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityPlausibilityAdjudicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        control_ids = {item.control_id for item in self.request.controls}
        evaluation_ids = tuple(item.control_id for item in self.evaluations)
        if set(evaluation_ids) != control_ids or len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("every control must have exactly one evaluation")
        blocking_outcomes = {
            ControlOutcome.FAILED,
            ControlOutcome.NOT_EVALUABLE,
            ControlOutcome.ABSTAINED,
        }
        has_blocking_outcome = any(item.outcome in blocking_outcomes for item in self.evaluations)
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("plausibility finding ids must be unique")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("plausibility result requires evidence references")
        if self.status is PlausibilityAdjudicationStatus.ADJUDICATED:
            if (
                self.grade is None
                or self.abstention_reason is not None
                or has_blocking_outcome
                or self.conflicts
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError(
                    "adjudicated result requires review-only controls and no conflicts"
                )
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


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Expose all seven uncertainty dimensions for plausibility adjudication."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Orthogonal evidence, known controls, direction, conservation, assay physics, "
            "and competing-mechanism checks are within the provisional support domain."
            if supported
            else (
                "At least one control, conflict, support, or plausibility input was not safely "
                "evaluable."
            )
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Bayesian/state-space, curated baseline, and orthogonal consensus architectures "
            "remain explicit; negative controls and conflicts gate promotion.",
        ),
    )


def expected_provenance(
    request: AdjudicateComplexActivityPlausibilityRequest, request_digest: Sha256Digest
) -> ProvenanceRecord:
    """Bind request inputs and the seven caller-declared control decisions."""

    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1507_MODULE_ID,
        module_version=M1507_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.sensitivity_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=request.sensitivity_result.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M1507_CONTRACT_VERSION",
    "M1507_EVIDENCE_CLAIM",
    "M1507_GATE",
    "M1507_M1506_RESULT_MEDIA_TYPE",
    "M1507_MAX_CANONICAL_REQUEST_BYTES",
    "M1507_MAX_CANONICAL_RESULT_BYTES",
    "M1507_MAX_CONFLICTS",
    "M1507_MAX_CONTROLS",
    "M1507_MAX_EVALUATIONS",
    "M1507_MAX_EVIDENCE",
    "M1507_MAX_FINDINGS",
    "M1507_MAX_MECHANISMS",
    "M1507_MODULE_ID",
    "M1507_OPERATION",
    "M1507_OUTPUT_MEDIA_TYPE",
    "M1507_OWNER",
    "M1507_PARENT",
    "M1507_PROVISIONAL_ABI",
    "M1507_SAFETY_CLASS",
    "AdjudicateComplexActivityPlausibilityRequest",
    "ComplexActivityPlausibilityAdjudicationResult",
    "ControlEvaluation",
    "ControlKind",
    "ControlOutcome",
    "PlausibilityAdjudicationStatus",
    "PlausibilityControl",
    "PlausibilityFinding",
    "PlausibilityFindingCode",
    "PlausibilityGrade",
    "UnresolvedConflict",
    "expected_provenance",
    "expected_uncertainty",
]
