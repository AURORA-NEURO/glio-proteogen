"""Analytical constrained optima for the complete hierarchy objective.

For one study, two genes and background (.5,.5), both symmetric donor pairs
below have their likelihood optimum at q=.5. At that point the study/global
and background/global KL penalties are both zero, for every default shrinkage.
Their nonnegativity therefore cannot move the optimum. These are low-level
kernel-domain oracles, not claims of fold or reference-cohort eligibility.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import DEFAULT_TRAINING_CONFIGURATION
from glio_proteogen.research.gbmap_deconvolution.hierarchy import (
    BACKGROUND_REGULARIZATION,
    DEFAULT_HIERARCHY_CONFIGURATION,
    MAXIMUM_CONCENTRATION,
    MINIMUM_CONCENTRATION,
    _HierarchyObjectiveEvaluator,
    _optimize_concentration,
    _validated_data,
    fit_lineage_hierarchy,
    lineage_hierarchy_objective,
    verify_hierarchy_trace,
)

_BACKGROUND = np.asarray([0.5, 0.5])
_STUDIES = ("synthetic-study", "synthetic-study")


def _bernoulli_kl(probability: float, reference: float) -> float:
    return math.fsum(
        (
            probability * math.log(probability / reference),
            (1.0 - probability) * math.log((1.0 - probability) / (1.0 - reference)),
        )
    )


def _closed_objective(kind: str, probability: float, concentration: float, shrinkage: float):
    """Two count-two PMFs plus the full independently written KL penalty."""
    if kind == "opposite_pure_donors":
        first = probability * (concentration * probability + 1.0) / (concentration + 1.0)
        second = (
            (1.0 - probability)
            * (concentration * (1.0 - probability) + 1.0)
            / (concentration + 1.0)
        )
        donor_loss = -0.5 * (math.log(first) + math.log(second))
    else:
        pmf = 2.0 * concentration * probability * (1.0 - probability) / (concentration + 1.0)
        donor_loss = -math.log(pmf)
    global_probability = (shrinkage * probability + BACKGROUND_REGULARIZATION * 0.5) / (
        shrinkage + BACKGROUND_REGULARIZATION
    )
    return math.fsum(
        (
            donor_loss,
            shrinkage * _bernoulli_kl(probability, global_probability),
            BACKGROUND_REGULARIZATION * _bernoulli_kl(0.5, global_probability),
        )
    )


@pytest.mark.parametrize("shrinkage", DEFAULT_TRAINING_CONFIGURATION.shrinkage_grid)
@pytest.mark.parametrize(
    ("kind", "counts", "endpoint"),
    [
        ("opposite_pure_donors", [[2, 0], [0, 2]], 4.0),
        ("identical_balanced_donors", [[1, 1], [1, 1]], 100_000.0),
    ],
)
def test_analytic_full_objective_selects_correct_bound_from_interior_and_default_fit(
    kind, counts, endpoint, shrinkage
):
    assert MINIMUM_CONCENTRATION == 4.0
    assert MAXIMUM_CONCENTRATION == 100_000.0
    assert BACKGROUND_REGULARIZATION == 0.01
    values = np.asarray(counts, dtype=np.int64)
    center = np.asarray([[0.5, 0.5]])
    concentrations = (4.0, 13.0, 1_000.0, 100_000.0)
    centered_losses = []
    for concentration in concentrations:
        expected_center = _closed_objective(kind, 0.5, concentration, shrinkage)
        centered_losses.append(expected_center)
        for probability in (0.25, 0.5, 0.75):
            expected = _closed_objective(kind, probability, concentration, shrinkage)
            observed = lineage_hierarchy_objective(
                values,
                _STUDIES,
                [[probability, 1.0 - probability]],
                _BACKGROUND,
                concentration=concentration,
                shrinkage=shrinkage,
            )
            assert observed == pytest.approx(expected, rel=0.0, abs=2e-12)
            assert expected >= expected_center
    # At q=.5, PMFs are (phi+2)/(4(phi+1)) for opposite pure donors,
    # and phi/(2(phi+1)) for balanced donors. Their monotonicity fixes the bound.
    differences = np.diff(centered_losses)
    assert np.all(differences > 0.0) if endpoint == 4.0 else np.all(differences < 0.0)

    # Start the real concentration update inside the bounds: the public
    # method-of-moments initializer already reaches the answer for these toys.
    # An interior start prevents that initializer from masking a broken update.
    data = _validated_data(values, _STUDIES, _BACKGROUND)
    evaluator = _HierarchyObjectiveEvaluator(data)
    start = 13.0
    updated, objective, _iterations = _optimize_concentration(
        data,
        evaluator,
        center,
        shrinkage=shrinkage,
        current_concentration=start,
        current_objective=_closed_objective(kind, 0.5, start, shrinkage),
        configuration=DEFAULT_HIERARCHY_CONFIGURATION,
        cancellation=None,
    )
    assert updated == endpoint
    expected_optimum = _closed_objective(kind, 0.5, endpoint, shrinkage)
    assert objective == pytest.approx(expected_optimum, rel=0.0, abs=2e-12)
    assert objective < _closed_objective(kind, 0.5, start, shrinkage)

    fit = fit_lineage_hierarchy(values, _STUDIES, _BACKGROUND, shrinkage=shrinkage)
    assert fit.converged
    assert verify_hierarchy_trace(fit)
    assert fit.concentration == endpoint
    assert fit.objective == pytest.approx(expected_optimum, rel=0.0, abs=2e-12)
    assert fit.kkt_residual <= DEFAULT_HIERARCHY_CONFIGURATION.kkt_tolerance
    assert fit.iterations <= DEFAULT_HIERARCHY_CONFIGURATION.max_outer_iterations
    np.testing.assert_array_equal(fit.study_signatures, center)
    np.testing.assert_array_equal(fit.global_signature, _BACKGROUND)
    assert all(
        later.objective
        <= earlier.objective + DEFAULT_HIERARCHY_CONFIGURATION.objective_increase_tolerance
        for earlier, later in zip(fit.trace, fit.trace[1:], strict=False)
    )
