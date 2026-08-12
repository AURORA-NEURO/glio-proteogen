"""Focused tests for the pure M01-05 rule kernel."""

from __future__ import annotations

from typing import Final

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.kernel import (
    Detection,
    FlagDecision,
    Predicate,
    Rule,
    Signal,
    SignalState,
    evaluate_rules,
)

_CLEAR_POSTERIOR: Final = 0.01
_HIGH_POSTERIOR: Final = 0.95
_VERY_HIGH_POSTERIOR: Final = 0.99


def _evaluate(
    rules: tuple[Rule, ...],
    signals: dict[str, Signal],
) -> Detection:
    return evaluate_rules(
        rules,
        signals,
        clear_posterior=_CLEAR_POSTERIOR,
        review_threshold=0.5,
        exclusion_threshold=0.9,
    )


def test_no_trigger_uses_configured_clear_posterior() -> None:
    rule = Rule("signal.a", Predicate.GREATER_THAN_OR_EQUAL, 0.8, 0.95)

    result = _evaluate((rule,), {"signal.a": Signal(SignalState.OBSERVED, 0.2)})

    assert result.posterior == _CLEAR_POSTERIOR
    assert result.decision is FlagDecision.CLEAR
    assert result.triggered_rule_indexes == ()


def test_missing_required_signal_is_not_evaluable_never_clear() -> None:
    rule = Rule(
        "signal.required",
        Predicate.EQUAL,
        threshold=True,
        triggered_posterior=_HIGH_POSTERIOR,
    )

    result = _evaluate((rule,), {})

    assert result.posterior is None
    assert result.decision is FlagDecision.NOT_EVALUABLE
    assert result.missing_signal_ids == ("signal.required",)


def test_triggered_rules_aggregate_by_max_configured_posterior() -> None:
    rules = (
        Rule("signal.a", Predicate.GREATER_THAN_OR_EQUAL, 0.5, 0.6),
        Rule("signal.b", Predicate.LESS_THAN_OR_EQUAL, 0.5, 0.95),
    )
    signals = {
        "signal.a": Signal(SignalState.OBSERVED, 0.8),
        "signal.b": Signal(SignalState.OBSERVED, 0.2),
    }

    result = _evaluate(rules, signals)

    assert result.posterior == _HIGH_POSTERIOR
    assert result.triggered_rule_indexes == (0, 1)
    assert result.decision is FlagDecision.EXCLUDE


def test_high_posterior_reviews_when_rule_is_not_exclusion_eligible() -> None:
    rule = Rule(
        "signal.a",
        Predicate.EQUAL,
        threshold=True,
        triggered_posterior=0.99,
        exclusion_eligible=False,
    )

    result = _evaluate(
        (rule,),
        {"signal.a": Signal(SignalState.OBSERVED, value=True)},
    )

    assert result.decision is FlagDecision.REVIEW


def test_only_maximum_posterior_rules_can_authorize_exclusion() -> None:
    rules = (
        Rule(
            "signal.eligible-low",
            Predicate.EQUAL,
            threshold=True,
            triggered_posterior=0.6,
            exclusion_eligible=True,
        ),
        Rule(
            "signal.ineligible-high",
            Predicate.EQUAL,
            threshold=True,
            triggered_posterior=_VERY_HIGH_POSTERIOR,
            exclusion_eligible=False,
        ),
    )
    signals = {
        "signal.eligible-low": Signal(SignalState.OBSERVED, value=True),
        "signal.ineligible-high": Signal(SignalState.OBSERVED, value=True),
    }

    result = _evaluate(rules, signals)

    assert result.posterior == _VERY_HIGH_POSTERIOR
    assert result.decision is FlagDecision.REVIEW


@pytest.mark.parametrize(
    ("posterior", "decision"),
    [
        (0.49, FlagDecision.CLEAR),
        (0.5, FlagDecision.REVIEW),
        (0.9, FlagDecision.EXCLUDE),
    ],
)
def test_decision_thresholds_are_inclusive(
    posterior: float,
    decision: FlagDecision,
) -> None:
    rule = Rule(
        "signal.a",
        Predicate.EQUAL,
        threshold=True,
        triggered_posterior=posterior,
    )
    result = _evaluate((rule,), {"signal.a": Signal(SignalState.OBSERVED, value=True)})

    assert result.decision is decision


@pytest.mark.parametrize("state", [SignalState.MISSING, SignalState.NOT_APPLICABLE])
def test_explicit_nonobserved_required_signal_is_not_evaluable(state: SignalState) -> None:
    rule = Rule("signal.a", Predicate.EQUAL, threshold=True, triggered_posterior=0.9)

    result = _evaluate((rule,), {"signal.a": Signal(state)})

    assert result.decision is FlagDecision.NOT_EVALUABLE


def test_optional_missing_signal_does_not_trigger() -> None:
    rule = Rule(
        "signal.optional",
        Predicate.EQUAL,
        threshold=True,
        triggered_posterior=0.9,
        required=False,
    )

    result = _evaluate((rule,), {})

    assert result.decision is FlagDecision.CLEAR


@pytest.mark.parametrize(
    ("predicate", "observed", "threshold", "triggered"),
    [
        (Predicate.GREATER_THAN_OR_EQUAL, 2.0, 2.0, True),
        (Predicate.LESS_THAN_OR_EQUAL, 2.0, 2.0, True),
        (Predicate.EQUAL, 2.0, 2.0, True),
        (Predicate.NOT_EQUAL, 2.0, 3.0, True),
        (Predicate.EQUAL, False, False, True),
        (Predicate.NOT_EQUAL, False, True, True),
    ],
)
def test_supported_predicates_are_deterministic(
    predicate: Predicate,
    observed: object,
    threshold: object,
    *,
    triggered: bool,
) -> None:
    assert isinstance(observed, float | bool)
    assert isinstance(threshold, float | bool)
    rule = Rule("signal.a", predicate, threshold=threshold, triggered_posterior=0.6)
    result = _evaluate(
        (rule,),
        {"signal.a": Signal(SignalState.OBSERVED, value=observed)},
    )

    assert bool(result.triggered_rule_indexes) is triggered


def test_nonfinite_and_mismatched_types_never_trigger() -> None:
    rules = (
        Rule("signal.nan", Predicate.EQUAL, 1.0, 0.9, required=False),
        Rule(
            "signal.mixed",
            Predicate.EQUAL,
            threshold=True,
            triggered_posterior=0.9,
            required=False,
        ),
    )
    signals = {
        "signal.nan": Signal(SignalState.OBSERVED, float("nan")),
        "signal.mixed": Signal(SignalState.OBSERVED, 1.0),
    }

    result = _evaluate(rules, signals)

    assert result.decision is FlagDecision.CLEAR
    assert result.triggered_rule_indexes == ()
