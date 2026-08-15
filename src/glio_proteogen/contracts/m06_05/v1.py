"""Provisional M06-05 mechanism and constraint-integrator contracts.

The dossier defines hard/soft constraint behavior and ablation acceptance but
does not freeze an estimator handoff, operation, schema inventory, media type,
endpoint, or constraint catalogue.  This is reviewable scaffolding only; all
ABI names and bounds are explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m06_01.canonical import canonical_request_digest
from glio_proteogen.contracts.m06_01.v1 import (
    FormalProteinStateSchema,  # noqa: TC001
    FormalStateFeatureValue,  # noqa: TC001
)
from glio_proteogen.contracts.m06_05.canonical import result_payload_digest
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

# PROVISIONAL ABI: inferred solely from the M06-05 dossier slice.
M0605_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-05"
M0605_OPERATION: Final = "integrate_protein_abundance_constraints"
M0605_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0605_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-05+json"
M0605_PARENT: Final = "biomarker_panel"
M0605_OWNER: Final = "Computational biology"
M0605_SAFETY_CLASS: Final = "S2"
M0605_GATE: Final = "G2"
M0605_MAX_FEATURES: Final = 512
M0605_MAX_CONSTRAINTS: Final = 512
M0605_MAX_EVALUATIONS: Final = M0605_MAX_CONSTRAINTS
M0605_MAX_ABLATIONS: Final = M0605_MAX_CONSTRAINTS
M0605_MAX_EVIDENCE: Final = 32
M0605_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0605_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0605_ADVANCED_ESTIMATOR_MEDIA_TYPE: Final = (
    "application/vnd.glio-proteogen.m06-04+json"
)
_M0605_ABLATION_TOLERANCE: Final = 1e-12
M0605_EVIDENCE_CLAIM: Final = (
    "Caller-declared mechanism and constraint evidence; issuer authority is not authenticated."
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


class MechanismConstraintHardness(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ConstraintEvaluationOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ConstraintIntegrationStatus(StrEnum):
    INTEGRATED = "integrated"
    ABSTAINED = "abstained"


class ConstraintIntegrationReplayReason(StrEnum):
    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"



class MechanismConstraint(FrozenModel):
    """One explicit hard or soft constraint over formal-state features."""

    constraint_id: Identifier
    version: SemanticVersion
    kind: MechanismConstraintKind
    hardness: MechanismConstraintHardness
    expression: NonEmptyStr
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0605_MAX_FEATURES)
    weight: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_shape_is_closed(self) -> MechanismConstraint:
        if self.hardness is MechanismConstraintHardness.HARD and self.weight is not None:
            raise ValueError("hard constraint cannot carry a soft weight")
        if self.hardness is MechanismConstraintHardness.SOFT and self.weight is None:
            raise ValueError("soft constraint requires an explicit weight")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ValueError("constraint feature ids must be unique")
        return self


class MechanismConstraintSet(FrozenModel):
    """Reviewed constraint set; no hidden prior or graph traversal is implied."""

    constraint_set_id: Identifier
    version: SemanticVersion
    constraints: tuple[MechanismConstraint, ...] = Field(
        min_length=1,
        max_length=M0605_MAX_CONSTRAINTS,
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_set_is_closed(self) -> MechanismConstraintSet:
        identifiers = tuple(item.constraint_id for item in self.constraints)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("constraint ids must be unique")
        return self


class ConstraintEvaluation(FrozenModel):
    """One explicit evaluation with no silent hard-constraint coercion."""

    constraint_id: Identifier
    outcome: ConstraintEvaluationOutcome
    residual: float | None = Field(default=None, allow_inf_nan=False)
    effect_size: float | None = Field(default=None, allow_inf_nan=False)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evaluation_shape_is_closed(self) -> ConstraintEvaluation:
        if self.outcome in {
            ConstraintEvaluationOutcome.SATISFIED,
            ConstraintEvaluationOutcome.VIOLATED,
        } and self.residual is None and self.effect_size is None:
            raise ValueError("satisfied or violated evaluation requires a numeric result")
        if self.outcome in {
            ConstraintEvaluationOutcome.NOT_EVALUABLE,
            ConstraintEvaluationOutcome.ABSTAINED,
        } and (self.residual is not None or self.effect_size is not None):
            raise ValueError("non-evaluable evaluation cannot carry a numeric result")
        return self


class ConstraintAblationRecord(FrozenModel):
    """Required soft-constraint ablation evidence for prior-dominance review."""

    constraint_id: Identifier
    with_constraint_effect: float = Field(allow_inf_nan=False)
    without_constraint_effect: float = Field(allow_inf_nan=False)
    effect_delta: float = Field(allow_inf_nan=False)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def effect_delta_is_canonical(self) -> ConstraintAblationRecord:
        expected = self.with_constraint_effect - self.without_constraint_effect
        if abs(self.effect_delta - expected) > _M0605_ABLATION_TOLERANCE:
            raise ValueError("ablation effect delta must equal with-minus-without effect")
        return self


class ConstraintAwareEstimate(FrozenModel):
    """One aggregate constraint-aware estimate without raw content or parent emission."""

    feature_id: Identifier
    unit: NonEmptyStr
    estimate_value: float = Field(allow_inf_nan=False)
    lower_bound: float | None = Field(default=None, allow_inf_nan=False)
    upper_bound: float | None = Field(default=None, allow_inf_nan=False)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_bounds_are_closed(self) -> ConstraintAwareEstimate:
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError("constraint-aware estimate bounds are not ordered")
            if not self.lower_bound <= self.estimate_value <= self.upper_bound:
                raise ValueError("constraint-aware estimate must lie within its bounds")
        return self


class IntegrateProteinAbundanceConstraintsRequest(FrozenModel):
    """Provisional request ABI for the mechanism/constraint integrator."""

    operation: Literal["integrate_protein_abundance_constraints"] = M0605_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0605_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    state_schema: FormalProteinStateSchema
    feature_values: tuple[FormalStateFeatureValue, ...] = Field(
        min_length=1,
        max_length=M0605_MAX_FEATURES,
    )
    constraint_set: MechanismConstraintSet
    advanced_estimator_result: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0605_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> IntegrateProteinAbundanceConstraintsRequest:
        schema_features = {item.feature_id for item in self.state_schema.features}
        value_features = {item.feature_id for item in self.feature_values}
        if len(value_features) != len(self.feature_values):
            raise ValueError("constraint request feature values must be unique")
        if value_features != schema_features:
            raise ValueError("constraint request must cover the formal-state schema")
        if self.advanced_estimator_result.media_type != M0605_ADVANCED_ESTIMATOR_MEDIA_TYPE:
            raise ValueError(
                "constraint request must bind the provisional M06-04 result media type"
            )
        if not all(
            set(item.feature_ids) <= schema_features
            for item in self.constraint_set.constraints
        ):
            raise ValueError("constraint set references an unknown formal-state feature")
        return self


class IntegrateProteinAbundanceConstraintsResult(FrozenModel):
    """Provisional constraint-aware estimate and satisfaction report."""

    output_type: Literal["protein_abundance_constraint_integration"] = (
        "protein_abundance_constraint_integration"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0605_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IntegrateProteinAbundanceConstraintsRequest
    status: ConstraintIntegrationStatus
    estimates: tuple[ConstraintAwareEstimate, ...] = Field(
        default=(), max_length=M0605_MAX_FEATURES
    )
    evaluations: tuple[ConstraintEvaluation, ...] = Field(
        default=(), max_length=M0605_MAX_EVALUATIONS
    )
    ablations: tuple[ConstraintAblationRecord, ...] = Field(
        default=(), max_length=M0605_MAX_ABLATIONS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M0605_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0605_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> IntegrateProteinAbundanceConstraintsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        constraints = {item.constraint_id: item for item in self.request.constraint_set.constraints}
        evaluations = {item.constraint_id: item for item in self.evaluations}
        if len(evaluations) != len(self.evaluations):
            raise ValueError("result constraint evaluations must be unique")
        if set(evaluations) != set(constraints):
            raise ValueError("result must evaluate every declared constraint exactly once")
        soft_ids = {
            item.constraint_id
            for item in self.request.constraint_set.constraints
            if item.hardness is MechanismConstraintHardness.SOFT
        }
        ablation_ids = {item.constraint_id for item in self.ablations}
        if not soft_ids <= ablation_ids:
            raise ValueError("every soft constraint requires ablation evidence")
        if len(ablation_ids) != len(self.ablations):
            raise ValueError("result constraint ablations must be unique")
        if not ablation_ids <= soft_ids:
            raise ValueError("hard constraints cannot carry ablation evidence")
        estimate_ids = tuple(item.feature_id for item in self.estimates)
        schema_ids = {item.feature_id for item in self.request.state_schema.features}
        if len(estimate_ids) != len(set(estimate_ids)):
            raise ValueError("constraint-aware estimate feature ids must be unique")
        if not set(estimate_ids) <= schema_ids:
            raise ValueError("constraint-aware estimate references an unknown feature")
        hard_violated = any(
            constraints[item.constraint_id].hardness is MechanismConstraintHardness.HARD
            and item.outcome is ConstraintEvaluationOutcome.VIOLATED
            for item in self.evaluations
        )
        if self.status is ConstraintIntegrationStatus.INTEGRATED:
            if not self.estimates or hard_violated or self.abstention_reason is not None:
                raise ValueError("integrated result requires estimates and no hard violation")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("integrated result requires supported status")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates, a reason, and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class IntegrateProteinAbundanceConstraintsVerification(FrozenModel):
    """Replay verdict for one canonical result; all fields are provisional."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: ConstraintIntegrationReplayReason

    @model_validator(mode="after")
    def verification_is_closed(self) -> IntegrateProteinAbundanceConstraintsVerification:
        if self.verified != (self.content_verified and self.deterministic_verified):
            raise ValueError("verified must equal content and deterministic verification")
        if self.verified and self.reason is not ConstraintIntegrationReplayReason.VERIFIED:
            raise ValueError("verified replay requires verified reason")
        if not self.verified and self.result_digest is not None:
            raise ValueError("failed replay cannot expose a trusted result digest")
        return self


