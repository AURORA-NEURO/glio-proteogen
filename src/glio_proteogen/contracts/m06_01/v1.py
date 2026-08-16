"""Provisional M06-01 formal-state and feature-schema contracts.

The authoritative dossier defines M06-01's behavior and acceptance criteria,
but it does not freeze an operation, request/result names, schema inventory,
media type, endpoint, or feature catalogue.  Every ABI symbol in this file is
therefore provisional and must be reviewed when the upstream M06 handoff is
available.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m06_01.canonical import (
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

# PROVISIONAL ABI: inferred from the dossier's M06-01 behavioral brief.
M0601_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-01"
M0601_OPERATION: Final = "validate_formal_protein_state"
M0601_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0601_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-01+json"
M0601_PARENT: Final = "biomarker_panel"
M0601_OWNER: Final = "Clinical science"
M0601_SAFETY_CLASS: Final = "S2"
M0601_GATE: Final = "G0"
M0601_MAX_FEATURES: Final = 512
M0601_MAX_INVARIANTS: Final = 512
M0601_MAX_MIGRATIONS: Final = 64
M0601_MAX_EVIDENCE: Final = 32
M0601_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0601_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0601_EVIDENCE_CLAIM: Final = (
    "Caller-declared formal-state schema evidence; issuer authority is not authenticated."
)


class FormalStateFeatureValueKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"
    VECTOR = "vector"


class FormalStateMissingness(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class FormalStateInvariantSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class FormalStateInvariantStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"


class FormalStateValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    ABSTAINED = "abstained"


class FormalStateFeatureDefinition(FrozenModel):
    """One typed feature domain in the provisional formal-state schema."""

    feature_id: Identifier
    version: SemanticVersion
    value_kind: FormalStateFeatureValueKind
    unit: NonEmptyStr
    allowed_missingness: tuple[FormalStateMissingness, ...] = Field(
        min_length=1,
        max_length=len(FormalStateMissingness),
    )
    domain_lower: float | None = None
    domain_upper: float | None = None
    allowed_categories: tuple[NonEmptyStr, ...] = Field(default=(), max_length=256)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0601_MAX_EVIDENCE)

    @field_validator("allowed_missingness")
    @classmethod
    def missingness_is_unique(
        cls,
        values: tuple[FormalStateMissingness, ...],
    ) -> tuple[FormalStateMissingness, ...]:
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
    def definition_is_closed(self) -> FormalStateFeatureDefinition:
        if (
            self.domain_lower is not None
            and self.domain_upper is not None
            and self.domain_lower > self.domain_upper
        ):
            raise ValueError("feature domain lower bound cannot exceed upper bound")
        if self.value_kind is FormalStateFeatureValueKind.CATEGORICAL:
            if not self.allowed_categories:
                raise ValueError("categorical feature requires allowed categories")
            if self.domain_lower is not None or self.domain_upper is not None:
                raise ValueError("categorical feature cannot declare numeric bounds")
        elif self.allowed_categories:
            raise ValueError("non-categorical feature cannot declare categories")
        return self


class FormalStateFeatureValue(FrozenModel):
    """One value or explicit missingness state; no missing-as-negative shortcut."""

    feature_id: Identifier
    state: FormalStateMissingness
    unit: NonEmptyStr
    scalar_value: float | None = None
    interval_lower: float | None = None
    interval_upper: float | None = None
    category: NonEmptyStr | None = None
    vector: tuple[float, ...] = Field(default=(), max_length=4096)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> FormalStateFeatureValue:
        has_interval = self.interval_lower is not None or self.interval_upper is not None
        present = sum(
            (
                self.scalar_value is not None,
                has_interval,
                self.category is not None,
                bool(self.vector),
            )
        )
        if self.state is FormalStateMissingness.OBSERVED:
            if present != 1:
                raise ValueError("observed feature requires exactly one value representation")
            if has_interval and (
                self.interval_lower is None
                or self.interval_upper is None
                or self.interval_lower > self.interval_upper
            ):
                raise ValueError("observed interval requires ordered lower and upper bounds")
        elif present:
            raise ValueError("non-observed feature cannot carry a value representation")
        return self


class FormalStateInvariant(FrozenModel):
    """Executable-invariant declaration; execution is owned by the runtime layer."""

    invariant_id: Identifier
    expression: NonEmptyStr
    severity: FormalStateInvariantSeverity
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0601_MAX_FEATURES)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0601_MAX_EVIDENCE)

    @field_validator("feature_ids")
    @classmethod
    def feature_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("invariant feature ids must be unique")
        return tuple(sorted(values))


class FormalStateMigrationRule(FrozenModel):
    """Versioned migration declaration with an explicit review requirement."""

    source_version: SemanticVersion
    target_version: SemanticVersion
    mapped_feature_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0601_MAX_FEATURES,
    )
    lossy: bool
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def versions_are_distinct(self) -> FormalStateMigrationRule:
        if self.source_version == self.target_version:
            raise ValueError("migration source and target versions must differ")
        return self


class FormalProteinStateSchema(FrozenModel):
    """Formal state schema plus invariant and migration declarations."""

    schema_id: Identifier
    version: SemanticVersion
    features: tuple[FormalStateFeatureDefinition, ...] = Field(
        min_length=1,
        max_length=M0601_MAX_FEATURES,
    )
    invariants: tuple[FormalStateInvariant, ...] = Field(
        default=(), max_length=M0601_MAX_INVARIANTS
    )
    migrations: tuple[FormalStateMigrationRule, ...] = Field(
        default=(), max_length=M0601_MAX_MIGRATIONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def schema_is_closed(self) -> FormalProteinStateSchema:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("schema feature ids must be unique")
        known = set(feature_ids)
        for invariant in self.invariants:
            if not set(invariant.feature_ids) <= known:
                raise ValueError("invariant references an unknown feature")
        return self


class FormalStateInvariantResult(FrozenModel):
    invariant_id: Identifier
    status: FormalStateInvariantStatus
    message: NonEmptyStr


class ValidateFormalProteinStateRequest(FrozenModel):
    """Provisional request ABI for schema validation and invariant execution."""

    operation: Literal["validate_formal_protein_state"] = M0601_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0601_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    state_schema: FormalProteinStateSchema
    values: tuple[FormalStateFeatureValue, ...] = Field(
        min_length=1,
        max_length=M0601_MAX_FEATURES,
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0601_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def values_match_schema(self) -> ValidateFormalProteinStateRequest:
        definitions = {item.feature_id: item for item in self.state_schema.features}
        values_by_id = {item.feature_id: item for item in self.values}
        if len(values_by_id) != len(self.values):
            raise ValueError("request feature values must be unique")
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
        return self


class ValidateFormalProteinStateResult(FrozenModel):
    """Provisional result carrying validation status, invariants and safety metadata."""

    output_type: Literal["formal_protein_state_validation"] = "formal_protein_state_validation"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0601_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ValidateFormalProteinStateRequest
    status: FormalStateValidationStatus
    support_decision: SupportDecision
    invariant_results: tuple[FormalStateInvariantResult, ...] = Field(
        default=(), max_length=M0601_MAX_INVARIANTS
    )
    parent_target: Literal["biomarker_panel"] = M0601_PARENT
    emits_parent: Literal[False] = False
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0601_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ValidateFormalProteinStateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        statuses = {item.status for item in self.invariant_results}
        if self.status is FormalStateValidationStatus.VALID:
            if FormalStateInvariantStatus.VIOLATED in statuses:
                raise ValueError("valid result cannot contain a violated invariant")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("valid result requires supported status")
        if (
            self.status is FormalStateValidationStatus.ABSTAINED
            and self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires unsupported or review-required status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0601_CONTRACT_VERSION",
    "M0601_EVIDENCE_CLAIM",
    "M0601_GATE",
    "M0601_MAX_CANONICAL_REQUEST_BYTES",
    "M0601_MAX_CANONICAL_RESULT_BYTES",
    "M0601_MAX_EVIDENCE",
    "M0601_MAX_FEATURES",
    "M0601_MAX_INVARIANTS",
    "M0601_MAX_MIGRATIONS",
    "M0601_MODULE_ID",
    "M0601_OPERATION",
    "M0601_OUTPUT_MEDIA_TYPE",
    "M0601_OWNER",
    "M0601_PARENT",
    "M0601_SAFETY_CLASS",
    "FormalProteinStateSchema",
    "FormalStateFeatureDefinition",
    "FormalStateFeatureValue",
    "FormalStateFeatureValueKind",
    "FormalStateInvariant",
    "FormalStateInvariantResult",
    "FormalStateInvariantSeverity",
    "FormalStateInvariantStatus",
    "FormalStateMigrationRule",
    "FormalStateMissingness",
    "FormalStateValidationStatus",
    "ValidateFormalProteinStateRequest",
    "ValidateFormalProteinStateResult",
]
