from __future__ import annotations

import math

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionInferenceError,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.solver import (
    MemberEvidence,
    solve_member_coordinate,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)


def _evidence(
    values: tuple[float, ...],
    semantics: tuple[str, ...] | None = None,
) -> tuple[MemberEvidence, ...]:
    states = semantics or ("exact_delta",) * len(values)
    return tuple(
        MemberEvidence(
            member_position=index,
            value=value,
            semantics=state,  # type: ignore[arg-type]
            reliability_weight=1.0,
        )
        for index, (value, state) in enumerate(zip(values, states, strict=True))
    )


def test_quadratic_region_matches_closed_form_ridge_solution() -> None:
    loading = np.asarray([0.5, -0.25, 0.75], dtype=np.float64)
    values = (0.2, -0.1, 0.3)
    expected = float(np.dot(loading, values) / (np.dot(loading, loading) + 0.075))

    result = solve_member_coordinate(loading, _evidence(values))

    assert result.coordinate == pytest.approx(expected, abs=2e-9)
    assert result.diagnostics.converged
    assert result.diagnostics.objective_monotone
    assert result.diagnostics.final_objective <= result.diagnostics.initial_objective
    assert result.diagnostics.exact_evidence_count == 3


def test_huber_fit_resists_one_extreme_member() -> None:
    loading = np.ones(4, dtype=np.float64)
    values = (0.5, 0.55, 0.45, 100.0)
    result = solve_member_coordinate(loading, _evidence(values))
    least_squares = sum(values) / (len(values) + 1.0)

    assert 0.0 < result.coordinate < 1.0
    assert result.coordinate < least_squares / 10.0


def test_inactive_one_sided_bound_is_not_converted_to_negative_evidence() -> None:
    loading = np.asarray([1.0, 1.0], dtype=np.float64)
    exact_only = solve_member_coordinate(loading[:1], _evidence((0.6,)))
    with_inactive_bound = solve_member_coordinate(
        loading,
        _evidence((0.6, -100.0), ("exact_delta", "lower_bound")),
    )

    assert with_inactive_bound.coordinate == pytest.approx(
        exact_only.coordinate,
        abs=2e-9,
    )
    assert with_inactive_bound.diagnostics.lower_bound_count == 1


def test_active_one_sided_bound_constrains_coordinate() -> None:
    loading = np.asarray([1.0, 1.0], dtype=np.float64)
    unconstrained = solve_member_coordinate(loading[:1], _evidence((0.2,)))
    constrained = solve_member_coordinate(
        loading,
        _evidence((0.2, 1.0), ("exact_delta", "lower_bound")),
    )

    assert constrained.coordinate > unconstrained.coordinate


def test_evidence_order_does_not_change_coordinate() -> None:
    loading = np.asarray([0.2, -0.5, 0.8], dtype=np.float64)
    evidence = _evidence((0.3, -0.4, 0.7))
    reordered = (evidence[2], evidence[0], evidence[1])

    left = solve_member_coordinate(loading, evidence)
    right = solve_member_coordinate(loading, reordered)

    assert left.coordinate == pytest.approx(right.coordinate, abs=1e-12)
    assert left.diagnostics.final_objective == pytest.approx(
        right.diagnostics.final_objective,
        abs=1e-12,
    )


@pytest.mark.parametrize(
    ("loading", "evidence", "overrides"),
    [
        (np.asarray([], dtype=np.float64), _evidence((1.0,)), {}),
        (np.asarray([math.nan], dtype=np.float64), _evidence((1.0,)), {}),
        (np.asarray([0.0], dtype=np.float64), _evidence((1.0,)), {}),
        (np.asarray([1.0], dtype=np.float64), (), {}),
        (
            np.asarray([1.0], dtype=np.float64),
            (MemberEvidence(0, 1.0, "exact_delta", 0.0),),
            {},
        ),
        (np.asarray([1.0], dtype=np.float64), _evidence((1.0,)), {"huber_k": 0.0}),
        (np.asarray([1.0], dtype=np.float64), _evidence((1.0,)), {"ridge_lambda": 0.0}),
        (np.asarray([1.0], dtype=np.float64), _evidence((1.0,)), {"damping": 0.0}),
        (np.asarray([1.0], dtype=np.float64), _evidence((1.0,)), {"max_iterations": 0}),
        (np.asarray([1.0], dtype=np.float64), _evidence((1.0,)), {"tolerance": 0.0}),
    ],
)
def test_invalid_solver_domains_fail_closed(
    loading: np.ndarray[tuple[int, ...], np.dtype[np.float64]],
    evidence: tuple[MemberEvidence, ...],
    overrides: dict[str, float | int],
) -> None:
    with pytest.raises(ComplexTransitionInferenceError):
        solve_member_coordinate(loading, evidence, **overrides)  # type: ignore[arg-type]


def test_solver_honors_pre_cancelled_context() -> None:
    context = CancellationContext()
    context.cancel()

    with pytest.raises(InferenceCancelledError):
        solve_member_coordinate(
            np.asarray([1.0], dtype=np.float64),
            _evidence((0.5,)),
            cancellation=context,
        )
