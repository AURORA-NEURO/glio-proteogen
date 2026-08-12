"""Focused tests for the contract-independent M01-04 calculation kernel."""

from __future__ import annotations

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.calculations import (
    ScalarObservation,
    ScalarResult,
    ScalarState,
    ScalarStatus,
    Thresholds,
    calculate_scalar,
    classify_scalar,
)

_RATIO_VALUE = 0.9
_DIRECT_VALUE = 1.25
_MARGIN_VALUE = 5.0


def test_ratio_calculation_is_exact() -> None:
    result = calculate_scalar(
        "ratio",
        ScalarObservation(state="observed", numerator=9, denominator=10),
    )

    assert result.state is ScalarState.OBSERVED
    assert result.value == _RATIO_VALUE


def test_direct_calculation_preserves_finite_scalar() -> None:
    result = calculate_scalar(
        "direct",
        ScalarObservation(state="provided", value=_DIRECT_VALUE),
    )

    assert result.state is ScalarState.OBSERVED
    assert result.value == _DIRECT_VALUE


@pytest.mark.parametrize(
    ("matches", "value"),
    [(True, 1.0), (False, 0.0)],
)
def test_sample_context_is_explicit(*, matches: bool, value: float) -> None:
    result = calculate_scalar(
        "boolean_match",
        ScalarObservation(state="observed", matches_expected=matches),
    )

    assert result.state is ScalarState.OBSERVED
    assert result.value == value


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("missing", ScalarState.MISSING),
        ("below_detection_limit", ScalarState.BELOW_DETECTION_LIMIT),
        ("not_applicable", ScalarState.NOT_APPLICABLE),
        ("unsupported", ScalarState.UNSUPPORTED),
    ],
)
def test_nonobserved_states_never_become_zero(state: str, expected: ScalarState) -> None:
    result = calculate_scalar("direct", ScalarObservation(state=state))

    assert result.state is expected
    assert result.value is None


@pytest.mark.parametrize(
    "observation",
    [
        ScalarObservation(state="observed", numerator=None, denominator=10),
        ScalarObservation(state="observed", numerator=1, denominator=0),
        ScalarObservation(state="observed", numerator=-1, denominator=10),
        ScalarObservation(state="observed", numerator=11, denominator=10),
        ScalarObservation(state="observed", numerator=float("inf"), denominator=10),
    ],
)
def test_invalid_ratio_material_abstains(observation: ScalarObservation) -> None:
    result = calculate_scalar("ratio", observation)

    assert result.value is None
    assert result.state in {ScalarState.MISSING, ScalarState.UNSUPPORTED}


def test_missing_boolean_and_unknown_computation_abstain() -> None:
    missing = calculate_scalar("boolean_match", ScalarObservation(state="observed"))
    unknown = calculate_scalar("novel_model", ScalarObservation(state="observed", value=1))

    assert (missing.state, missing.value) == (ScalarState.MISSING, None)
    assert (unknown.state, unknown.value) == (ScalarState.UNSUPPORTED, None)


def test_detection_margin_and_relative_error_are_dimensionless() -> None:
    margin = calculate_scalar(
        "detection_margin",
        ScalarObservation(state="observed", value=10, detection_limit=2),
    )
    error = calculate_scalar(
        "relative_error",
        ScalarObservation(state="observed", value=9, expected_value=10),
    )

    assert margin.value == _MARGIN_VALUE
    assert error.value == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("computation", "observation"),
    [
        ("detection_margin", ScalarObservation(state="observed", value=1)),
        (
            "detection_margin",
            ScalarObservation(state="observed", value=1, detection_limit=0),
        ),
        ("relative_error", ScalarObservation(state="observed", value=1)),
        (
            "relative_error",
            ScalarObservation(state="observed", value=1, expected_value=0),
        ),
    ],
)
def test_invalid_specialized_material_abstains(
    computation: str,
    observation: ScalarObservation,
) -> None:
    result = calculate_scalar(computation, observation)

    assert result.state in {ScalarState.MISSING, ScalarState.UNSUPPORTED}
    assert result.value is None


