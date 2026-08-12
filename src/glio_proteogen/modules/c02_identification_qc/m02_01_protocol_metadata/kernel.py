"""Contract-independent deterministic conformance kernel for M02-01."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

_UNDEFINED_OBSERVATION = "observations reference undefined fields"
_DUPLICATE_FIELDS = "field definitions must have unique field identifiers"
_DUPLICATE_OBSERVATIONS = "observations must have unique field identifiers"
_INVALID_CARDINALITY = "field cardinality is invalid"
_REQUIRED_MINIMUM = "required fields need positive minimum cardinality"
_REQUIRED_NA = "required fields cannot allow not-applicable"
_DUPLICATE_RULES = "rule identifiers must be unique"
_UNDEFINED_RULE_FIELD = "rules reference undefined fields"
_INVALID_TERMS = "term rules require unique allowed terms"
_MISSING_BOUND = "numeric rules require a bound"
_INVERTED_BOUNDS = "numeric rule bounds must be ordered"
_MISSING_BOOLEAN = "boolean rules require an expected value"


class ObservationState(StrEnum):
    """Explicit caller-declared state; absence is never a negative finding."""

    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    CONFLICTING = "conflicting"


class RuleKind(StrEnum):
    """Small closed compatibility-rule set."""

    TERM_IN_SET = "term_in_set"
    NUMERIC_RANGE = "numeric_range"
    BOOLEAN_EQUALS = "boolean_equals"


class ResultState(StrEnum):
    """Field or aggregate deterministic conformance state."""

    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    field_id: str
    required: bool
    min_items: int = 0
    max_items: int = 1
    unit_id: str | None = None
    allow_not_applicable: bool = False


@dataclass(frozen=True, slots=True)
class FieldObservation:
    field_id: str
    state: ObservationState
    values: tuple[str | int | float | bool, ...] = ()
    unit_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProtocolRule:
    rule_id: str
    field_id: str
    kind: RuleKind
    reason_code: str
    allowed_terms: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    expected_bool: bool | None = None


@dataclass(frozen=True, slots=True)
class FieldResult:
    field_id: str
    state: ResultState
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    state: ResultState
    quarantined: bool
    human_review_required: bool
    fields: tuple[FieldResult, ...]
    reason_codes: tuple[str, ...]


def validate_protocol(
    fields: tuple[FieldDefinition, ...],
    observations: tuple[FieldObservation, ...],
    rules: tuple[ProtocolRule, ...],
) -> ValidationResult:
    """Validate explicit metadata without coercion, conversion, or imputation."""

    definitions = _definitions_by_id(fields)
    observed = _observations_by_id(observations)
    _validate_definitions(fields)
    _validate_rules(rules, definitions)
    unknown = set(observed) - set(definitions)
    if unknown:
        raise ValueError(_UNDEFINED_OBSERVATION)
    grouped: dict[str, list[ProtocolRule]] = {
        field_id: [] for field_id in definitions
    }
    for rule in rules:
        grouped[rule.field_id].append(rule)

    results: list[FieldResult] = []
    for field_id in sorted(definitions):
        definition = definitions[field_id]
        observation = observed.get(field_id)
        reasons = _field_reasons(definition, observation)
        if not reasons and observation is not None:
            reasons.extend(_rule_reasons(observation, tuple(grouped[field_id])))
        state = _field_state(observation, reasons)
        results.append(FieldResult(field_id, state, tuple(sorted(set(reasons)))))

    aggregate = _aggregate(tuple(item.state for item in results))
    reason_codes = tuple(
        sorted({reason for item in results for reason in item.reason_codes})
    )
    return ValidationResult(
        state=aggregate,
        quarantined=aggregate is not ResultState.CONFORMANT,
        human_review_required=(
            aggregate is not ResultState.CONFORMANT
            or any(
                observation.state is ObservationState.CONFLICTING
                for observation in observations
            )
        ),
        fields=tuple(results),
        reason_codes=reason_codes,
    )


def _definitions_by_id(
    items: tuple[FieldDefinition, ...],
) -> dict[str, FieldDefinition]:
    mapped = {item.field_id: item for item in items}
    if len(mapped) != len(items):
        raise ValueError(_DUPLICATE_FIELDS)
    return mapped


def _observations_by_id(
    items: tuple[FieldObservation, ...],
) -> dict[str, FieldObservation]:
    mapped = {item.field_id: item for item in items}
    if len(mapped) != len(items):
        raise ValueError(_DUPLICATE_OBSERVATIONS)
    return mapped


def _validate_definitions(fields: tuple[FieldDefinition, ...]) -> None:
    for field in fields:
        if field.min_items < 0 or field.max_items < 1 or field.min_items > field.max_items:
            raise ValueError(_INVALID_CARDINALITY)
        if field.required and field.min_items == 0:
            raise ValueError(_REQUIRED_MINIMUM)
        if field.required and field.allow_not_applicable:
            raise ValueError(_REQUIRED_NA)


def _validate_rules(
    rules: tuple[ProtocolRule, ...], definitions: Mapping[str, FieldDefinition]
) -> None:
    identifiers = [rule.rule_id for rule in rules]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(_DUPLICATE_RULES)
    for rule in rules:
        if rule.field_id not in definitions:
            raise ValueError(_UNDEFINED_RULE_FIELD)
        if rule.kind is RuleKind.TERM_IN_SET:
            if not rule.allowed_terms or len(rule.allowed_terms) != len(set(rule.allowed_terms)):
                raise ValueError(_INVALID_TERMS)
        elif rule.kind is RuleKind.NUMERIC_RANGE:
            if rule.minimum is None and rule.maximum is None:
                raise ValueError(_MISSING_BOUND)
            if (
                rule.minimum is not None
                and rule.maximum is not None
                and rule.minimum > rule.maximum
            ):
                raise ValueError(_INVERTED_BOUNDS)
        elif rule.expected_bool is None:
            raise ValueError(_MISSING_BOOLEAN)


def _field_reasons(
    definition: FieldDefinition, observation: FieldObservation | None
) -> list[str]:
    if observation is None:
        return ["required_field_absent"] if definition.required else []
    if observation.state in {
        ObservationState.MISSING,
        ObservationState.UNKNOWN,
        ObservationState.CONFLICTING,
    }:
        return [f"field_{observation.state.value}"]
    if observation.state is ObservationState.NOT_APPLICABLE:
        return [] if definition.allow_not_applicable else ["not_applicable_not_allowed"]
    count = len(observation.values)
    reasons: list[str] = []
    if count < definition.min_items or count > definition.max_items:
        reasons.append("cardinality_mismatch")
    if definition.unit_id != observation.unit_id:
        reasons.append("unit_mismatch")
    return reasons


def _rule_reasons(
    observation: FieldObservation, rules: tuple[ProtocolRule, ...]
) -> list[str]:
    return [
        rule.reason_code
        for rule in rules
        if any(not _matches(value, rule) for value in observation.values)
    ]


def _matches(value: object, rule: ProtocolRule) -> bool:
    if rule.kind is RuleKind.TERM_IN_SET:
        return isinstance(value, str) and value in rule.allowed_terms
    if rule.kind is RuleKind.BOOLEAN_EQUALS:
        return isinstance(value, bool) and value is rule.expected_bool
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    number = float(value)
    return (
        math.isfinite(number)
        and (rule.minimum is None or number >= rule.minimum)
        and (rule.maximum is None or number <= rule.maximum)
    )


def _field_state(
    observation: FieldObservation | None, reasons: list[str]
) -> ResultState:
    if observation is None or (
        observation.state
        in {ObservationState.MISSING, ObservationState.UNKNOWN, ObservationState.CONFLICTING}
    ):
        return ResultState.INDETERMINATE if reasons else ResultState.CONFORMANT
    return ResultState.NONCONFORMANT if reasons else ResultState.CONFORMANT


def _aggregate(states: tuple[ResultState, ...]) -> ResultState:
    if ResultState.NONCONFORMANT in states:
        return ResultState.NONCONFORMANT
    if ResultState.INDETERMINATE in states:
        return ResultState.INDETERMINATE
    return ResultState.CONFORMANT


__all__ = [
    "FieldDefinition",
    "FieldObservation",
    "FieldResult",
    "ObservationState",
    "ProtocolRule",
    "ResultState",
    "RuleKind",
    "ValidationResult",
    "validate_protocol",
]
