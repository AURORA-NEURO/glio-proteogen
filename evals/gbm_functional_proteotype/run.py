"""Deterministic scientific calibration for the functional-proteotype engine.

The evaluator intentionally keeps every fixture in memory.  It exercises the
public engine for recovery and interval coverage, the profile's exact
permutation/BH implementation under a complete null, and the public numerical
solver against an independently assembled equality-constrained ridge oracle.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from typing import Final

import numpy as np

from glio_proteogen.research.gbm_functional_proteotype import (
    AXIS_ORDER,
    PROFILE_ID,
    AnalysisSupport,
    FunctionalProteotypeRequest,
    ProteinEvidence,
    ProteinEvidenceState,
    algorithm_profile,
    analyze_functional_proteotype,
    functional_proteotype_catalog,
)
from glio_proteogen.research.gbm_functional_proteotype.canonical import sha256_digest
from glio_proteogen.research.gbm_functional_proteotype.profile import CONSTANTS
from glio_proteogen.research.gbm_functional_proteotype.solver import (
    SolverConfiguration,
    SolverObservation,
    solve_constrained_latent,
)
from glio_proteogen.research.gbm_functional_proteotype.statistics import (
    stratified_permutation_rank_test,
)

_AXIS_COUNT: Final = 4
_GRAPH_COUNT: Final = 25
_SOURCE_INDICES: Final = (
    *range(5),
    *range(38, 43),
    *range(76, 81),
    *range(114, 119),
)
_SOURCE_RANKS: Final = tuple(index + 1 for index in _SOURCE_INDICES)
_OBSERVATIONS_PER_AXIS: Final = len(_SOURCE_INDICES)
_TRUE_COORDINATES: Final = (1.5, 0.5, -0.5, -1.5)
_INTERCEPT: Final = 0.25
_STANDARD_ERROR: Final = 0.30
_QUALITY_WEIGHT: Final = 0.90
_GRAPH_SEED: Final = 123
_BOOTSTRAP_REPLICATES: Final = 64
_ENGINE_PERMUTATION_REPLICATES: Final = 64
_MINIMUM_DIRECTION_RECOVERY: Final = 0.90
_COVERAGE_NOMINAL: Final = 0.90
_COVERAGE_LOWER: Final = 0.85
_COVERAGE_UPPER: Final = 0.95

_NULL_FAMILIES: Final = 250
_NULL_SEED: Final = 0x0BADC0DE
_NULL_PERMUTATION_SEED_BASE: Final = 10_000
_FDR_TOLERANCE: Final = 0.02

_SOLVER_REFERENCE_TOLERANCE: Final = 1e-10
_SIMULATION_PROVENANCE: Final = sha256_digest(
    {
        "evaluation": "gbm-functional-proteotype-scientific-calibration",
        "profile_id": PROFILE_ID,
        "design_version": "1",
        "patient_data": False,
    }
)
_DESIGN_DIGEST: Final = sha256_digest(
    {
        "profile_id": PROFILE_ID,
        "graph_count": _GRAPH_COUNT,
        "source_ranks": _SOURCE_RANKS,
        "truth": _TRUE_COORDINATES,
        "intercept": _INTERCEPT,
        "standard_error": _STANDARD_ERROR,
        "quality_weight": _QUALITY_WEIGHT,
        "graph_seed": _GRAPH_SEED,
        "bootstrap_replicates": _BOOTSTRAP_REPLICATES,
        "engine_permutation_replicates": _ENGINE_PERMUTATION_REPLICATES,
        "null_families": _NULL_FAMILIES,
        "null_seed": _NULL_SEED,
        "null_permutation_replicates": CONSTANTS.default_permutation_replicates,
    }
)


def _sampling_evaluation() -> dict[str, object]:
    """Run the locked Gaussian working-model simulation through the public engine."""

    catalog = functional_proteotype_catalog()
    rng = np.random.default_rng(_GRAPH_SEED)
    total_axes = _GRAPH_COUNT * _AXIS_COUNT
    converged_graphs = 0
    supported_axes = 0
    direction_matches = 0
    supported_direction_matches = 0
    intervals_returned = 0
    intervals_covering_truth = 0

    for graph_index in range(_GRAPH_COUNT):
        observations: list[ProteinEvidence] = []
        for axis_index, axis in enumerate(AXIS_ORDER):
            truth = _TRUE_COORDINATES[axis_index]
            rows = (catalog.axes[axis.value][index] for index in _SOURCE_INDICES)
            for row in rows:
                sampled_effect = (
                    _INTERCEPT
                    + truth * row.source_loading
                    + float(rng.normal(0.0, _STANDARD_ERROR))
                )
                observations.append(
                    ProteinEvidence(
                        observation_id=(
                            f"locked.graph.{graph_index:03d}.{axis.value}."
                            f"{row.source_rank:03d}"
                        ),
                        gene_symbol=row.gene_symbol,
                        state=ProteinEvidenceState.OBSERVED,
                        standardized_effect=round(sampled_effect, 12),
                        standard_error=_STANDARD_ERROR,
                        quality_weight=_QUALITY_WEIGHT,
                        provenance_digest=_SIMULATION_PROVENANCE,
                    )
                )
        request = FunctionalProteotypeRequest(
            sample_id=f"functional-eval-{graph_index:03d}",
            observations=tuple(observations),
            bootstrap_replicates=_BOOTSTRAP_REPLICATES,
            permutation_replicates=_ENGINE_PERMUTATION_REPLICATES,
            effect_reference_id="functional-eval-reference-v1",
        )
        result = analyze_functional_proteotype(request)
        converged_graphs += int(result.solver.converged)
        for axis_index, evidence in enumerate(result.axis_evidence):
            truth = _TRUE_COORDINATES[axis_index]
            latent = evidence.latent
            supported = evidence.support is AnalysisSupport.SUPPORTED
            direction_match = latent is not None and latent.estimate * truth > 0.0
            supported_axes += int(supported)
            direction_matches += int(direction_match)
            supported_direction_matches += int(supported and direction_match)
            if latent is not None:
                intervals_returned += 1
                intervals_covering_truth += int(
                    latent.lower_bound <= truth <= latent.upper_bound
                )

    direction_rate = supported_direction_matches / total_axes
    coverage_rate = intervals_covering_truth / total_axes
    return {
        "graph_count": _GRAPH_COUNT,
        "converged_graphs": converged_graphs,
        "axes_evaluated": total_axes,
        "observations_per_axis": _OBSERVATIONS_PER_AXIS,
        "source_ranks": list(_SOURCE_RANKS),
        "true_coordinates": {
            axis.value: _TRUE_COORDINATES[index] for index, axis in enumerate(AXIS_ORDER)
        },
        "sampling_model": "independent_normal_with_caller_supplied_standard_error",
        "sampling_seed": _GRAPH_SEED,
        "bootstrap_replicates_per_graph": _BOOTSTRAP_REPLICATES,
        "permutation_replicates_per_graph": _ENGINE_PERMUTATION_REPLICATES,
        "supported_axes": supported_axes,
        "direction_matches": direction_matches,
        "supported_direction_matches": supported_direction_matches,
        "direction_recovery_rate": direction_rate,
        "minimum_direction_recovery": _MINIMUM_DIRECTION_RECOVERY,
        "direction_recovery_passed": direction_rate >= _MINIMUM_DIRECTION_RECOVERY,
        "intervals_returned": intervals_returned,
        "intervals_covering_truth": intervals_covering_truth,
        "coverage_rate": coverage_rate,
        "nominal_coverage": _COVERAGE_NOMINAL,
        "coverage_acceptance_band": [_COVERAGE_LOWER, _COVERAGE_UPPER],
        "coverage_passed": _COVERAGE_LOWER <= coverage_rate <= _COVERAGE_UPPER,
    }


def _null_fdr_evaluation() -> dict[str, object]:
    """Estimate complete-null BH FDR over fixed four-axis families.

    Under the complete null, a family's false-discovery proportion is one when
    it contains any rejection and zero otherwise.  Its Monte Carlo mean is thus
    the family false-discovery rate, while the per-axis rejection fraction is
    retained as a secondary diagnostic.
    """

    axis_indices = np.repeat(
        np.arange(_AXIS_COUNT, dtype=np.int64),
        _OBSERVATIONS_PER_AXIS,
    )
    source_ranks = np.tile(
        np.asarray(_SOURCE_RANKS, dtype=np.int64),
        _AXIS_COUNT,
    )
    rng = np.random.default_rng(_NULL_SEED)
    families_with_discovery = 0
    rejected_axes = 0
    for family_index in range(_NULL_FAMILIES):
        values = rng.normal(0.0, 1.0, size=len(axis_indices))
        result = stratified_permutation_rank_test(
            values,
            axis_indices,
            source_ranks,
            replicates=CONSTANTS.default_permutation_replicates,
            seed=_NULL_PERMUTATION_SEED_BASE + family_index,
        )
        family_rejections = sum(
            q_value <= CONSTANTS.rank_q_threshold for q_value in result.q_values
        )
        rejected_axes += family_rejections
        families_with_discovery += int(family_rejections > 0)

    axis_tests = _NULL_FAMILIES * _AXIS_COUNT
    empirical_fdr = families_with_discovery / _NULL_FAMILIES
    false_positive_fraction = rejected_axes / axis_tests
    acceptance_upper = CONSTANTS.rank_q_threshold + _FDR_TOLERANCE
    return {
        "complete_null_families": _NULL_FAMILIES,
        "axes_per_family": _AXIS_COUNT,
        "axis_tests": axis_tests,
        "permutation_replicates": CONSTANTS.default_permutation_replicates,
        "q_threshold": CONSTANTS.rank_q_threshold,
        "acceptance_tolerance": _FDR_TOLERANCE,
        "acceptance_upper": acceptance_upper,
        "families_with_discovery": families_with_discovery,
        "rejected_axes": rejected_axes,
        "empirical_family_fdr": empirical_fdr,
        "per_axis_false_positive_fraction": false_positive_fraction,
        "passed": empirical_fdr <= acceptance_upper,
    }


def _solver_configuration() -> SolverConfiguration:
    return SolverConfiguration(
        huber_delta=CONSTANTS.huber_delta,
        standard_error_floor=CONSTANTS.standard_error_floor,
        axis_ridge=CONSTANTS.axis_ridge_penalty,
        intercept_ridge=CONSTANTS.intercept_ridge_penalty,
        damping=CONSTANTS.initial_damping,
        tolerance=CONSTANTS.coordinate_tolerance,
        gradient_tolerance=CONSTANTS.gradient_tolerance,
        max_iterations=CONSTANTS.maximum_solver_iterations,
        backtracking_factor=CONSTANTS.backtracking_factor,
        backtracking_steps=CONSTANTS.maximum_backtracking_steps,
        objective_increase_tolerance=CONSTANTS.objective_increase_tolerance,
    )


def _solver_reference_evaluation() -> dict[str, object]:
    """Compare a small quadratic-regime graph to an independent KKT solve."""

    configuration = _solver_configuration()
    rows = (
        (0, 0.42, 1.00, 0.60, 0.90),
        (0, 0.38, 0.80, 0.65, 1.00),
        (1, -0.28, 1.10, 0.60, 0.80),
        (1, -0.22, 0.90, 0.65, 1.00),
        (2, 0.18, 1.20, 0.60, 0.70),
        (2, 0.12, 0.70, 0.65, 1.00),
        (3, -0.32, 1.00, 0.60, 0.90),
        (3, -0.28, 0.85, 0.65, 1.00),
    )
    observations = tuple(
        SolverObservation(
            axis_index=axis_index,
            source_loading=loading,
            state="observed",
            value=value,
            standard_error=standard_error,
            quality_weight=quality_weight,
        )
        for axis_index, value, loading, standard_error, quality_weight in rows
    )

    design = np.zeros((len(observations), _AXIS_COUNT + 1), dtype=np.float64)
    response = np.asarray([item.value for item in observations], dtype=np.float64)
    weights = np.empty(len(observations), dtype=np.float64)
    scales = np.empty(len(observations), dtype=np.float64)
    for index, item in enumerate(observations):
        design[index, 0] = 1.0
        design[index, item.axis_index + 1] = item.source_loading
        variance = (
            item.standard_error**2 + configuration.standard_error_floor**2
        )
        weights[index] = item.quality_weight / variance
        scales[index] = np.sqrt(variance)

    hessian = design.T @ (weights[:, None] * design)
    hessian += np.diag(
        [configuration.intercept_ridge]
        + [configuration.axis_ridge] * _AXIS_COUNT
    )
    right_hand_side = design.T @ (weights * response)
    constraint = np.asarray([0.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    kkt = np.block(
        [
            [hessian, constraint[:, None]],
            [constraint[None, :], np.zeros((1, 1), dtype=np.float64)],
        ]
    )
    oracle = np.linalg.solve(
        kkt,
        np.concatenate((right_hand_side, np.asarray([0.0], dtype=np.float64))),
    )[: _AXIS_COUNT + 1]
    maximum_oracle_residual = float(
        np.max(np.abs((design @ oracle - response) / scales))
    )

    outcome = solve_constrained_latent(observations, configuration)
    actual = np.asarray((outcome.intercept, *outcome.axis_values), dtype=np.float64)
    maximum_absolute_error = float(np.max(np.abs(actual - oracle)))
    passed = (
        outcome.converged
        and maximum_oracle_residual <= configuration.huber_delta
        and maximum_absolute_error <= _SOLVER_REFERENCE_TOLERANCE
    )
    return {
        "observation_count": len(observations),
        "converged": outcome.converged,
        "solver_iterations": outcome.iterations,
        "quadratic_regime_maximum_standardized_residual": maximum_oracle_residual,
        "huber_delta": configuration.huber_delta,
        "maximum_absolute_parameter_error": maximum_absolute_error,
        "acceptance_tolerance": _SOLVER_REFERENCE_TOLERANCE,
        "passed": passed,
    }


@lru_cache(maxsize=1)
def run_evaluation() -> dict[str, object]:
    """Return the compact, deterministic scientific-evaluation report."""

    profile = algorithm_profile()
    sampling = _sampling_evaluation()
    null_fdr = _null_fdr_evaluation()
    solver_reference = _solver_reference_evaluation()
    checks = {
        "profile_locked": profile.profile_id == PROFILE_ID,
        "all_graphs_converged": sampling["converged_graphs"] == _GRAPH_COUNT,
        "latent_direction_recovery": bool(sampling["direction_recovery_passed"]),
        "bootstrap_interval_coverage": bool(sampling["coverage_passed"]),
        "permutation_bh_null_fdr": bool(null_fdr["passed"]),
        "small_graph_solver_reference": bool(solver_reference["passed"]),
    }
    return {
        "evaluation_id": "gbm-functional-proteotype-scientific-calibration-v1",
        "profile_id": profile.profile_id,
        "profile_digest": profile.profile_digest,
        "design_digest": _DESIGN_DIGEST,
        "patient_data": False,
        "passed": all(checks.values()),
        "checks": checks,
        "sampling_evaluation": sampling,
        "permutation_bh_null_evaluation": null_fdr,
        "solver_reference_evaluation": solver_reference,
    }


def main() -> int:
    report = run_evaluation()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_evaluation"]
