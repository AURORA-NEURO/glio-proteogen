"""Provisional M09-05 mechanism and constraint-integrator contracts.

The dossier specifies hard/soft biological constraints and explicit conflict
reporting, but does not freeze the public ABI, ontology catalogue, estimator,
or constraint ceilings.  Every symbol here is provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m09_05.canonical import (
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

M0905_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-05"
M0905_OPERATION: Final = "integrate_complex_activity_constraints"
M0905_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0905_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-05+json"
M0905_BASELINE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-04+json"
M0905_PARENT: Final = "complex_activity"
M0905_OWNER: Final = "Quality engineering"
M0905_SAFETY_CLASS: Final = "S2"
M0905_GATE: Final = "G2"
M0905_PROVISIONAL_ABI: Final = True
M0905_MAX_ESTIMATES: Final = 1_024
M0905_MAX_CONSTRAINTS: Final = 256
M0905_MAX_REPORTS: Final = 256
M0905_MAX_EVIDENCE: Final = 64
M0905_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0905_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0905_EVIDENCE_CLAIM: Final = (
    "Caller-declared complex-activity mechanism and constraint evidence; "
    "issuer authority is not authenticated."
)


class MechanismConstraintKind(StrEnum):
    BIOLOGICAL_PRIOR = "biological_prior"
    ONTOLOGY = "ontology"
    GRAPH = "graph"
    TOPOLOGY = "topology"
    CONSERVATION = "conservation"
    CHEMISTRY = "chemistry"
    ASSAY_PHYSICS = "assay_physics"
    DISEASE = "disease"


class ConstraintSeverity(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ConstraintEvaluationStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"


class ConstraintIntegratorStatus(StrEnum):
    ESTIMATED = "estimated"
    ABSTAINED = "abstained"


class ConstraintEstimateKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class MechanismConstraint(FrozenModel):
    constraint_id: Identifier
    version: SemanticVersion
    kind: MechanismConstraintKind
    expression: NonEmptyStr
    severity: ConstraintSeverity
    reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)


class ConstraintIntegratorPolicy(FrozenModel):
    """Locked hard/soft constraint and conflict-reporting declaration."""

    policy_id: Identifier
    version: SemanticVersion
    estimator_family: NonEmptyStr
    constraints: tuple[MechanismConstraint, ...] = Field(
        min_length=1, max_length=M0905_MAX_CONSTRAINTS
    )
    conflict_tolerance: float = Field(ge=0.0, le=1.0)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_ids_are_unique(self) -> ConstraintIntegratorPolicy:
        ids = tuple(item.constraint_id for item in self.constraints)
        if len(ids) != len(set(ids)):
            raise ValueError("constraint ids must be unique")
        return self


class ConstraintAwareEstimate(FrozenModel):
    feature_id: Identifier
    kind: ConstraintEstimateKind
    unit: NonEmptyStr
    estimate_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    support_score: float = Field(ge=0.0, le=1.0)
    applied_constraint_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0905_MAX_CONSTRAINTS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> ConstraintAwareEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is ConstraintEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar estimate requires one scalar value")
        elif self.kind is ConstraintEstimateKind.INTERVAL:
            if (
                self.estimate_value is None
                or self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.estimate_value <= self.upper_bound
                or self.category is not None
            ):
                raise ValueError("interval estimate requires ordered bounds and center")
        elif self.category is None or self.estimate_value is not None or has_interval:
            raise ValueError("categorical estimate requires only a category")
        return self


class ConstraintSatisfactionReport(FrozenModel):
    constraint_id: Identifier
    severity: ConstraintSeverity
    status: ConstraintEvaluationStatus
    violation_score: float | None = Field(default=None, ge=0.0, le=1.0)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def violation_score_is_explicit(self) -> ConstraintSatisfactionReport:
        if self.status is ConstraintEvaluationStatus.VIOLATED and self.violation_score is None:
            raise ValueError("violated constraint requires a violation score")
        if (
            self.status is not ConstraintEvaluationStatus.VIOLATED
            and self.violation_score is not None
        ):
            raise ValueError("non-violated constraint cannot carry a violation score")
        return self


class IntegrateComplexActivityConstraintsRequest(FrozenModel):
    """Provisional request bound to the complete M09-04 probabilistic result."""

    operation: Literal["integrate_complex_activity_constraints"] = M0905_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0905_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    baseline_result: ArtifactReference
    policy: ConstraintIntegratorPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0905_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> IntegrateComplexActivityConstraintsRequest:
        if self.baseline_result.media_type != M0905_BASELINE_MEDIA_TYPE:
            raise ValueError("constraint request must bind the provisional M09-04 result")
        return self


class IntegrateComplexActivityConstraintsResult(FrozenModel):
    """Constraint-aware estimate with explicit hard/soft satisfaction report."""

    output_type: Literal["complex_activity_constraint_estimate"] = (
        "complex_activity_constraint_estimate"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0905_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IntegrateComplexActivityConstraintsRequest
    status: ConstraintIntegratorStatus
    estimates: tuple[ConstraintAwareEstimate, ...] = Field(
        default=(), max_length=M0905_MAX_ESTIMATES
    )
    satisfaction_report: tuple[ConstraintSatisfactionReport, ...] = Field(
        default=(), max_length=M0905_MAX_REPORTS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0905_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> IntegrateComplexActivityConstraintsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        report_ids = {item.constraint_id for item in self.satisfaction_report}
        policy_ids = {item.constraint_id for item in self.request.policy.constraints}
        if report_ids and report_ids != policy_ids:
            raise ValueError("satisfaction report must cover the requested constraints")
        hard_violated = any(
            item.status is ConstraintEvaluationStatus.VIOLATED
            and item.severity is ConstraintSeverity.HARD
            for item in self.satisfaction_report
        )
        if self.status is ConstraintIntegratorStatus.ESTIMATED:
            if not self.estimates or self.abstention_reason is not None or hard_violated:
                raise ValueError(
                    "estimated result requires supported estimates and no hard violation"
                )
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0905_BASELINE_MEDIA_TYPE",
    "M0905_CONTRACT_VERSION",
    "M0905_EVIDENCE_CLAIM",
    "M0905_GATE",
    "M0905_MAX_CANONICAL_REQUEST_BYTES",
    "M0905_MAX_CANONICAL_RESULT_BYTES",
    "M0905_MAX_CONSTRAINTS",
    "M0905_MAX_ESTIMATES",
    "M0905_MAX_EVIDENCE",
    "M0905_MAX_REPORTS",
    "M0905_MODULE_ID",
    "M0905_OPERATION",
    "M0905_OUTPUT_MEDIA_TYPE",
    "M0905_OWNER",
    "M0905_PARENT",
    "M0905_PROVISIONAL_ABI",
    "M0905_SAFETY_CLASS",
    "ConstraintAwareEstimate",
    "ConstraintEstimateKind",
    "ConstraintEvaluationStatus",
    "ConstraintIntegratorPolicy",
    "ConstraintIntegratorStatus",
    "ConstraintSatisfactionReport",
    "ConstraintSeverity",
    "IntegrateComplexActivityConstraintsRequest",
    "IntegrateComplexActivityConstraintsResult",
    "MechanismConstraint",
    "MechanismConstraintKind",
]
