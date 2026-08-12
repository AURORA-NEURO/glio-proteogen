"""Contract-independent deterministic rule kernel for M01-05.

This module evaluates configured scalar predicates. It does not parse raw data, learn detector
weights, or treat missing evidence as a clear result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class SignalState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class Predicate(StrEnum):
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    WITHIN_RANGE = "within_range"
    OUTSIDE_RANGE = "outside_range"


class FlagDecision(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    EXCLUDE = "exclude"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class Signal:
    state: SignalState
    value: float | bool | None = None


@dataclass(frozen=True, slots=True)
class Rule:
    signal_id: str
    predicate: Predicate
    threshold: float | bool
    triggered_posterior: float
    upper_threshold: float | None = None
    required: bool = True
    exclusion_eligible: bool = True


@dataclass(frozen=True, slots=True)
class Detection:
    posterior: float | None
    decision: FlagDecision
    triggered_rule_indexes: tuple[int, ...]
    missing_signal_ids: tuple[str, ...]


def evaluate_rules(
    rules: tuple[Rule, ...],
    signals: dict[str, Signal],
    *,
    clear_posterior: float,
    review_threshold: float,
    exclusion_threshold: float,
) -> Detection:
    """Evaluate one target/class rule set with max-only posterior aggregation."""

    missing = tuple(
        sorted(
            {
                rule.signal_id
                for rule in rules
                if rule.required
                and (
                    rule.signal_id not in signals
                    or signals[rule.signal_id].state is not SignalState.OBSERVED
                )
            }
        )
    )
    if missing:
        return Detection(None, FlagDecision.NOT_EVALUABLE, (), missing)
    triggered = tuple(
        index
        for index, rule in enumerate(rules)
        if _triggered(rule, signals.get(rule.signal_id))
    )
    posterior = (
        max(rules[index].triggered_posterior for index in triggered)
        if triggered
        else clear_posterior
    )
    maximum_sources = tuple(
        rules[index]
        for index in triggered
        if rules[index].triggered_posterior == posterior
    )
    exclusion_authorized = bool(maximum_sources) and all(
        rule.exclusion_eligible for rule in maximum_sources
    )
    if exclusion_authorized and posterior >= exclusion_threshold:
        decision = FlagDecision.EXCLUDE
    elif posterior >= review_threshold:
        decision = FlagDecision.REVIEW
    else:
        decision = FlagDecision.CLEAR
    return Detection(posterior, decision, triggered, ())


def _triggered(rule: Rule, signal: Signal | None) -> bool:  # noqa: PLR0911
    if signal is None or signal.state is not SignalState.OBSERVED or signal.value is None:
        return False
    observed, threshold = signal.value, rule.threshold
    if isinstance(observed, bool) or isinstance(threshold, bool):
        if not isinstance(observed, bool) or not isinstance(threshold, bool):
            return False
        return observed == threshold if rule.predicate is Predicate.EQUAL else observed != threshold
    if not math.isfinite(observed) or not math.isfinite(threshold):
        return False
    if rule.predicate in {Predicate.WITHIN_RANGE, Predicate.OUTSIDE_RANGE}:
        upper = rule.upper_threshold
        if upper is None or not math.isfinite(upper):
            return False
        within = threshold <= observed <= upper
        return within if rule.predicate is Predicate.WITHIN_RANGE else not within
    return {
        Predicate.GREATER_THAN_OR_EQUAL: observed >= threshold,
        Predicate.LESS_THAN_OR_EQUAL: observed <= threshold,
        Predicate.EQUAL: observed == threshold,
        Predicate.NOT_EQUAL: observed != threshold,
    }[rule.predicate]


__all__ = [
    "Detection",
    "FlagDecision",
    "Predicate",
    "Rule",
    "Signal",
    "SignalState",
    "evaluate_rules",
]
