"""Provisional M07-05 mechanism and constraint-integrator contracts.

The dossier specifies explicit hard/soft constraint behavior and ablation
acceptance, but does not freeze operation names, schemas, media types,
endpoints, feature catalogues, or mechanism vocabularies.  This is reviewable
scaffolding only; every ABI symbol is provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M07-05 dossier slice.
M0705_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-05"
M0705_OPERATION: Final = "integrate_proteotype_constraints"
M0705_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0705_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-05+json"
M0705_PARENT: Final = "proteotype"
M0705_OWNER: Final = "Bioinformatics"
M0705_SAFETY_CLASS: Final = "S2"
M0705_GATE: Final = "G2"
M0705_MAX_FEATURES: Final = 512
M0705_MAX_CONSTRAINTS: Final = 512
M0705_MAX_EVALUATIONS: Final = M0705_MAX_CONSTRAINTS
M0705_MAX_ABLATIONS: Final = M0705_MAX_CONSTRAINTS
M0705_MAX_EVIDENCE: Final = 32
M0705_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0705_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M0705_ABLATION_TOLERANCE: Final = 1e-12
M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-04+json"
M0705_EVIDENCE_CLAIM: Final = (
    "Caller-declared proteotype constraint evidence; issuer authority is not authenticated."
)


class ProteotypeConstraintKind(StrEnum):
    BIOLOGICAL_PRIOR = "biological_prior"
    ONTOLOGY = "ontology"
    GRAPH = "graph"
    TOPOLOGY = "topology"
    CONSERVATION = "conservation"
    CHEMISTRY = "chemistry"
    ASSAY_PHYSICS = "assay_physics"
    DISEASE = "disease"


class ProteotypeConstraintHardness(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ProteotypeConstraintEvaluationOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ProteotypeConstraintIntegrationStatus(StrEnum):
    INTEGRATED = "integrated"
    ABSTAINED = "abstained"


class ProteotypeMechanismConstraint(FrozenModel):
    """One explicit hard or soft constraint over proteotype features."""

    constraint_id: Identifier
    version: SemanticVersion
    kind: ProteotypeConstraintKind
    hardness: ProteotypeConstraintHardness
    expression: NonEmptyStr
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0705_MAX_FEATURES)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_shape_is_closed(self) -> ProteotypeMechanismConstraint:
        if self.hardness is ProteotypeConstraintHardness.HARD and self.weight is not None:
            raise ValueError("hard constraint cannot carry a soft weight")
        if self.hardness is ProteotypeConstraintHardness.SOFT and self.weight is None:
            raise ValueError("soft constraint requires an explicit weight")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ValueError("constraint feature ids must be unique")
        return self


class ProteotypeMechanismConstraintSet(FrozenModel):
    """Reviewed constraint set; no hidden prior or graph traversal is implied."""

    constraint_set_id: Identifier
    version: SemanticVersion
    constraints: tuple[ProteotypeMechanismConstraint, ...] = Field(
        min_length=1,
        max_length=M0705_MAX_CONSTRAINTS,
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_set_is_closed(self) -> ProteotypeMechanismConstraintSet:
        identifiers = tuple(item.constraint_id for item in self.constraints)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("constraint ids must be unique")
        return self


class ProteotypeConstraintEvaluation(FrozenModel):
    constraint_id: Identifier
    outcome: ProteotypeConstraintEvaluationOutcome
    residual: float | None = None
    effect_size: float | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)


class ProteotypeConstraintAblation(FrozenModel):
    """Soft-constraint ablation evidence required to detect prior dominance."""

    constraint_id: Identifier
    with_constraint_effect: float
    without_constraint_effect: float
    effect_delta: float
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)

    @model_validator(mode="after")
    def effect_delta_is_canonical(self) -> ProteotypeConstraintAblation:
        expected = self.with_constraint_effect - self.without_constraint_effect
        if abs(self.effect_delta - expected) > _M0705_ABLATION_TOLERANCE:
            raise ValueError("ablation effect delta must equal with-minus-without effect")
        return self


class ProteotypeConstraintAwareEstimate(FrozenModel):
    feature_id: Identifier
    unit: NonEmptyStr
    estimate_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_bounds_are_closed(self) -> ProteotypeConstraintAwareEstimate:
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError("constraint-aware estimate bounds are not ordered")
            if not self.lower_bound <= self.estimate_value <= self.upper_bound:
                raise ValueError("constraint-aware estimate must lie within its bounds")
        return self


class IntegrateProteotypeConstraintsRequest(FrozenModel):
    """Provisional request ABI for the M07-05 constraint integrator."""

    operation: Literal["integrate_proteotype_constraints"] = M0705_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0705_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    constraint_set: ProteotypeMechanismConstraintSet
    advanced_estimator_result: ArtifactReference
    feature_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0705_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> IntegrateProteotypeConstraintsRequest:
        if self.representation_result.media_type != "application/vnd.glio-proteogen.m07-02+json":
            raise ValueError("request must bind the provisional M07-02 representation result")
        if self.advanced_estimator_result.media_type != M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M07-04 result media type")
        if self.representation_result.artifact_id == self.advanced_estimator_result.artifact_id:
            raise ValueError("representation and estimator handoffs must remain distinct")
        return self


class IntegrateProteotypeConstraintsResult(FrozenModel):
    """Provisional constraint-aware estimate and satisfaction report."""

    output_type: Literal["proteotype_constraint_integration"] = (
        "proteotype_constraint_integration"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0705_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IntegrateProteotypeConstraintsRequest
    status: ProteotypeConstraintIntegrationStatus
    estimates: tuple[ProteotypeConstraintAwareEstimate, ...] = Field(
        default=(), max_length=M0705_MAX_FEATURES
    )
    evaluations: tuple[ProteotypeConstraintEvaluation, ...] = Field(
        default=(), max_length=M0705_MAX_EVALUATIONS
    )
    ablations: tuple[ProteotypeConstraintAblation, ...] = Field(
        default=(), max_length=M0705_MAX_ABLATIONS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0705_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0705_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> IntegrateProteotypeConstraintsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        constraints = {item.constraint_id: item for item in self.request.constraint_set.constraints}
        evaluations = {item.constraint_id: item for item in self.evaluations}
        if set(evaluations) != set(constraints):
            raise ValueError("result must evaluate every declared constraint exactly once")
        soft_ids = {
            item.constraint_id
            for item in self.request.constraint_set.constraints
            if item.hardness is ProteotypeConstraintHardness.SOFT
        }
        if not soft_ids <= {item.constraint_id for item in self.ablations}:
            raise ValueError("every soft constraint requires ablation evidence")
        hard_violated = any(
            constraints[item.constraint_id].hardness is ProteotypeConstraintHardness.HARD
            and item.outcome is ProteotypeConstraintEvaluationOutcome.VIOLATED
            for item in self.evaluations
        )
        if self.status is ProteotypeConstraintIntegrationStatus.INTEGRATED:
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


__all__ = [
    "M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE",
    "M0705_CONTRACT_VERSION",
    "M0705_EVIDENCE_CLAIM",
    "M0705_GATE",
    "M0705_MAX_ABLATIONS",
    "M0705_MAX_CANONICAL_REQUEST_BYTES",
    "M0705_MAX_CANONICAL_RESULT_BYTES",
    "M0705_MAX_CONSTRAINTS",
    "M0705_MAX_EVALUATIONS",
    "M0705_MAX_EVIDENCE",
    "M0705_MAX_FEATURES",
    "M0705_MODULE_ID",
    "M0705_OPERATION",
    "M0705_OUTPUT_MEDIA_TYPE",
    "M0705_OWNER",
    "M0705_PARENT",
    "M0705_SAFETY_CLASS",
    "IntegrateProteotypeConstraintsRequest",
    "IntegrateProteotypeConstraintsResult",
    "ProteotypeConstraintAblation",
    "ProteotypeConstraintAwareEstimate",
    "ProteotypeConstraintEvaluation",
    "ProteotypeConstraintEvaluationOutcome",
    "ProteotypeConstraintHardness",
    "ProteotypeConstraintIntegrationStatus",
    "ProteotypeConstraintKind",
    "ProteotypeMechanismConstraint",
    "ProteotypeMechanismConstraintSet",
]
