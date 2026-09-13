"""Provisional M09-05 mechanism and constraint-integrator contracts.

The dossier specifies hard/soft biological constraints and explicit conflict
reporting, but does not freeze the public ABI, ontology catalogue, estimator,
or constraint ceilings.  Every symbol here is provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
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
M0905_MAX_TYPED_OBSERVATIONS: Final = 256
M0905_MAX_TYPED_EFFECT: Final = 20.0
M0905_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0905_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0905_GLIOMA_MODEL_FAMILY: Final = "glioma-mechanism-constraint-irls/1.0.0"
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


class ConstraintObservationState(StrEnum):
    """State of one complex-member abundance observation."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class ConstraintReplayReason(StrEnum):
    """Closed replay-verification outcomes for canonical result bytes."""

    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"
    NON_CANONICAL = "non_canonical"
    OVERSIZED = "oversized"


class ConstraintEstimateKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class GliomaConstraintProgram(StrEnum):
    """Glioma mechanism programs used to scope constraint integration."""

    RTK_PI3K_AKT_MTOR = "RTK_PI3K_AKT_MTOR"
    P53_DNA_REPAIR = "P53_DNA_REPAIR"
    IDH_HIF1A = "IDH_HIF1A"
    HYPOXIA_ANGIOGENESIS = "HYPOXIA_ANGIOGENESIS"
    CELL_CYCLE = "CELL_CYCLE"


class GliomaConstraintMemberRole(StrEnum):
    """Whether a member is required for a complex to remain active."""

    ESSENTIAL = "essential"
    SUPPORTING = "supporting"


