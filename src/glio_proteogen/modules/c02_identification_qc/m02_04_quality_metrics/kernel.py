"""Pure identification-specific metric adapter over the shared scalar kernel."""

from __future__ import annotations

import math
from dataclasses import dataclass

from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.calculations import (
    ScalarObservation,
    ScalarResult,
    ScalarState,
    ScalarStatus,
    Thresholds,
    calculate_scalar,
    classify_scalar,
)


@dataclass(frozen=True, slots=True)
class IdentificationMetricInput:
    state: str
    numerator: float | None = None
    denominator: float | None = None
    value: float | None = None
    matches_expected: bool | None = None


@dataclass(frozen=True, slots=True)
class IdentificationMetricOutcome:
    state: ScalarState
    status: ScalarStatus
    value: float | None


def compute_identification_metric(
    metric_code: str,
    observation: IdentificationMetricInput,
    direction: str,
    thresholds: Thresholds,
) -> IdentificationMetricOutcome:
    """Compute and classify one closed identification-quality metric."""

    state = "below_detection_limit" if observation.state == "censored" else observation.state
    if metric_code == "sample_context_match":
        scalar = calculate_scalar(
            "boolean_match",
            ScalarObservation(state=state, matches_expected=observation.matches_expected),
        )
    elif metric_code == "precursor_mass_error_accuracy":
        scalar = calculate_scalar(
            "direct",
            ScalarObservation(state=state, value=observation.value),
        )
    elif metric_code == "control_material_recovery":
        scalar = _recovery(state, observation.numerator, observation.denominator)
    else:
        scalar = calculate_scalar(
            "ratio",
            ScalarObservation(
                state=state,
                numerator=observation.numerator,
                denominator=observation.denominator,
            ),
        )
    return _outcome(scalar, direction, thresholds)


def _recovery(
    state: str,
    numerator: float | None,
    denominator: float | None,
) -> ScalarResult:
    if state != "observed":
        return calculate_scalar("direct", ScalarObservation(state=state))
    if numerator is None or denominator is None:
        return ScalarResult(ScalarState.MISSING, None)
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    if numerator < 0 or denominator <= 0:
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    return ScalarResult(ScalarState.OBSERVED, numerator / denominator)


def _outcome(
    scalar: ScalarResult,
    direction: str,
    thresholds: Thresholds,
) -> IdentificationMetricOutcome:
    return IdentificationMetricOutcome(
        state=scalar.state,
        status=classify_scalar(scalar, direction, thresholds),
        value=scalar.value,
    )


__all__ = [
    "IdentificationMetricInput",
    "IdentificationMetricOutcome",
    "compute_identification_metric",
]
