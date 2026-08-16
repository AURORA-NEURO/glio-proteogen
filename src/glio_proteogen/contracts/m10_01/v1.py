"""Provisional M10-01 formal state and feature-schema contracts.

The dossier freezes formal-state responsibilities and safety boundaries, but
not the public ABI, feature catalogue, operation, media type, or capacities.
All symbols here are provisional scaffolding pending owner review.
"""

from __future__ import annotations

import re
from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m10_01.canonical import (
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

M1001_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-01"
M1001_OPERATION: Final = "validate_protein_rna_discordance_formal_state"
M1001_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1001_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-01+json"
M1001_PARENT: Final = "protein_rna_discordance"
M1001_OWNER: Final = "Computational biology"
M1001_SAFETY_CLASS: Final = "S2"
M1001_GATE: Final = "G0"
M1001_PROVISIONAL_ABI: Final = True
M1001_MAX_FEATURES: Final = 512
M1001_MAX_INVARIANTS: Final = 512
M1001_MAX_MIGRATIONS: Final = 64
M1001_MAX_EVIDENCE: Final = 32
M1001_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1001_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1001_EVIDENCE_CLAIM: Final = (
    "Caller-declared protein-RNA discordance formal-state evidence; "
    "issuer authority is not authenticated."
)
M1001_MAX_EXPRESSION_BYTES: Final = 512
M1001_MAX_FEATURE_VECTOR_LENGTH: Final = 4096
M1001_SUPPORTED_EXPRESSION: Final = (
    "Expressions are declarative only: present(<feature>), missing(<feature>), "
    "<feature> <operator> <number>, or <feature> between <lower> and <upper>."
)

_IDENTIFIER_TOKEN: Final = r"[a-zA-Z][a-zA-Z0-9._:-]{0,127}"  # noqa: S105
_COMPARISON_PATTERN: Final = re.compile(
    rf"^(?P<feature>{_IDENTIFIER_TOKEN})\s*(?P<operator>==|>=|<=|>|<)\s*"
    r"(?P<value>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)
_BETWEEN_PATTERN: Final = re.compile(
    rf"^(?P<feature>{_IDENTIFIER_TOKEN})\s+between\s+"
    r"(?P<lower>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+and\s+"
    r"(?P<upper>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)
_PRESENCE_PATTERN: Final = re.compile(
    rf"^(?P<kind>present|missing)\((?P<feature>{_IDENTIFIER_TOKEN})\)$"
)


class ProteinRnaFeatureValueKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"
    VECTOR = "vector"


class ProteinRnaMissingness(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ProteinRnaInvariantSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ProteinRnaInvariantStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"


class ProteinRnaValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    ABSTAINED = "abstained"


class ProteinRnaReplayReason(StrEnum):
    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    NON_CANONICAL = "non_canonical"
    DIGEST_MISMATCH = "digest_mismatch"
    OVERSIZED = "oversized"


class ProteinRnaFeatureDefinition(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    value_kind: ProteinRnaFeatureValueKind
    unit: NonEmptyStr
    allowed_missingness: tuple[ProteinRnaMissingness, ...] = Field(
        min_length=1,
        max_length=len(ProteinRnaMissingness),
    )
    domain_lower: float | None = None
    domain_upper: float | None = None
    allowed_categories: tuple[NonEmptyStr, ...] = Field(default=(), max_length=256)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1001_MAX_EVIDENCE)

    @field_validator("allowed_missingness")
    @classmethod
    def missingness_is_unique(
        cls,
        values: tuple[ProteinRnaMissingness, ...],
    ) -> tuple[ProteinRnaMissingness, ...]:
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
    def definition_is_closed(self) -> ProteinRnaFeatureDefinition:
        if (
            self.domain_lower is not None
            and self.domain_upper is not None
            and self.domain_lower > self.domain_upper
        ):
            raise ValueError("feature domain lower bound cannot exceed upper bound")
        if self.value_kind is ProteinRnaFeatureValueKind.CATEGORICAL:
            if not self.allowed_categories:
                raise ValueError("categorical feature requires allowed categories")
            if self.domain_lower is not None or self.domain_upper is not None:
                raise ValueError("categorical feature cannot declare numeric bounds")
        elif self.allowed_categories:
            raise ValueError("non-categorical feature cannot declare categories")
        if self.value_kind is ProteinRnaFeatureValueKind.VECTOR and (
            self.domain_lower is not None or self.domain_upper is not None
        ):
            raise ValueError("vector feature cannot declare scalar numeric bounds")
        return self


class ProteinRnaFeatureValue(FrozenModel):
    feature_id: Identifier
    state: ProteinRnaMissingness
    unit: NonEmptyStr
    scalar_value: float | None = None
    interval_lower: float | None = None
    interval_upper: float | None = None
    category: NonEmptyStr | None = None
    vector: tuple[float, ...] = Field(default=(), max_length=M1001_MAX_FEATURE_VECTOR_LENGTH)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> ProteinRnaFeatureValue:
        has_interval = self.interval_lower is not None or self.interval_upper is not None
        present = sum(
            (
                self.scalar_value is not None,
                has_interval,
                self.category is not None,
                bool(self.vector),
            )
        )
        if self.state is ProteinRnaMissingness.OBSERVED:
            if present != 1:
                raise ValueError("observed feature requires exactly one value representation")
            if has_interval and (
                self.interval_lower is None
                or self.interval_upper is None
                or self.interval_lower > self.interval_upper
            ):
                raise ValueError("observed interval requires ordered bounds")
            for numeric in (
                self.scalar_value,
                self.interval_lower,
                self.interval_upper,
                *self.vector,
            ):
                if numeric is not None and not isfinite(numeric):
                    raise ValueError("feature values must be finite")
        elif present:
            raise ValueError("non-observed feature cannot carry a value representation")
        return self


class ProteinRnaInvariant(FrozenModel):
    invariant_id: Identifier
    expression: NonEmptyStr
    severity: ProteinRnaInvariantSeverity
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1001_MAX_FEATURES)

    @field_validator("feature_ids")
    @classmethod
    def feature_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("invariant feature ids must be unique")
        return tuple(sorted(values))

    @field_validator("expression")
    @classmethod
    def expression_is_declarative(cls, value: NonEmptyStr) -> NonEmptyStr:
        if len(value.encode("utf-8")) > M1001_MAX_EXPRESSION_BYTES:
            raise ValueError("invariant expression exceeds the bounded byte limit")
        if not (
            _COMPARISON_PATTERN.fullmatch(value)
            or _BETWEEN_PATTERN.fullmatch(value)
            or _PRESENCE_PATTERN.fullmatch(value)
        ):
            raise ValueError(M1001_SUPPORTED_EXPRESSION)
        return value


class ProteinRnaMigrationRule(FrozenModel):
    source_version: SemanticVersion
    target_version: SemanticVersion
    mapped_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1001_MAX_FEATURES)
    lossy: bool
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def versions_are_distinct(self) -> ProteinRnaMigrationRule:
        if self.source_version == self.target_version:
            raise ValueError("migration source and target versions must differ")
        if len(set(self.mapped_feature_ids)) != len(self.mapped_feature_ids):
            raise ValueError("migration feature ids must be unique")
        return self


class FormalProteinRnaDiscordanceStateSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    features: tuple[ProteinRnaFeatureDefinition, ...] = Field(
        min_length=1,
        max_length=M1001_MAX_FEATURES,
    )
    invariants: tuple[ProteinRnaInvariant, ...] = Field(
        default=(),
        max_length=M1001_MAX_INVARIANTS,
    )
    migrations: tuple[ProteinRnaMigrationRule, ...] = Field(
        default=(),
        max_length=M1001_MAX_MIGRATIONS,
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1001_MAX_EVIDENCE)

    @model_validator(mode="after")
    def schema_is_closed(self) -> FormalProteinRnaDiscordanceStateSchema:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("schema feature ids must be unique")
        invariant_ids = tuple(item.invariant_id for item in self.invariants)
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("schema invariant ids must be unique")
        known = set(feature_ids)
        if any(not set(item.feature_ids) <= known for item in self.invariants):
            raise ValueError("invariant references an unknown feature")
        if any(not set(item.mapped_feature_ids) <= known for item in self.migrations):
            raise ValueError("migration references an unknown feature")
        return self


class ProteinRnaInvariantResult(FrozenModel):
    invariant_id: Identifier
    status: ProteinRnaInvariantStatus
    message: NonEmptyStr


class ValidateProteinRnaDiscordanceStateRequest(FrozenModel):
    """Provisional request for schema validation and invariant execution."""

    operation: Literal["validate_protein_rna_discordance_formal_state"] = M1001_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1001_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    state_schema: FormalProteinRnaDiscordanceStateSchema
    values: tuple[ProteinRnaFeatureValue, ...] = Field(
        min_length=1,
        max_length=M1001_MAX_FEATURES,
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M1001_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def values_match_schema(self) -> ValidateProteinRnaDiscordanceStateRequest:
        definitions = {item.feature_id: item for item in self.state_schema.features}
        values_by_id = {item.feature_id: item for item in self.values}
        if len(values_by_id) != len(self.values):
            raise ValueError("protein-RNA feature values must be unique")
        if set(values_by_id) != set(definitions):
            raise ValueError("request must provide exactly the schema feature domain")
        for feature_id, value in values_by_id.items():
            definition = definitions[feature_id]
            if value.state not in definition.allowed_missingness:
                raise ValueError("feature value uses a disallowed missingness state")
            if value.unit != definition.unit:
                raise ValueError("feature value unit does not match schema unit")
            if value.state is ProteinRnaMissingness.OBSERVED:
                expected = {
                    ProteinRnaFeatureValueKind.SCALAR: value.scalar_value is not None,
                    ProteinRnaFeatureValueKind.INTERVAL: (
                        value.interval_lower is not None and value.interval_upper is not None
                    ),
                    ProteinRnaFeatureValueKind.CATEGORICAL: value.category is not None,
                    ProteinRnaFeatureValueKind.VECTOR: bool(value.vector),
                }[definition.value_kind]
                if not expected:
                    raise ValueError("feature value representation does not match schema kind")
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


class ValidateProteinRnaDiscordanceStateResult(FrozenModel):
    """Provisional result carrying validation status and safety metadata."""

    output_type: Literal["protein_rna_discordance_formal_state_validation"] = (
        "protein_rna_discordance_formal_state_validation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1001_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ValidateProteinRnaDiscordanceStateRequest
    status: ProteinRnaValidationStatus
    support_decision: SupportDecision
    invariant_results: tuple[ProteinRnaInvariantResult, ...] = Field(
        default=(),
        max_length=M1001_MAX_INVARIANTS,
    )
    parent_target: Literal["protein_rna_discordance"] = M1001_PARENT
    emits_parent: Literal[False] = False
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1001_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ValidateProteinRnaDiscordanceStateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        hard_invariant_ids = {
            item.invariant_id
            for item in self.request.state_schema.invariants
            if item.severity is ProteinRnaInvariantSeverity.ERROR
        }
        soft_violation = any(
            item.status is ProteinRnaInvariantStatus.VIOLATED
            and item.invariant_id not in hard_invariant_ids
            for item in self.invariant_results
        )
        if self.status is ProteinRnaValidationStatus.VALID:
            if any(
                item.status is ProteinRnaInvariantStatus.VIOLATED
                and item.invariant_id in hard_invariant_ids
                for item in self.invariant_results
            ):
                raise ValueError("valid result cannot contain a violated hard invariant")
            if self.support_decision.status is not SupportStatus.SUPPORTED and not soft_violation:
                raise ValueError("valid result requires supported status")
        if (
            self.status is ProteinRnaValidationStatus.ABSTAINED
            and self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires unsupported or review-required status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class ValidateProteinRnaDiscordanceStateVerification(FrozenModel):
    """Replay verdict that distinguishes content, digest, and size failures."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    reason: ProteinRnaReplayReason
    result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def verdict_is_closed(self) -> ValidateProteinRnaDiscordanceStateVerification:
        if self.verified != (self.content_verified and self.deterministic_verified):
            raise ValueError("verification verdict does not match its component checks")
        if self.verified and (
            self.reason is not ProteinRnaReplayReason.VERIFIED or self.result_digest is None
        ):
            raise ValueError("verified replay requires a digest and verified reason")
        if not self.verified and self.result_digest is not None:
            raise ValueError("failed replay cannot publish a result digest")
        return self


__all__ = [
    "M1001_CONTRACT_VERSION",
    "M1001_EVIDENCE_CLAIM",
    "M1001_GATE",
    "M1001_MAX_CANONICAL_REQUEST_BYTES",
    "M1001_MAX_CANONICAL_RESULT_BYTES",
    "M1001_MAX_EVIDENCE",
    "M1001_MAX_FEATURES",
    "M1001_MAX_INVARIANTS",
    "M1001_MAX_MIGRATIONS",
    "M1001_MODULE_ID",
    "M1001_OPERATION",
    "M1001_OUTPUT_MEDIA_TYPE",
    "M1001_OWNER",
    "M1001_PARENT",
    "M1001_PROVISIONAL_ABI",
    "M1001_SAFETY_CLASS",
    "FormalProteinRnaDiscordanceStateSchema",
    "ProteinRnaFeatureDefinition",
    "ProteinRnaFeatureValue",
    "ProteinRnaFeatureValueKind",
    "ProteinRnaInvariant",
    "ProteinRnaInvariantResult",
    "ProteinRnaInvariantSeverity",
    "ProteinRnaInvariantStatus",
    "ProteinRnaMigrationRule",
    "ProteinRnaMissingness",
    "ProteinRnaReplayReason",
    "ProteinRnaValidationStatus",
    "ValidateProteinRnaDiscordanceStateRequest",
    "ValidateProteinRnaDiscordanceStateResult",
    "ValidateProteinRnaDiscordanceStateVerification",
]
