"""Provisional M09-01 formal state and feature-schema contracts.

The dossier freezes formal state, units, domains, missingness, invariants,
constraints, compatibility and migration responsibility, but not the public
ABI, feature catalogue, operation, media type, or capacities.  All symbols
here are provisional scaffolding pending owner review.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m09_01.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M09-01 dossier slice.
M0901_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-01"
M0901_OPERATION: Final = "validate_complex_activity_formal_state"
M0901_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0901_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-01+json"
M0901_PARENT: Final = "complex_activity"
M0901_OWNER: Final = "Scientific engineering"
M0901_SAFETY_CLASS: Final = "S2"
M0901_GATE: Final = "G0"
M0901_PROVISIONAL_ABI: Final = True
M0901_MAX_FEATURES: Final = 1_024
M0901_MAX_INVARIANTS: Final = 1_024
M0901_MAX_CONSTRAINTS: Final = 1_024
M0901_MAX_COMPATIBILITY_RULES: Final = 256
M0901_MAX_MIGRATIONS: Final = 128
M0901_MAX_EVIDENCE: Final = 64
M0901_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0901_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0901_BENCHMARK_WARMUPS: Final = 3
M0901_BENCHMARK_ITERATIONS: Final = 10
M0901_MEAN_BUDGET_NS: Final = 2_000_000_000
M0901_P95_BUDGET_NS: Final = 3_000_000_000
M0901_EVIDENCE_CLAIM: Final = (
    "Caller-declared complex-activity formal-state evidence; issuer authority is not authenticated."
)


class ComplexActivityFeatureValueKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"
    VECTOR = "vector"


class ComplexActivityMissingness(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ComplexActivityInvariantSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ComplexActivityInvariantStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"


class ComplexActivityValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    ABSTAINED = "abstained"


class ComplexActivityFeatureDefinition(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    value_kind: ComplexActivityFeatureValueKind
    unit: NonEmptyStr
    allowed_missingness: tuple[ComplexActivityMissingness, ...] = Field(
        min_length=1,
        max_length=len(ComplexActivityMissingness),
    )
    domain_lower: float | None = None
    domain_upper: float | None = None
    allowed_categories: tuple[NonEmptyStr, ...] = Field(default=(), max_length=256)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @field_validator("allowed_missingness")
    @classmethod
    def missingness_is_unique(
        cls,
        values: tuple[ComplexActivityMissingness, ...],
    ) -> tuple[ComplexActivityMissingness, ...]:
        if len(values) != len(set(values)):
            raise ValueError("allowed missingness states must be unique")
        return tuple(sorted(values, key=lambda item: item.value))

    @field_validator("allowed_categories")
    @classmethod
    def categories_are_unique(cls, values: tuple[NonEmptyStr, ...]) -> tuple[NonEmptyStr, ...]:
        if len(values) != len(set(values)):
            raise ValueError("allowed categories must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def definition_is_closed(self) -> ComplexActivityFeatureDefinition:
        if (
            self.domain_lower is not None
            and self.domain_upper is not None
            and self.domain_lower > self.domain_upper
        ):
            raise ValueError("feature domain lower bound cannot exceed upper bound")
        if self.value_kind is ComplexActivityFeatureValueKind.CATEGORICAL:
            if not self.allowed_categories:
                raise ValueError("categorical feature requires allowed categories")
            if self.domain_lower is not None or self.domain_upper is not None:
                raise ValueError("categorical feature cannot declare numeric bounds")
        elif self.allowed_categories:
            raise ValueError("non-categorical feature cannot declare categories")
        return self


class ComplexActivityFeatureValue(FrozenModel):
    feature_id: Identifier
    state: ComplexActivityMissingness
    unit: NonEmptyStr
    scalar_value: float | None = None
    interval_lower: float | None = None
    interval_upper: float | None = None
    category: NonEmptyStr | None = None
    vector: tuple[float, ...] = Field(default=(), max_length=4_096)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> ComplexActivityFeatureValue:
        has_interval = self.interval_lower is not None or self.interval_upper is not None
        present = sum(
            (
                self.scalar_value is not None,
                has_interval,
                self.category is not None,
                bool(self.vector),
            )
        )
        if self.state is ComplexActivityMissingness.OBSERVED:
            if present != 1:
                raise ValueError("observed feature requires exactly one value representation")
            if has_interval and (
                self.interval_lower is None
                or self.interval_upper is None
                or self.interval_lower > self.interval_upper
            ):
                raise ValueError("observed interval requires ordered bounds")
            numeric_values = tuple(
                value
                for value in (
                    self.scalar_value,
                    self.interval_lower,
                    self.interval_upper,
                    *self.vector,
                )
                if value is not None
            )
            if not all(math.isfinite(value) for value in numeric_values):
                raise ValueError("observed numeric values must be finite")
        elif present:
            raise ValueError("non-observed feature cannot carry a value representation")
        return self


class ComplexActivityInvariant(FrozenModel):
    invariant_id: Identifier
    expression: NonEmptyStr
    severity: ComplexActivityInvariantSeverity
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0901_MAX_FEATURES)

    @field_validator("feature_ids")
    @classmethod
    def feature_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("invariant feature ids must be unique")
        return tuple(sorted(values))


class ComplexActivityConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0901_MAX_FEATURES)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @field_validator("feature_ids")
    @classmethod
    def constraint_feature_ids_are_unique(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("constraint feature ids must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def constraint_expression_is_bounded(self) -> ComplexActivityConstraint:
        if not self.expression.startswith("feature:"):
            raise ValueError("constraint expression must use the bounded feature language")
        return self


class ComplexActivityCompatibilityRule(FrozenModel):
    rule_id: Identifier
    source_version: SemanticVersion
    target_version: SemanticVersion
    expression: NonEmptyStr
    compatible: Literal[True] = True
    review_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def versions_are_distinct(self) -> ComplexActivityCompatibilityRule:
        if self.source_version == self.target_version:
            raise ValueError("compatibility source and target versions must differ")
        return self


class ComplexActivityMigrationRule(FrozenModel):
    source_version: SemanticVersion
    target_version: SemanticVersion
    mapped_feature_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0901_MAX_FEATURES,
    )
    lossy: bool
    review_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def versions_are_distinct(self) -> ComplexActivityMigrationRule:
        if self.source_version == self.target_version:
            raise ValueError("migration source and target versions must differ")
        return self


class FormalComplexActivityStateSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    features: tuple[ComplexActivityFeatureDefinition, ...] = Field(
        min_length=1,
        max_length=M0901_MAX_FEATURES,
    )
    invariants: tuple[ComplexActivityInvariant, ...] = Field(
        default=(),
        max_length=M0901_MAX_INVARIANTS,
    )
    constraints: tuple[ComplexActivityConstraint, ...] = Field(
        default=(),
        max_length=M0901_MAX_CONSTRAINTS,
    )
    compatibility_rules: tuple[ComplexActivityCompatibilityRule, ...] = Field(
        default=(),
        max_length=M0901_MAX_COMPATIBILITY_RULES,
    )
    migrations: tuple[ComplexActivityMigrationRule, ...] = Field(
        default=(),
        max_length=M0901_MAX_MIGRATIONS,
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)

    @model_validator(mode="after")
    def schema_is_closed(self) -> FormalComplexActivityStateSchema:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("schema feature ids must be unique")
        known = set(feature_ids)
        for invariant in self.invariants:
            if not set(invariant.feature_ids) <= known:
                raise ValueError("invariant references an unknown feature")
        for constraint in self.constraints:
            if not set(constraint.feature_ids) <= known:
                raise ValueError("constraint references an unknown feature")
        compatibility_pairs = {
            (rule.source_version, rule.target_version) for rule in self.compatibility_rules
        }
        if len(compatibility_pairs) != len(self.compatibility_rules):
            raise ValueError("compatibility rules must have unique version pairs")
        migration_pairs = {(rule.source_version, rule.target_version) for rule in self.migrations}
        if len(migration_pairs) != len(self.migrations):
            raise ValueError("migration rules must have unique version pairs")
        for migration in self.migrations:
            if not set(migration.mapped_feature_ids) <= known:
                raise ValueError("migration references an unknown feature")
        return self


class ComplexActivityInvariantResult(FrozenModel):
    invariant_id: Identifier
    status: ComplexActivityInvariantStatus
    message: NonEmptyStr


class ValidateComplexActivityStateRequest(FrozenModel):
    """Provisional request for schema validation and invariant execution."""

    operation: Literal["validate_complex_activity_formal_state"] = M0901_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0901_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    state_schema: FormalComplexActivityStateSchema
    values: tuple[ComplexActivityFeatureValue, ...] = Field(
        min_length=1,
        max_length=M0901_MAX_FEATURES,
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0901_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def values_match_schema(self) -> ValidateComplexActivityStateRequest:
        definitions = {item.feature_id: item for item in self.state_schema.features}
        values_by_id = {item.feature_id: item for item in self.values}
        if len(values_by_id) != len(self.values):
            raise ValueError("complex-activity feature values must be unique")
        if set(values_by_id) != set(definitions):
            raise ValueError("request must provide exactly the schema feature domain")
        for feature_id, value in values_by_id.items():
            definition = definitions[feature_id]
            if value.state not in definition.allowed_missingness:
                raise ValueError("feature value uses a disallowed missingness state")
            if value.unit != definition.unit:
                raise ValueError("feature value unit does not match schema unit")
            if value.category is not None and value.category not in definition.allowed_categories:
                raise ValueError("feature category is outside the declared domain")
            if value.state is ComplexActivityMissingness.OBSERVED:
                expected_kind = {
                    ComplexActivityFeatureValueKind.SCALAR: value.scalar_value is not None,
                    ComplexActivityFeatureValueKind.INTERVAL: (
                        value.interval_lower is not None and value.interval_upper is not None
                    ),
                    ComplexActivityFeatureValueKind.CATEGORICAL: value.category is not None,
                    ComplexActivityFeatureValueKind.VECTOR: bool(value.vector),
                }[definition.value_kind]
                if not expected_kind:
                    raise ValueError("feature value representation does not match schema kind")
            elif value.state not in definition.allowed_missingness:
                raise ValueError("feature value uses a disallowed missingness state")
            if value.scalar_value is not None and (
                (
                    definition.domain_lower is not None
                    and value.scalar_value < definition.domain_lower
                )
                or (
                    definition.domain_upper is not None
                    and value.scalar_value > definition.domain_upper
                )
            ):
                raise ValueError("scalar feature value is outside the declared domain")
            if value.interval_lower is not None and (
                (
                    definition.domain_lower is not None
                    and value.interval_lower < definition.domain_lower
                )
                or (
                    definition.domain_upper is not None
                    and value.interval_upper is not None
                    and value.interval_upper > definition.domain_upper
                )
            ):
                raise ValueError("interval feature value is outside the declared domain")
        return self


class ValidateComplexActivityStateResult(FrozenModel):
    """Provisional result carrying validation status and safety metadata."""

    output_type: Literal["complex_activity_formal_state_validation"] = (
        "complex_activity_formal_state_validation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0901_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ValidateComplexActivityStateRequest
    status: ComplexActivityValidationStatus
    support_decision: SupportDecision
    invariant_results: tuple[ComplexActivityInvariantResult, ...] = Field(
        default=(),
        max_length=M0901_MAX_INVARIANTS,
    )
    parent_target: Literal["complex_activity"] = M0901_PARENT
    emits_parent: Literal[False] = False
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0901_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ValidateComplexActivityStateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        statuses = {item.status for item in self.invariant_results}
        if self.status is ComplexActivityValidationStatus.VALID:
            if ComplexActivityInvariantStatus.VIOLATED in statuses:
                raise ValueError("valid result cannot contain a violated invariant")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("valid result requires supported status")
            if statuses != {ComplexActivityInvariantStatus.SATISFIED} and statuses:
                raise ValueError("valid result requires every invariant to be satisfied")
        if self.status is ComplexActivityValidationStatus.INVALID:
            if ComplexActivityInvariantStatus.VIOLATED not in statuses:
                raise ValueError("invalid result requires a violated invariant")
            if self.support_decision.status is SupportStatus.UNSUPPORTED:
                raise ValueError("unsupported evidence must abstain instead of becoming invalid")
        if (
            self.status is ComplexActivityValidationStatus.ABSTAINED
            and self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires unsupported or review-required status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0901_BENCHMARK_ITERATIONS",
    "M0901_BENCHMARK_WARMUPS",
    "M0901_CONTRACT_VERSION",
    "M0901_EVIDENCE_CLAIM",
    "M0901_GATE",
    "M0901_MAX_CANONICAL_REQUEST_BYTES",
    "M0901_MAX_CANONICAL_RESULT_BYTES",
    "M0901_MAX_COMPATIBILITY_RULES",
    "M0901_MAX_CONSTRAINTS",
    "M0901_MAX_EVIDENCE",
    "M0901_MAX_FEATURES",
    "M0901_MAX_INVARIANTS",
    "M0901_MAX_MIGRATIONS",
    "M0901_MEAN_BUDGET_NS",
    "M0901_MODULE_ID",
    "M0901_OPERATION",
    "M0901_OUTPUT_MEDIA_TYPE",
    "M0901_OWNER",
    "M0901_P95_BUDGET_NS",
    "M0901_PARENT",
    "M0901_PROVISIONAL_ABI",
    "M0901_SAFETY_CLASS",
    "ComplexActivityCompatibilityRule",
    "ComplexActivityConstraint",
    "ComplexActivityFeatureDefinition",
    "ComplexActivityFeatureValue",
    "ComplexActivityFeatureValueKind",
    "ComplexActivityInvariant",
    "ComplexActivityInvariantResult",
    "ComplexActivityInvariantSeverity",
    "ComplexActivityInvariantStatus",
    "ComplexActivityMigrationRule",
    "ComplexActivityMissingness",
    "ComplexActivityValidationStatus",
    "FormalComplexActivityStateSchema",
    "ValidateComplexActivityStateRequest",
    "ValidateComplexActivityStateResult",
]