def test_nonfinite_direct_value_is_unsupported() -> None:
    result = calculate_scalar(
        "detection_limit",
        ScalarObservation(state="observed", value=float("nan")),
    )

    assert result.state is ScalarState.UNSUPPORTED
    assert result.value is None


@pytest.mark.parametrize(
    ("direction", "thresholds", "values", "statuses"),
    [
        (
            "higher_is_better",
            Thresholds(pass_min=0.9, warning_min=0.8),
            (0.95, 0.85, 0.7),
            (ScalarStatus.PASS, ScalarStatus.WARNING, ScalarStatus.FAIL),
        ),
        (
            "lower_is_better",
            Thresholds(pass_max=0.1, warning_max=0.2),
            (0.05, 0.15, 0.3),
            (ScalarStatus.PASS, ScalarStatus.WARNING, ScalarStatus.FAIL),
        ),
        (
            "within_range",
            Thresholds(pass_min=0.9, pass_max=1.1, warning_min=0.8, warning_max=1.2),
            (1.0, 1.15, 1.3),
            (ScalarStatus.PASS, ScalarStatus.WARNING, ScalarStatus.FAIL),
        ),
    ],
)
def test_direction_aware_thresholds(
    direction: str,
    thresholds: Thresholds,
    values: tuple[float, ...],
    statuses: tuple[ScalarStatus, ...],
) -> None:
    observed = tuple(
        classify_scalar(ScalarResult(ScalarState.OBSERVED, value), direction, thresholds)
        for value in values
    )

    assert observed == statuses


def test_classifier_abstains_for_missing_policy_or_value() -> None:
    missing = classify_scalar(
        ScalarResult(ScalarState.MISSING, None),
        "higher_is_better",
        Thresholds(pass_min=0.9, warning_min=0.8),
    )
    incomplete = classify_scalar(
        ScalarResult(ScalarState.OBSERVED, 1),
        "within_range",
        Thresholds(),
    )
    unknown = classify_scalar(
        ScalarResult(ScalarState.OBSERVED, 1),
        "novel_direction",
        Thresholds(),
    )

    assert missing is ScalarStatus.NOT_EVALUABLE
    assert incomplete is ScalarStatus.NOT_EVALUABLE
    assert unknown is ScalarStatus.NOT_EVALUABLE


def test_absent_warning_band_falls_directly_to_fail() -> None:
    higher = classify_scalar(
        ScalarResult(ScalarState.OBSERVED, 0.5),
        "higher_is_better",
        Thresholds(pass_min=0.8),
    )
    lower = classify_scalar(
        ScalarResult(ScalarState.OBSERVED, 0.5),
        "lower_is_better",
        Thresholds(pass_max=0.2),
    )
    within = classify_scalar(
        ScalarResult(ScalarState.OBSERVED, 2),
        "within_range",
        Thresholds(pass_min=0.8, pass_max=1.2),
    )

    assert (higher, lower, within) == (
        ScalarStatus.FAIL,
        ScalarStatus.FAIL,
        ScalarStatus.FAIL,
    )


@pytest.mark.parametrize(
    ("computation", "observation"),
    [
        ("direct", ScalarObservation(state="observed")),
        (
            "detection_margin",
            ScalarObservation(state="observed", value=float("inf"), detection_limit=1),
        ),
        (
            "relative_error",
            ScalarObservation(state="observed", value=1, expected_value=float("nan")),
        ),
    ],
)
def test_missing_or_nonfinite_scalar_material_abstains(
    computation: str,
    observation: ScalarObservation,
) -> None:
    result = calculate_scalar(computation, observation)

    assert result.state in {ScalarState.MISSING, ScalarState.UNSUPPORTED}
    assert result.value is None
