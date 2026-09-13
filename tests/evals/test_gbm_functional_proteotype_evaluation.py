"""Locked scientific acceptance tests for the functional-proteotype profile."""

from __future__ import annotations

import pytest
from evals.gbm_functional_proteotype.run import run_evaluation

from glio_proteogen.research.gbm_functional_proteotype import PROFILE_ID

_GRAPH_COUNT = 25
_AXES_EVALUATED = 100
_SUPPORTED_AXES = 100
_COVERED_INTERVALS = 90
_NULL_FAMILIES = 250
_NULL_AXIS_TESTS = 1_000
_NULL_FAMILIES_WITH_DISCOVERY = 27
_NULL_REJECTED_AXES = 35
_SOLVER_OBSERVATIONS = 8


@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return run_evaluation()


def test_evaluation_is_bound_to_the_requested_profile(
    report: dict[str, object],
) -> None:
    assert report["profile_id"] == PROFILE_ID
    assert str(report["profile_digest"]).startswith("sha256:")
    assert str(report["design_digest"]).startswith("sha256:")
    assert report["patient_data"] is False
    assert report["passed"] is True
    assert all(report["checks"].values())  # type: ignore[union-attr]


def test_supported_latent_direction_recovery_exceeds_ninety_percent(
    report: dict[str, object],
) -> None:
    sampling = report["sampling_evaluation"]
    assert isinstance(sampling, dict)
    assert sampling["graph_count"] == _GRAPH_COUNT
    assert sampling["converged_graphs"] == _GRAPH_COUNT
    assert sampling["axes_evaluated"] == _AXES_EVALUATED
    assert sampling["supported_axes"] == _SUPPORTED_AXES
    assert sampling["direction_matches"] == _AXES_EVALUATED
    assert sampling["supported_direction_matches"] == _SUPPORTED_AXES
    assert sampling["direction_recovery_rate"] == pytest.approx(1.0)
    assert sampling["minimum_direction_recovery"] == pytest.approx(0.90)
    assert sampling["direction_recovery_passed"] is True


def test_nominal_ninety_percent_bootstrap_coverage_is_in_locked_band(
    report: dict[str, object],
) -> None:
    sampling = report["sampling_evaluation"]
    assert isinstance(sampling, dict)
    assert sampling["intervals_returned"] == _AXES_EVALUATED
    assert sampling["intervals_covering_truth"] == _COVERED_INTERVALS
    assert sampling["coverage_rate"] == pytest.approx(0.90)
    assert sampling["nominal_coverage"] == pytest.approx(0.90)
    assert sampling["coverage_acceptance_band"] == [0.85, 0.95]
    assert sampling["coverage_passed"] is True


def test_four_axis_permutation_bh_complete_null_controls_false_discoveries(
    report: dict[str, object],
) -> None:
    null_fdr = report["permutation_bh_null_evaluation"]
    assert isinstance(null_fdr, dict)
    assert null_fdr["complete_null_families"] == _NULL_FAMILIES
    assert null_fdr["axis_tests"] == _NULL_AXIS_TESTS
    assert null_fdr["q_threshold"] == pytest.approx(0.10)
    assert null_fdr["acceptance_upper"] == pytest.approx(0.12)
    assert null_fdr["families_with_discovery"] == _NULL_FAMILIES_WITH_DISCOVERY
    assert null_fdr["empirical_family_fdr"] == pytest.approx(0.108)
    assert null_fdr["rejected_axes"] == _NULL_REJECTED_AXES
    assert null_fdr["per_axis_false_positive_fraction"] == pytest.approx(0.035)
    assert null_fdr["passed"] is True


def test_small_graph_solver_matches_independent_kkt_reference(
    report: dict[str, object],
) -> None:
    solver = report["solver_reference_evaluation"]
    assert isinstance(solver, dict)
    assert solver["observation_count"] == _SOLVER_OBSERVATIONS
    assert solver["converged"] is True
    assert solver["quadratic_regime_maximum_standardized_residual"] < solver["huber_delta"]
    assert solver["maximum_absolute_parameter_error"] <= solver["acceptance_tolerance"]
    assert solver["passed"] is True
