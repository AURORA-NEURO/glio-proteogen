"""Contract-independent deterministic support-routing kernel for M01-07."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

_DUPLICATE_CRITERIA = "criterion identifiers must be unique"
_INVALID_TERMS = "term criteria require unique allowed terms"
_MISSING_NUMERIC_BOUND = "numeric criteria require at least one bound"
_INVERTED_NUMERIC_BOUNDS = "numeric criterion bounds must be ordered"
_MISSING_EXPECTED_BOOL = "boolean criteria require an expected value"
_INVALID_NOT_APPLICABLE = "required criteria cannot allow not-applicable evidence"


class EvidenceState(StrEnum):
    """Explicit state of one caller-declared support signal."""

    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class CriterionKind(StrEnum):
    """Small closed set of deterministic support predicates."""

    TERM_IN_SET = "term_in_set"
    NUMERIC_RANGE = "numeric_range"
    BOOLEAN_EQUALS = "boolean_equals"
    REQUIRED_PRESENT = "required_present"


class CriterionDecision(StrEnum):
    """Outcome of one configured support criterion."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class RouteDecision(StrEnum):
    """Aggregate routing outcome; neither value is a scientific finding."""

    SUPPORTED = "supported"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    """One already-authorized scalar or controlled-term value."""

    state: EvidenceState
    value: str | float | bool | None = None


@dataclass(frozen=True, slots=True)
class Criterion:
    """One reviewed support rule and its typed remediation path."""

    criterion_id: str
    signal_id: str
    kind: CriterionKind
    remediation_code: str
    required: bool = True
    allow_not_applicable: bool = False
    allowed_terms: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    expected_bool: bool | None = None


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """Deterministic result for one configured criterion."""

    criterion_id: str
    decision: CriterionDecision
    remediation_code: str | None


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Aggregate route plus all criterion-level explanations."""

    decision: RouteDecision
    review_required: bool
    criteria: tuple[CriterionResult, ...]
    remediation_codes: tuple[str, ...]


def route_support(
    criteria: tuple[Criterion, ...],
    evidence: dict[str, EvidenceValue],
) -> RoutingResult:
    """Evaluate configured support predicates without inferring absent evidence."""

    _validate_criteria(criteria)
    results = tuple(
        _evaluate(criterion, evidence.get(criterion.signal_id))
        for criterion in criteria
    )
    abstained = any(
        result.decision is not CriterionDecision.SUPPORTED
        for result in results
    )
    remediation = tuple(
        dict.fromkeys(
            result.remediation_code
            for result in results
            if result.remediation_code is not None
        )
    )
    return RoutingResult(
        decision=RouteDecision.ABSTAINED if abstained else RouteDecision.SUPPORTED,
        review_required=abstained,
        criteria=results,
        remediation_codes=remediation,
    )


def _evaluate(
    criterion: Criterion,
    evidence: EvidenceValue | None,
) -> CriterionResult:
    if (
        evidence is not None
        and evidence.state is EvidenceState.NOT_APPLICABLE
        and not criterion.required
        and criterion.allow_not_applicable
    ):
        decision = CriterionDecision.SUPPORTED
    elif criterion.kind is CriterionKind.REQUIRED_PRESENT:
        decision = (
            CriterionDecision.SUPPORTED
            if evidence is not None and evidence.state is EvidenceState.OBSERVED
            else CriterionDecision.INDETERMINATE
        )
    elif evidence is None or evidence.state is not EvidenceState.OBSERVED:
        decision = CriterionDecision.INDETERMINATE
    elif criterion.kind is CriterionKind.TERM_IN_SET:
        decision = _term_decision(evidence.value, criterion.allowed_terms)
    elif criterion.kind is CriterionKind.NUMERIC_RANGE:
        decision = _numeric_decision(evidence.value, criterion.minimum, criterion.maximum)
    else:
        decision = _boolean_decision(evidence.value, expected=criterion.expected_bool)
    return CriterionResult(
        criterion_id=criterion.criterion_id,
        decision=decision,
        remediation_code=(
            None if decision is CriterionDecision.SUPPORTED else criterion.remediation_code
        ),
    )


def _term_decision(value: object, allowed: tuple[str, ...]) -> CriterionDecision:
    if not isinstance(value, str):
        return CriterionDecision.INDETERMINATE
    return (
        CriterionDecision.SUPPORTED
        if value in allowed
        else CriterionDecision.UNSUPPORTED
    )


def _numeric_decision(
    value: object,
    minimum: float | None,
    maximum: float | None,
) -> CriterionDecision:
    if not isinstance(value, float) or not math.isfinite(value):
        return CriterionDecision.INDETERMINATE
    within = (minimum is None or value >= minimum) and (maximum is None or value <= maximum)
    return CriterionDecision.SUPPORTED if within else CriterionDecision.UNSUPPORTED


def _boolean_decision(
    value: object,
    *,
    expected: bool | None,
) -> CriterionDecision:
    if not isinstance(value, bool) or expected is None:
        return CriterionDecision.INDETERMINATE
    return CriterionDecision.SUPPORTED if value is expected else CriterionDecision.UNSUPPORTED


def _validate_criteria(criteria: tuple[Criterion, ...]) -> None:
    identifiers = [criterion.criterion_id for criterion in criteria]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(_DUPLICATE_CRITERIA)
    for criterion in criteria:
        if criterion.kind is CriterionKind.TERM_IN_SET:
            if not criterion.allowed_terms or len(criterion.allowed_terms) != len(
                set(criterion.allowed_terms)
            ):
                raise ValueError(_INVALID_TERMS)
        elif criterion.kind is CriterionKind.NUMERIC_RANGE:
            if criterion.minimum is None and criterion.maximum is None:
                raise ValueError(_MISSING_NUMERIC_BOUND)
            if (
                criterion.minimum is not None
                and criterion.maximum is not None
                and criterion.minimum > criterion.maximum
            ):
                raise ValueError(_INVERTED_NUMERIC_BOUNDS)
        elif criterion.kind is CriterionKind.BOOLEAN_EQUALS and criterion.expected_bool is None:
            raise ValueError(_MISSING_EXPECTED_BOOL)
        if criterion.required and criterion.allow_not_applicable:
            raise ValueError(_INVALID_NOT_APPLICABLE)


__all__ = [
    "Criterion",
    "CriterionDecision",
    "CriterionKind",
    "CriterionResult",
    "EvidenceState",
    "EvidenceValue",
    "RouteDecision",
    "RoutingResult",
    "route_support",
]
