"""Small deterministic calculation kernel for M01-04 quality metrics.

The kernel deliberately knows nothing about Pydantic contracts, storage, raw formats, or biology.
It converts already-authorized scalar observations into finite metric values and typed states so
the public engine can remain a thin contract adapter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ScalarState(StrEnum):
    """Internal, contract-independent scalar outcome."""

    OBSERVED = "observed"
    MISSING = "missing"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ScalarStatus(StrEnum):
    """Contract-independent threshold classification."""

    PASS = "pass"  # noqa: S105 - metric classification, not a credential.
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ScalarObservation:
    """Minimal scalar material required by the deterministic calculators."""

    state: str
    value: float | None = None
    numerator: float | None = None
    denominator: float | None = None
    detection_limit: float | None = None
    expected_value: float | None = None
    matches_expected: bool | None = None


@dataclass(frozen=True, slots=True)
class ScalarResult:
    """Finite value or explicit abstention from one supported calculator."""

    state: ScalarState
    value: float | None


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Already-validated bounds supplied by one metric definition."""

    pass_min: float | None = None
    pass_max: float | None = None
    warning_min: float | None = None
    warning_max: float | None = None


def calculate_scalar(computation: str, observation: ScalarObservation) -> ScalarResult:
    """Calculate one bounded scalar without coercing missing or censored evidence to zero."""

    state = observation.state.casefold()
    explicit_states: dict[str, ScalarState] = {
        ScalarState.MISSING.value: ScalarState.MISSING,
        ScalarState.BELOW_DETECTION_LIMIT.value: ScalarState.BELOW_DETECTION_LIMIT,
        ScalarState.NOT_APPLICABLE.value: ScalarState.NOT_APPLICABLE,
    }
    explicit_state = explicit_states.get(state)
    if explicit_state is not None:
        return ScalarResult(explicit_state, None)
    if state not in {"observed", "provided"}:
        return ScalarResult(ScalarState.UNSUPPORTED, None)

    calculators = {
        "ratio": _ratio,
        "direct": _direct,
        "detection_margin": _detection_margin,
        "relative_error": _relative_error,
        "boolean_match": _boolean_match,
    }
    calculator = calculators.get(computation.casefold())
    return (
        ScalarResult(ScalarState.UNSUPPORTED, None)
        if calculator is None
        else calculator(observation)
    )


def classify_scalar(
    result: ScalarResult,
    direction: str,
    thresholds: Thresholds,
) -> ScalarStatus:
    """Classify one finite scalar against a closed, direction-aware threshold policy."""

    if result.state is not ScalarState.OBSERVED or result.value is None:
        return ScalarStatus.NOT_EVALUABLE
    classifiers = {
        "higher_is_better": _classify_higher,
        "lower_is_better": _classify_lower,
        "within_range": _classify_range,
    }
    classifier = classifiers.get(direction.casefold())
    return (
        ScalarStatus.NOT_EVALUABLE
        if classifier is None
        else classifier(result.value, thresholds)
    )


def _classify_higher(value: float, thresholds: Thresholds) -> ScalarStatus:
    if thresholds.pass_min is None:
        return ScalarStatus.NOT_EVALUABLE
    if value >= thresholds.pass_min:
        return ScalarStatus.PASS
    return (
        ScalarStatus.WARNING
        if thresholds.warning_min is not None and value >= thresholds.warning_min
        else ScalarStatus.FAIL
    )


def _classify_lower(value: float, thresholds: Thresholds) -> ScalarStatus:
    if thresholds.pass_max is None:
        return ScalarStatus.NOT_EVALUABLE
    if value <= thresholds.pass_max:
        return ScalarStatus.PASS
    return (
        ScalarStatus.WARNING
        if thresholds.warning_max is not None and value <= thresholds.warning_max
        else ScalarStatus.FAIL
    )


def _classify_range(value: float, thresholds: Thresholds) -> ScalarStatus:
    if thresholds.pass_min is None or thresholds.pass_max is None:
        return ScalarStatus.NOT_EVALUABLE
    if thresholds.pass_min <= value <= thresholds.pass_max:
        return ScalarStatus.PASS
    if thresholds.warning_min is None or thresholds.warning_max is None:
        return ScalarStatus.FAIL
    return (
        ScalarStatus.WARNING
        if thresholds.warning_min <= value <= thresholds.warning_max
        else ScalarStatus.FAIL
    )


def _ratio(observation: ScalarObservation) -> ScalarResult:
    if observation.numerator is None or observation.denominator is None:
        return ScalarResult(ScalarState.MISSING, None)
    if not _finite(observation.numerator) or not _finite(observation.denominator):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    if observation.numerator < 0 or observation.denominator <= 0:
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    value = observation.numerator / observation.denominator
    if value > 1:
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    return ScalarResult(ScalarState.OBSERVED, value)


def _direct(observation: ScalarObservation) -> ScalarResult:
    if observation.value is None:
        return ScalarResult(ScalarState.MISSING, None)
    if not _finite(observation.value):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    return ScalarResult(ScalarState.OBSERVED, observation.value)


def _detection_margin(observation: ScalarObservation) -> ScalarResult:
    if observation.value is None or observation.detection_limit is None:
        return ScalarResult(ScalarState.MISSING, None)
    if not _finite(observation.value) or not _finite(observation.detection_limit):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    if observation.detection_limit <= 0:
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    return ScalarResult(
        ScalarState.OBSERVED,
        observation.value / observation.detection_limit,
    )


def _relative_error(observation: ScalarObservation) -> ScalarResult:
    if observation.value is None or observation.expected_value is None:
        return ScalarResult(ScalarState.MISSING, None)
    if not _finite(observation.value) or not _finite(observation.expected_value):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    if observation.expected_value == 0:
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    return ScalarResult(
        ScalarState.OBSERVED,
        abs(observation.value - observation.expected_value) / abs(observation.expected_value),
    )


def _boolean_match(observation: ScalarObservation) -> ScalarResult:
    if observation.matches_expected is None:
        return ScalarResult(ScalarState.MISSING, None)
    return ScalarResult(
        ScalarState.OBSERVED,
        1.0 if observation.matches_expected else 0.0,
    )


def _finite(value: float) -> bool:
    return math.isfinite(value)


__all__ = [
    "ScalarObservation",
    "ScalarResult",
    "ScalarState",
    "ScalarStatus",
    "Thresholds",
    "calculate_scalar",
    "classify_scalar",
]