class GliomaConstraintEvidenceState(StrEnum):
    """How a typed member measurement contributes to the fit."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class ConstraintOptimizationStatus(StrEnum):
    """Status of one deterministic typed complex fit."""

    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    NOT_EVALUABLE = "not_evaluable"


class GliomaComplexConstraintObservation(FrozenModel):
    """Explicit member evidence for the additive glioma constraint lane."""

    observation_id: Identifier
    complex_id: Identifier
    member_id: Identifier
    program: GliomaConstraintProgram | None = None
    member_role: GliomaConstraintMemberRole = GliomaConstraintMemberRole.SUPPORTING
    evidence_state: GliomaConstraintEvidenceState | None = None
    standardized_effect: float | None = Field(
        default=None, ge=-M0905_MAX_TYPED_EFFECT, le=M0905_MAX_TYPED_EFFECT
    )
    standard_error: float | None = Field(default=None, gt=0.0, le=M0905_MAX_TYPED_EFFECT)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    stoichiometric_weight: float = Field(default=1.0, gt=0.0, le=16.0)
    censoring_limit: float | None = Field(
        default=None, ge=-M0905_MAX_TYPED_EFFECT, le=M0905_MAX_TYPED_EFFECT
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def typed_observation_shape_is_closed(self) -> GliomaComplexConstraintObservation:
        typed = self.evidence_state is not None or self.standardized_effect is not None
        if not typed:
            if self.standard_error is not None or self.program is not None:
                raise ValueError(
                    "typed constraint measurements require an effect and evidence state"
                )
            return self
        if self.evidence_state is None:
            raise ValueError("typed constraint effects require evidence_state")
        active = self.evidence_state in {
            GliomaConstraintEvidenceState.OBSERVED,
            GliomaConstraintEvidenceState.LEFT_CENSORED,
        }
        if self.evidence_state is GliomaConstraintEvidenceState.OBSERVED:
            if (
                self.standardized_effect is None
                or self.standard_error is None
                or self.program is None
                or self.censoring_limit is not None
            ):
                raise ValueError(
                    "observed constraint evidence requires program, effect, and standard error"
                )
        elif self.evidence_state is GliomaConstraintEvidenceState.LEFT_CENSORED:
            if (
                self.censoring_limit is None
                or self.standard_error is None
                or self.program is None
                or self.standardized_effect is not None
            ):
                raise ValueError(
                    "left-censored constraint evidence requires program, limit, and standard error"
                )
        elif (
            self.standardized_effect is not None
            or self.standard_error is not None
            or self.censoring_limit is not None
            or self.program is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported constraint evidence cannot carry a value")
        if active and self.quality_weight <= 0.0:
            raise ValueError("active constraint evidence requires positive quality weight")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("typed constraint evidence must use the evidence role")
        return self


class MechanismConstraint(FrozenModel):
    constraint_id: Identifier
    version: SemanticVersion
    kind: MechanismConstraintKind
    expression: NonEmptyStr
    severity: ConstraintSeverity
    reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)


class ConstraintEvidenceObservation(FrozenModel):
    """Measured member abundance used by the complex constraint fit."""

    feature_id: Identifier
    state: ConstraintObservationState = ConstraintObservationState.OBSERVED
    value: float | None = None
    standard_error: float | None = Field(default=None, gt=0.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    censoring_limit: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_shape_is_closed(self) -> ConstraintEvidenceObservation:
        for name, number in (
            ("value", self.value),
            ("standard_error", self.standard_error),
            ("quality_weight", self.quality_weight),
            ("censoring_limit", self.censoring_limit),
        ):
            if number is not None and not isfinite(number):
                raise ValueError(f"{name} must be finite")
        if self.state is ConstraintObservationState.OBSERVED:
            if (
                self.value is None
                or self.standard_error is None
                or self.censoring_limit is not None
            ):
                raise ValueError("observed evidence requires value and standard error")
        elif self.state is ConstraintObservationState.LEFT_CENSORED:
            if (
                self.censoring_limit is None
                or self.standard_error is None
                or self.value is not None
            ):
                raise ValueError(
                    "left-censored evidence requires a censoring limit and standard error"
                )
        elif (
            self.value is not None
            or self.standard_error is not None
            or self.censoring_limit is not None
        ):
            raise ValueError("missing or unsupported evidence cannot carry numeric values")
        return self


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
    max_iterations: int = Field(default=128, gt=0, le=10_000)
    bootstrap_replicates: int = Field(
        default=M0905_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0905_MAX_BOOTSTRAP_REPLICATES,
    )

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
    evidence_count: int = Field(default=0, ge=0, le=M0905_MAX_TYPED_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
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
    ablation_effect: float | None = Field(default=None, ge=-1.0, le=1.0)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def violation_score_is_explicit(self) -> ConstraintSatisfactionReport:
        if self.status is ConstraintEvaluationStatus.VIOLATED and self.violation_score is None:
            raise ValueError("violated constraint requires a violation score")
        if (
            self.status is ConstraintEvaluationStatus.VIOLATED
            and self.severity is ConstraintSeverity.SOFT
            and self.ablation_effect is None
        ):
            raise ValueError("soft violation requires a quantified ablation effect")
        if (
            self.status is not ConstraintEvaluationStatus.VIOLATED
            and self.violation_score is not None
        ):
            raise ValueError("non-violated constraint cannot carry a violation score")
        if (
            self.status is not ConstraintEvaluationStatus.VIOLATED
            and self.ablation_effect is not None
        ):
            raise ValueError("non-violated constraint cannot carry an ablation effect")
        return self


class ConstraintOptimizationDiagnostic(FrozenModel):
    """Replay-visible optimization diagnostics for one typed complex."""

    diagnostic_id: Identifier
    complex_id: Identifier
    status: ConstraintOptimizationStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    objective_trace_digest: Sha256Digest | None = None
    model_family: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_shape_is_closed(self) -> ConstraintOptimizationDiagnostic:
        if self.status is ConstraintOptimizationStatus.CONVERGED:
            if self.objective_value is None or self.convergence_gap is None:
                raise ValueError("converged diagnostic requires objective and convergence gap")
        elif self.objective_value is not None and self.convergence_gap is None:
            raise ValueError("objective value requires a convergence gap")
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
    observations: tuple[ConstraintEvidenceObservation, ...] = Field(
        default=(), max_length=M0905_MAX_ESTIMATES
    )
    typed_observations: tuple[GliomaComplexConstraintObservation, ...] = Field(
        default=(), max_length=M0905_MAX_TYPED_OBSERVATIONS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> IntegrateComplexActivityConstraintsRequest:
        if self.baseline_result.media_type != M0905_BASELINE_MEDIA_TYPE:
            raise ValueError("constraint request must bind the provisional M09-04 result")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifact identifiers must be unique")
        observation_ids = tuple(item.feature_id for item in self.observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation feature ids must be unique")
        if any(item.feature_id not in set(artifact_ids) for item in self.observations):
            raise ValueError("observations must bind a declared source artifact")
        if self.typed_observations:
            typed_ids = tuple(item.observation_id for item in self.typed_observations)
            if len(typed_ids) != len(set(typed_ids)):
                raise ValueError("typed constraint observation identifiers must be unique")
            member_keys = tuple(
                (item.complex_id, item.member_id) for item in self.typed_observations
            )
            if len(member_keys) != len(set(member_keys)):
                raise ValueError("typed constraint member identifiers must be unique per complex")
        return self


class IntegrateComplexActivityConstraintsVerification(FrozenModel):
    """Replay result that distinguishes content, digest, and canonical-byte failures."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: ConstraintReplayReason

    @model_validator(mode="after")
    def outcome_is_closed(self) -> IntegrateComplexActivityConstraintsVerification:
        if self.verified != (self.content_verified and self.deterministic_verified):
            raise ValueError("verification outcome must equal both verification checks")
        if self.verified:
            if self.reason is not ConstraintReplayReason.VERIFIED or self.result_digest is None:
                raise ValueError("verified replay requires verified reason and digest")
        elif self.result_digest is not None:
            raise ValueError("failed replay cannot expose a trusted digest")
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
    diagnostics: tuple[ConstraintOptimizationDiagnostic, ...] = Field(default=(), max_length=256)
    model_family: NonEmptyStr | None = None
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
        if report_ids != policy_ids:
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
    "M0905_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0905_EVIDENCE_CLAIM",
    "M0905_GATE",
    "M0905_GLIOMA_MODEL_FAMILY",
    "M0905_MAX_BOOTSTRAP_REPLICATES",
    "M0905_MAX_CANONICAL_REQUEST_BYTES",
    "M0905_MAX_CANONICAL_RESULT_BYTES",
    "M0905_MAX_CONSTRAINTS",
    "M0905_MAX_ESTIMATES",
    "M0905_MAX_EVIDENCE",
    "M0905_MAX_REPORTS",
    "M0905_MAX_TYPED_EFFECT",
    "M0905_MAX_TYPED_OBSERVATIONS",
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
    "ConstraintEvidenceObservation",
    "ConstraintIntegratorPolicy",
    "ConstraintIntegratorStatus",
    "ConstraintObservationState",
    "ConstraintOptimizationDiagnostic",
    "ConstraintOptimizationStatus",
    "ConstraintReplayReason",
    "ConstraintSatisfactionReport",
    "ConstraintSeverity",
    "GliomaComplexConstraintObservation",
    "GliomaConstraintEvidenceState",
    "GliomaConstraintMemberRole",
    "GliomaConstraintProgram",
    "IntegrateComplexActivityConstraintsRequest",
    "IntegrateComplexActivityConstraintsResult",
    "IntegrateComplexActivityConstraintsVerification",
    "MechanismConstraint",
    "MechanismConstraintKind",
]
