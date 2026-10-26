"""Numerical parity and bounded-liveness checks for the independent Huber audit."""

from __future__ import annotations

import struct
from typing import Any

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_cis_dosage import model as legacy
from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.convergence import (
    ALLOWED_ITERATION_BUDGETS,
    fit_huber_with_budget,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.profile import (
    algorithm_profile,
)


def _contaminated_case(seed: int = 9) -> tuple[np.ndarray, np.ndarray]:
    """Prespecified slow oracle: heavy tails, contamination, correlated predictors."""

    random = np.random.default_rng(seed)
    x = random.normal(size=(40, 2))
    x[:, 1] = 0.95 * x[:, 0] + 0.1 * x[:, 1]
    y = 1.2 * x[:, 0] - 0.4 * x[:, 1] + random.standard_t(1.5, size=40) * 0.3
    y[:16] += random.normal(loc=1.0, scale=3.0, size=16)
    return x, y


def _assert_bitwise_equal(left: RobustFit | None, right: RobustFit | None) -> None:
    if left is None or right is None:
        assert left is None and right is None
        return
    assert type(left) is type(right) is RobustFit
    assert left.converged is right.converged
    assert left.iterations == right.iterations
    assert struct.pack("!d", left.y_center) == struct.pack("!d", right.y_center)
    assert struct.pack("!d", left.y_scale) == struct.pack("!d", right.y_scale)
    for first, second in (
        (left.x_center, right.x_center),
        (left.x_scale, right.x_scale),
        (left.beta, right.beta),
    ):
        assert first.dtype == second.dtype
        assert first.shape == second.shape
        assert first.tobytes() == second.tobytes()


@pytest.mark.parametrize("seed", [0, 1, 9, 12, 32, 37, 40, 71])
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_default_thirty_iterations_match_legacy_bit_for_bit(seed: int, dtype: Any) -> None:
    x, y = _contaminated_case(seed)
    x, y = x.astype(dtype), y.astype(dtype)
    original = legacy.fit_huber(x, y)
    audited = fit_huber_with_budget(x, y)
    _assert_bitwise_equal(original, audited)
    if original is not None and audited is not None:
        assert original.predict(x[:7]).tobytes() == audited.predict(x[:7]).tobytes()


def test_larger_prespecified_budget_recovers_a_slow_case_without_relabeling_legacy() -> None:
    x, y = _contaminated_case()
    original = legacy.fit_huber(x, y)
    assert original is not None and not original.converged and original.iterations == 30
    default = fit_huber_with_budget(x, y, max_iterations=30)
    _assert_bitwise_equal(original, default)
    recovered = fit_huber_with_budget(x, y, max_iterations=60)
    assert recovered is not None and recovered.converged
    assert 30 < recovered.iterations <= 60
    assert recovered.iterations == 41
    assert bool(np.all(np.isfinite(recovered.predict(x))))
    assert not np.array_equal(recovered.beta, original.beta)
    for budget in (120, 240):
        _assert_bitwise_equal(recovered, fit_huber_with_budget(x, y, max_iterations=budget))
    _assert_bitwise_equal(original, legacy.fit_huber(x, y))
    assert legacy.MAX_IRLS_ITERATIONS == 30


@pytest.mark.parametrize("budget", [30, 60, 120, 240])
def test_determinism_readonly_inputs_and_profile_globals_remain_unchanged(budget: int) -> None:
    x, y = _contaminated_case()
    x.flags.writeable = False
    y.flags.writeable = False
    before = (x.tobytes(), y.tobytes())
    constants = (
        legacy.MAX_IRLS_ITERATIONS,
        legacy.HUBER_K,
        legacy.IRLS_TOLERANCE,
        legacy.SLOPE_RIDGE,
    )
    profile = algorithm_profile().profile_digest
    first = fit_huber_with_budget(x, y, max_iterations=budget)
    second = fit_huber_with_budget(x, y, max_iterations=budget)
    _assert_bitwise_equal(first, second)
    assert before == (x.tobytes(), y.tobytes())
    assert constants == (
        legacy.MAX_IRLS_ITERATIONS,
        legacy.HUBER_K,
        legacy.IRLS_TOLERANCE,
        legacy.SLOPE_RIDGE,
    )
    assert algorithm_profile().profile_digest == profile


def test_nonconverging_updates_stop_at_the_declared_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    x, y = _contaminated_case()
    calls = 0

    def oscillate(_matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.full_like(rhs, 0.1 if calls % 2 else 0.0)

    monkeypatch.setattr(np.linalg, "solve", oscillate)
    fit = fit_huber_with_budget(x, y, max_iterations=240)
    assert fit is not None and not fit.converged
    assert fit.iterations == 240
    assert calls == 241  # One initial least-squares solve, then the exact declared cap.


@pytest.mark.parametrize("failure_call", [1, 2])
def test_failed_initial_or_weighted_linear_solve_abstains(
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    x, y = _contaminated_case()
    original_solve = np.linalg.solve
    calls = 0

    def fail_selected_solve(matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise np.linalg.LinAlgError
        return original_solve(matrix, rhs)

    monkeypatch.setattr(np.linalg, "solve", fail_selected_solve)
    assert fit_huber_with_budget(x, y, max_iterations=60) is None
    assert calls == failure_call


def test_nonfinite_solver_residual_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    x, y = _contaminated_case()
    monkeypatch.setattr(np.linalg, "solve", lambda _matrix, rhs: np.full_like(rhs, np.nan))
    assert fit_huber_with_budget(x, y, max_iterations=30) is None


def test_degenerate_scales_mad_fallback_and_near_exact_fit_preserve_legacy_behavior() -> None:
    varied = np.arange(10, dtype=np.float64)
    assert fit_huber_with_budget(np.zeros((10, 1)), varied) is None
    assert fit_huber_with_budget(varied[:, None], np.ones(10)) is None
    fallback_x = np.asarray([0.0] * 7 + [1.0, 2.0, 3.0])[:, None]
    fallback_y = 2.0 * fallback_x[:, 0] + 1.0
    original = legacy.fit_huber(fallback_x, fallback_y)
    audited = fit_huber_with_budget(fallback_x, fallback_y)
    _assert_bitwise_equal(original, audited)
    assert audited is not None and audited.converged and audited.iterations == 1
    assert audited.x_scale[0] == float(np.std(fallback_x[:, 0], ddof=1))
    collinear = np.column_stack((varied, varied))
    _assert_bitwise_equal(
        legacy.fit_huber(collinear, varied * 3.0), fit_huber_with_budget(collinear, varied * 3.0)
    )


@pytest.mark.parametrize("value", [0, 1, 29, 31, 59, 61, 121, 241, -30, 10**12])
def test_only_prespecified_integer_budgets_are_accepted(value: int) -> None:
    x, y = _contaminated_case()
    with pytest.raises(ValueError, match="one of 30, 60, 120, or 240"):
        fit_huber_with_budget(x, y, max_iterations=value)
    assert ALLOWED_ITERATION_BUDGETS == (30, 60, 120, 240)


@pytest.mark.parametrize("value", [True, False, None, 30.0, "30", np.int64(30)])
def test_budget_validation_does_not_coerce_booleans_floats_or_numpy_scalars(value: Any) -> None:
    x, y = _contaminated_case()
    with pytest.raises(TypeError, match="exact integer"):
        fit_huber_with_budget(x, y, max_iterations=value)


@pytest.mark.parametrize(("column", "value"), [(0, np.nan), (1, np.inf), (1, -np.inf)])
def test_nonfinite_predictors_are_rejected(column: int, value: float) -> None:
    x, y = _contaminated_case()
    x[4, column] = value
    with pytest.raises(ValueError, match="non-finite"):
        fit_huber_with_budget(x, y, max_iterations=60)


def test_nonfinite_response_and_malformed_shapes_are_rejected() -> None:
    x, y = _contaminated_case()
    invalid_y = y.copy()
    invalid_y[2] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        fit_huber_with_budget(x, invalid_y)
    for first, second in ((x[:, 0], y), (x, y[:, None]), (x, y[:-1]), (x[:2], y[:2])):
        with pytest.raises(ValueError, match="aligned finite matrices"):
            fit_huber_with_budget(first, second)
    with pytest.raises(TypeError, match="NumPy arrays"):
        fit_huber_with_budget(x.tolist(), y)  # type: ignore[arg-type]