__all__ = [
    "M0605_ADVANCED_ESTIMATOR_MEDIA_TYPE",
    "M0605_CONTRACT_VERSION",
    "M0605_EVIDENCE_CLAIM",
    "M0605_GATE",
    "M0605_MAX_ABLATIONS",
    "M0605_MAX_CANONICAL_REQUEST_BYTES",
    "M0605_MAX_CANONICAL_RESULT_BYTES",
    "M0605_MAX_CONSTRAINTS",
    "M0605_MAX_EVALUATIONS",
    "M0605_MAX_EVIDENCE",
    "M0605_MAX_FEATURES",
    "M0605_MODULE_ID",
    "M0605_OPERATION",
    "M0605_OUTPUT_MEDIA_TYPE",
    "M0605_OWNER",
    "M0605_PARENT",
    "M0605_SAFETY_CLASS",
    "ConstraintAblationRecord",
    "ConstraintAwareEstimate",
    "ConstraintEvaluation",
    "ConstraintEvaluationOutcome",
    "ConstraintIntegrationStatus",
    "ConstraintIntegrationReplayReason",
    "IntegrateProteinAbundanceConstraintsRequest",
    "IntegrateProteinAbundanceConstraintsResult",
    "IntegrateProteinAbundanceConstraintsVerification",
    "MechanismConstraint",
    "MechanismConstraintHardness",
    "MechanismConstraintKind",
    "MechanismConstraintSet",
]
