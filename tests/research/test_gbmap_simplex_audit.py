"""Independent endpoint equations; an audit never rescues the legacy gate.

Integer harmonic sums and finite log products below do not call the production
DM, gradient or endpoint helpers. Synthetic solutions exercise request binding;
they do not authenticate biological source admission or an optimizer trajectory.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.simplex import (
    ReferenceMixtureSolution,
    SimplexSolverConfiguration,
    solve_reference_mixture,
    verify_objective_trace,
)
from glio_proteogen.research.gbmap_mixture_benchmark import MixturePointPolicy
from glio_proteogen.research.gbmap_simplex_audit import (
    AUDIT_VERSION,
    SimplexAuditError,
    SimplexEndpointAudit,
    audit_simplex_solution,
)

_MIDPOINT = np.asarray([[0.5, 1 / 6], [1 / 6, 0.5], [1 / 3, 1 / 3]])
_UNIFORM = np.full(3, 1 / 3)
_SIGNATURES = np.asarray([[0.5, 0.1], [0.25, 0.2], [0.15, 0.3], [0.1, 0.4]])
_BACKGROUND = np.asarray([0.1, 0.2, 0.3, 0.4])
_WEIGHTS = np.asarray([0.45, 0.25, 0.1, 0.08, 0.07, 0.05])
_COUNTS = np.asarray([0, 255, 256, 257], dtype=np.int64)


def _policy(**changes):
    return MixturePointPolicy(
        **{
            "concentration": 13.0,
            "lambda_mass": 0.07,
            "lambda_shape": 0.3,
            "initial_unknown_mass": 0.2,
            **changes,
        }
    )


def _midpoint_solution(initial_unknown_mass):
    policy = _policy(
        concentration=100.0,
        lambda_mass=0.0,
        lambda_shape=0.1,
        initial_unknown_mass=initial_unknown_mass,
    )
    solution = solve_reference_mixture(
        [300, 300, 300],
        _MIDPOINT,
        _UNIFORM,
        concentration=policy.concentration,
        lambda_mass=policy.lambda_mass,
        lambda_shape=policy.lambda_shape,
        initial_unknown_mass=policy.initial_unknown_mass,
    )
    return policy, solution


def _log_factorial(value):
    return math.fsum(math.log(index) for index in range(1, int(value) + 1))


def _objective_parts(counts, signatures, background, weights, policy):
    """Finite integer products for the entire request-bound objective."""
    known_count = signatures.shape[1]
    known, unknown = weights[:known_count], weights[known_count:]
    probabilities = signatures @ known + unknown
    total = sum(int(value) for value in counts)
    log_pmf = math.fsum(
        [
            _log_factorial(total),
            *(-_log_factorial(value) for value in counts),
            *(
                math.log(policy.concentration * float(probability) + offset)
                for count, probability in zip(counts, probabilities, strict=True)
                for offset in range(int(count))
            ),
            *(-math.log(policy.concentration + offset) for offset in range(total)),
        ]
    )
    unknown_mass = math.fsum(float(value) for value in unknown)
    mass = policy.lambda_mass * unknown_mass
    shape = policy.lambda_shape * math.fsum(
        float(value) * math.log(float(value) / (unknown_mass * float(base)))
        for value, base in zip(unknown, background, strict=True)
        if value > 0.0
    )
    return -log_pmf / total, mass, shape


def _harmonic_gradient(counts, signatures, background, weights, policy):
    """Integer digamma differences written as finite reciprocal sums."""
    known_count = signatures.shape[1]
    unknown = weights[known_count:]
    probabilities = signatures @ weights[:known_count] + unknown
    total = sum(int(value) for value in counts)
    likelihood = np.asarray(
        [
            -policy.concentration
            / total
            * math.fsum(
                1.0 / (policy.concentration * float(probability) + offset)
                for offset in range(int(count))
            )
            for count, probability in zip(counts, probabilities, strict=True)
        ]
    )
    unknown_mass = math.fsum(float(value) for value in unknown)
    gradient = [
        math.fsum(float(s) * float(g) for s, g in zip(column, likelihood, strict=True))
        for column in signatures.T
    ]
    gradient.extend(
        float(g)
        + policy.lambda_mass
        + policy.lambda_shape * math.log(float(value) / (unknown_mass * float(base)))
        for g, value, base in zip(likelihood, unknown, background, strict=True)
    )
    return np.asarray(gradient)


def _kkt(gradient, weights):
    active = weights > SimplexSolverConfiguration().active_weight_tolerance
    multiplier = math.fsum(float(value) for value in gradient[active]) / int(active.sum())
    return max(
        *(abs(float(value) - multiplier) for value in gradient[active]),
        *(max(multiplier - float(value), 0.0) for value in gradient[~active]),
    )


def _initial_weights(policy, background, known_count):
    unnormalized = [
        *([(1.0 - policy.initial_unknown_mass) / known_count] * known_count),
        *(policy.initial_unknown_mass * float(value) for value in background),
    ]
    floor = SimplexSolverConfiguration().simplex_floor
    total = math.fsum(unnormalized)
    return np.asarray(
        [floor + (1.0 - len(unnormalized) * floor) * value / total for value in unnormalized]
    )


def _synthetic_solution(
    *, counts=_COUNTS, signatures=_SIGNATURES, background=_BACKGROUND, weights=_WEIGHTS, policy=None
):
    """Construct an internally valid endpoint, with no trajectory-fit claim."""
    policy = _policy() if policy is None else policy
    known_count = signatures.shape[1]
    gradient = (
        _harmonic_gradient(counts, signatures, background, weights, policy)
        if np.all(weights[known_count:] > 0.0)
        else None
    )
    initial = _initial_weights(policy, background, known_count)
    condition = 1.0
    if known_count > 1:
        singular = np.linalg.svd(signatures[:, :-1] - signatures[:, [-1]], compute_uv=False)
        condition = float(singular[0] / singular[-1])
    return ReferenceMixtureSolution(
        known_rna_weights=weights[:known_count],
        unknown_gene_mass=weights[known_count:],
        fitted_probabilities=signatures @ weights[:known_count] + weights[known_count:],
        unknown_mass=math.fsum(float(value) for value in weights[known_count:]),
        initial_objective=math.fsum(
            _objective_parts(counts, signatures, background, initial, policy)
        ),
        objective=math.fsum(_objective_parts(counts, signatures, background, weights, policy)),
        converged=False,
        iterations=0,
        kkt_residual=0.0 if gradient is None else _kkt(gradient, weights),
        signature_condition_number=condition,
        trace=(),
    )


def _audit(
    *, counts=_COUNTS, signatures=_SIGNATURES, background=_BACKGROUND, policy=None, solution=None
):
    policy = _policy() if policy is None else policy
    solution = _synthetic_solution() if solution is None else solution
    return audit_simplex_solution(counts, signatures, background, policy, solution)


@pytest.mark.parametrize("initial_unknown_mass", [0.05, 0.2])
def test_genuine_default_stationarity_never_rescues_the_original_trace_gate(initial_unknown_mass):
    policy, solution = _midpoint_solution(initial_unknown_mass)
    report = audit_simplex_solution([300] * 3, _MIDPOINT, _UNIFORM, policy, solution)
    assert report.gradient_status == "available"
    assert report.default_stationary is True
    assert report.recomputed_kkt_residual == pytest.approx(0.0, abs=1e-12)
    assert report.reconstructed_probabilities_match is True
    assert report.objective_matches is report.initial_objective_matches is True
    assert report.condition_number_matches is report.unknown_mass_matches is True
    assert report.admission_changed is report.trajectory_replayed is False
    if initial_unknown_mass == 0.2:
        assert solution.iterations == 0
        assert solution.converged is verify_objective_trace(solution) is False
        assert report.legacy_benchmark_status == "solver_trace_invalid"
        assert report.zero_step_endpoint_matches_initial is report.zero_step_stationary is True
    else:
        assert solution.iterations == 1
        assert solution.converged is verify_objective_trace(solution) is True
        assert report.legacy_benchmark_status == "scored"
        assert report.zero_step_endpoint_matches_initial is report.zero_step_stationary is None


def test_harmonic_derivatives_and_full_log_product_objective_at_count_boundaries():
    policy, weights = _policy(), _WEIGHTS
    solution = _synthetic_solution()
    report = _audit(solution=solution)
    nll, mass, shape = _objective_parts(_COUNTS, _SIGNATURES, _BACKGROUND, weights, policy)
    gradient = _harmonic_gradient(_COUNTS, _SIGNATURES, _BACKGROUND, weights, policy)
    assert tuple(_COUNTS) == (0, 255, 256, 257)
    assert report.count_depth == 768
    assert report.recomputed_nll == pytest.approx(nll, abs=2e-12)
    assert report.recomputed_mass_penalty == pytest.approx(mass, abs=1e-14)
    assert report.recomputed_shape_penalty == pytest.approx(shape, abs=1e-14)
    assert report.recomputed_shape_divergence == pytest.approx(shape / policy.lambda_shape)
    assert report.recomputed_objective == pytest.approx(math.fsum((nll, mass, shape)), abs=2e-12)
    assert report.objective_matches is report.initial_objective_matches is True
    assert report.gradient_status == "available"
    assert report.recomputed_kkt_residual == pytest.approx(_kkt(gradient, weights), abs=2e-12)
    assert report.kkt_matches is True
    assert report.default_stationary is False
    minimum = min(gradient)
    stable_gap = math.fsum(
        float(w) * (float(g) - minimum) for w, g in zip(weights, gradient, strict=True)
    )
    raw_gap = (
        math.fsum(float(w) * float(g) for w, g in zip(weights, gradient, strict=True)) - minimum
    )
    assert report.stable_frank_wolfe_gap == pytest.approx(stable_gap, abs=2e-12)
    assert report.raw_frank_wolfe_gap == pytest.approx(raw_gap, abs=2e-12)
    assert report.stable_frank_wolfe_gap >= 0.0
    assert (
        report.frank_wolfe_gap_difference
        == report.raw_frank_wolfe_gap - report.stable_frank_wolfe_gap
    )
    # Directions stay in the shared simplex. This finite-difference check uses
    # the independent finite-product objective, not the production gradient.
    epsilon = 1e-6
    for index in range(weights.size - 1):
        plus, minus = weights.copy(), weights.copy()
        plus[index] += epsilon
        plus[-1] -= epsilon
        minus[index] -= epsilon
        minus[-1] += epsilon
        numerical = (
            math.fsum(_objective_parts(_COUNTS, _SIGNATURES, _BACKGROUND, plus, policy))
            - math.fsum(_objective_parts(_COUNTS, _SIGNATURES, _BACKGROUND, minus, policy))
        ) / (2.0 * epsilon)
        assert numerical == pytest.approx(gradient[index] - gradient[-1], abs=1e-8)


def test_nonstationary_zero_step_endpoint_is_not_an_initial_stationary_solution():
    report = _audit()
    assert report.iterations == 0
    assert report.recomputed_kkt_residual > 0.4
    assert report.stable_frank_wolfe_gap > 0.25
    assert report.zero_step_stationary is report.zero_step_endpoint_matches_initial is False
    assert report.legacy_trace_consistent is report.reported_converged is False
    assert report.legacy_benchmark_status == "solver_trace_invalid"


@pytest.mark.parametrize("boundary", ["all_unknown_zero", "one_unknown_zero"])
def test_boundary_unknown_coordinates_preserve_objective_and_unavailable_gradients(boundary):
    weights = (
        np.asarray([0.6, 0.4, 0.0, 0.0, 0.0, 0.0])
        if boundary == "all_unknown_zero"
        else np.asarray([0.45, 0.25, 0.0, 0.1, 0.1, 0.1])
    )
    solution = _synthetic_solution(weights=weights)
    report = _audit(solution=solution)
    assert report.objective_status == "available"
    assert report.objective_matches is True
    assert report.gradient_status == "boundary_unknown_zero"
    for name in (
        "recomputed_kkt_residual",
        "kkt_absolute_error",
        "kkt_matches",
        "default_stationary",
        "raw_frank_wolfe_gap",
        "stable_frank_wolfe_gap",
        "frank_wolfe_gap_difference",
    ):
        assert getattr(report, name) is None
    assert report.zero_step_stationary is None
    assert report.legacy_benchmark_status == "solver_trace_invalid"
    if boundary == "all_unknown_zero":
        assert report.recomputed_unknown_mass == 0.0
        assert report.recomputed_mass_penalty == report.recomputed_shape_penalty == 0.0


@pytest.mark.parametrize(
    "change", ["counts", "signatures", "background", "concentration", "mass", "initialization"]
)
def test_structurally_valid_stale_request_is_diagnosed_without_authenticating_or_repairing_it(
    change,
):
    policy, solution = _policy(), _synthetic_solution()
    counts, signatures, background = _COUNTS.copy(), _SIGNATURES.copy(), _BACKGROUND.copy()
    if change == "counts":
        counts[1] += 1
        counts[2] -= 1
    elif change == "signatures":
        signatures[:, 0] = signatures[::-1, 0]
    elif change == "background":
        background = background[::-1].copy()
    elif change == "concentration":
        policy = _policy(concentration=17.0)
    elif change == "mass":
        policy = _policy(lambda_mass=0.17)
    else:
        policy = _policy(initial_unknown_mass=0.4)
    report = _audit(
        counts=counts,
        signatures=signatures,
        background=background,
        policy=policy,
        solution=solution,
    )
    if change == "initialization":
        assert report.objective_matches is True
        assert report.initial_objective_matches is False
    else:
        assert report.objective_matches is False
    assert report.reconstructed_probabilities_match is (change != "signatures")
    assert report.source_provenance_authenticated is report.admission_changed is False


@pytest.mark.parametrize(
    "forgery", ["objective_trace", "fitted_probabilities", "kkt_trace", "condition"]
)
def test_internally_consistent_old_solution_cannot_supply_its_own_request_certificate(forgery):
    policy, original = _midpoint_solution(0.05)
    assert original.iterations == 1 and verify_objective_trace(original)
    if forgery == "objective_trace":
        delta = 0.125
        solution = replace(
            original,
            initial_objective=original.initial_objective + delta,
            objective=original.objective + delta,
            trace=tuple(replace(row, objective=row.objective + delta) for row in original.trace),
        )
    elif forgery == "fitted_probabilities":
        solution = replace(original, fitted_probabilities=np.asarray([0.2, 0.3, 0.5]))
    elif forgery == "kkt_trace":
        solution = replace(
            original, kkt_residual=0.25, trace=(replace(original.trace[0], kkt_residual=0.25),)
        )
    else:
        solution = replace(original, signature_condition_number=2.0)
    assert verify_objective_trace(solution) is True
    report = audit_simplex_solution([300] * 3, _MIDPOINT, _UNIFORM, policy, solution)
    if forgery == "objective_trace":
        assert report.objective_matches is report.initial_objective_matches is False
        assert report.objective_absolute_error == pytest.approx(0.125)
    elif forgery == "fitted_probabilities":
        assert report.reconstructed_probabilities_match is False
        assert report.fitted_probability_max_absolute_error == pytest.approx(1 / 6)
        assert report.objective_matches is True
    elif forgery == "kkt_trace":
        assert report.kkt_matches is False
        assert report.default_stationary is True
        assert report.legacy_benchmark_status == "solver_not_converged"
    else:
        assert report.recomputed_signature_condition_number == pytest.approx(1.0)
        assert report.condition_number_matches is False
    assert report.legacy_trace_consistent is True
    assert report.admission_changed is False


def test_changed_zero_step_endpoint_is_not_mistaken_for_the_reported_initialization():
    policy, solution = _midpoint_solution(0.2)
    altered = np.asarray([0.35, 0.35])
    unknown = np.asarray([0.1, 0.1, 0.1])
    stale = replace(
        solution,
        known_rna_weights=altered,
        unknown_gene_mass=unknown,
        unknown_mass=0.3,
        fitted_probabilities=_MIDPOINT @ altered + unknown,
    )
    report = audit_simplex_solution([300] * 3, _MIDPOINT, _UNIFORM, policy, stale)
    assert report.zero_step_endpoint_matches_initial is False
    assert report.initial_endpoint_max_absolute_error == pytest.approx(0.05)
    assert report.zero_step_stationary is True
    assert report.legacy_benchmark_status == "solver_trace_invalid"


@pytest.mark.parametrize("kind", ["single", "identical", "tiny_contrast"])
def test_conditioning_is_recomputed_from_the_actual_ordered_reference(kind):
    if kind == "single":
        signatures = _SIGNATURES[:, :1]
        weights = np.asarray([0.7, 0.1, 0.08, 0.07, 0.05])
        solution = _synthetic_solution(signatures=signatures, weights=weights)
    elif kind == "identical":
        signatures = np.column_stack((_SIGNATURES[:, 0], _SIGNATURES[:, 0]))
        solution = _synthetic_solution()
    else:
        first = _SIGNATURES[:, 0]
        signatures = np.column_stack((first, first + np.asarray([1e-10, -1e-10, 0.0, 0.0])))
        solution = _synthetic_solution()
    report = _audit(signatures=signatures, solution=solution)
    assert report.conditioning_status == "available"
    if kind == "single":
        assert report.recomputed_signature_condition_number == 1.0
        assert report.smallest_signature_contrast is None
        assert report.default_conditioning_passed is True
    else:
        assert report.default_conditioning_passed is False
        assert report.legacy_benchmark_status == "signature_conditioning_rejected"
        assert report.smallest_signature_contrast < 1e-8
        if kind == "identical":
            assert report.recomputed_signature_condition_number is None
            assert report.condition_number_absolute_error is None
            assert report.condition_number_matches is False


@pytest.mark.parametrize("field", ["counts", "signatures", "background"])
def test_masked_arrays_are_rejected_before_silently_using_their_underlying_values(field):
    values = {"counts": _COUNTS, "signatures": _SIGNATURES, "background": _BACKGROUND}
    masked = np.ma.array(values[field], mask=np.zeros(values[field].shape, dtype=bool))
    masked.mask.flat[0] = True
    with pytest.raises(SimplexAuditError):
        _audit(**{field: masked})


@pytest.mark.parametrize(
    "counts",
    [
        [],
        [0] * 4,
        [True, 255, 256, 257],
        [np.bool_(0), 255, 256, 257],
        [0.0, 255.0, 256.0, 257.0],
        [0, -1, 256, 257],
        [0, math.inf, 256, 257],
        [0, Decimal(255), 256, 257],
        [0, "255", 256, 257],
        [[0, 255, 256, 257]],
        [0, 2**63, 0, 0],
        [0, 2**63 - 1, 1, 0],
    ],
)
def test_counts_require_positive_total_exact_nonboolean_int64_mass(counts):
    with pytest.raises(SimplexAuditError):
        _audit(counts=counts)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("counts", [1, 2, 3]),
        ("signatures", np.ones((1, 2))),
        ("signatures", np.ones((4, 0))),
        ("signatures", _SIGNATURES.T),
        ("signatures", _SIGNATURES * 0.5),
        ("signatures", np.full((4, 2), math.nan)),
        ("signatures", np.full((4, 2), 0.0)),
        ("signatures", np.ones((4, 2), dtype=bool)),
        ("signatures", np.asarray(_SIGNATURES, dtype=complex)),
        ("background", [[0.1, 0.2, 0.3, 0.4]]),
        ("background", [0.5, 0.5]),
        ("background", [-0.1, 0.2, 0.3, 0.6]),
        ("background", [0.0, 0.2, 0.3, 0.5]),
        ("background", [0.1, 0.2, 0.3, math.inf]),
        ("background", [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]),
        ("policy", object()),
        ("solution", object()),
    ],
)
def test_request_axes_probability_domains_and_exact_internal_types_are_strict(field, value):
    with pytest.raises(SimplexAuditError):
        _audit(**{field: value})


def test_endpoint_axis_mismatch_is_rejected_instead_of_truncated():
    solution = _synthetic_solution()
    with pytest.raises(SimplexAuditError):
        audit_simplex_solution(_COUNTS, _SIGNATURES[:, :1], _BACKGROUND, _policy(), solution)


def test_request_arrays_and_original_solution_are_not_modified_or_resolved(monkeypatch):
    counts, signatures, background = _COUNTS.copy(), _SIGNATURES.copy(), _BACKGROUND.copy()
    solution = _synthetic_solution()
    arrays = (
        counts,
        signatures,
        background,
        solution.known_rna_weights,
        solution.unknown_gene_mass,
        solution.fitted_probabilities,
    )
    before = tuple((value.copy(), value.flags.writeable) for value in arrays)

    def forbidden(*_args, **_kwargs):
        pytest.fail("endpoint auditing must not call the optimizer")

    monkeypatch.setattr(
        "glio_proteogen.research.gbmap_deconvolution.simplex.solve_reference_mixture", forbidden
    )
    _audit(counts=counts, signatures=signatures, background=background, solution=solution)
    for array, (original, writeable) in zip(arrays, before, strict=True):
        np.testing.assert_array_equal(array, original)
        assert array.flags.writeable is writeable


def test_closed_scalar_report_roundtrips_without_source_vectors_or_admission_claims():
    report = _audit()
    document = report.model_dump(mode="json")
    assert report.audit_version == AUDIT_VERSION
    assert SimplexEndpointAudit.model_validate_json(report.model_dump_json()) == report
    assert not any(isinstance(value, (list, tuple, np.ndarray)) for value in document.values())
    assert not set(document) & {
        "counts",
        "signatures",
        "background",
        "trace",
        "gradient",
        "weights",
        "source_path",
        "request_digest",
        "accepted",
        "accepted_solution",
    }
    with pytest.raises(ValueError):
        report.count_depth = 1
    for name in (
        "admission_changed",
        "source_provenance_authenticated",
        "trajectory_replayed",
        "production_artifact_permitted",
        "numerical_interval_certified",
    ):
        assert document[name] is False
        for invalid in (True, 0, 1):
            with pytest.raises(ValueError):
                SimplexEndpointAudit.model_validate({**document, name: invalid})
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate_json(json.dumps({**document, "gradient": [0.0]}))


@pytest.mark.parametrize(
    "change",
    [
        {"legacy_benchmark_status": "scored"},
        {"weight_simplex_absolute_error": 0.5},
        {"reconstructed_probabilities_match": False},
        {"objective_matches": False},
        {"initial_objective_matches": False},
        {"kkt_matches": False},
        {"default_stationary": True},
        {"stable_frank_wolfe_gap": None},
        {"frank_wolfe_gap_difference": 1.0},
        {"default_conditioning_passed": False},
        {"condition_number_matches": False},
        {"zero_step_stationary": True},
        {"solver_configuration_digest": "sha256:" + "0" * 64},
    ],
)
def test_saved_scalars_cannot_contradict_comparisons_nulls_or_original_gates(change):
    report = _audit()
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate({**report.model_dump(mode="python"), **change})


def test_frank_wolfe_roundoff_and_simplex_closure_are_reported_without_certification():
    policy = _policy(lambda_mass=0.0, lambda_shape=0.0)
    scale = np.nextafter(np.nextafter(1.0, math.inf), math.inf)
    weights = np.asarray([0.4, 0.4, 1 / 15, 1 / 15, 1 / 15]) * scale
    solution = _synthetic_solution(
        counts=[1, 1, 1],
        signatures=_MIDPOINT,
        background=_UNIFORM,
        weights=weights,
        policy=policy,
    )
    report = audit_simplex_solution([1] * 3, _MIDPOINT, _UNIFORM, policy, solution)
    assert 0.0 < report.weight_simplex_absolute_error < 2e-12
    assert report.weight_simplex_absolute_error == abs(report.weight_simplex_sum - 1.0)
    assert report.default_stationary is True
    assert report.stable_frank_wolfe_gap >= 0.0
    assert abs(report.raw_frank_wolfe_gap) < 4e-15
    assert abs(report.frank_wolfe_gap_difference) < 4e-15
    assert report.numerical_interval_certified is False
    # A raw dot-product gap may have either rounding sign across platforms.
    # Its closed scalar codec must retain a negative ulp, rather than clipping
    # it into a purported nonnegative objective-gap certificate.
    document = report.model_dump(mode="python")
    document["raw_frank_wolfe_gap"] = -math.ulp(1.0)
    document["frank_wolfe_gap_difference"] = (
        document["raw_frank_wolfe_gap"] - report.stable_frank_wolfe_gap
    )
    restored = SimplexEndpointAudit.model_validate(document)
    assert restored.raw_frank_wolfe_gap == -math.ulp(1.0)
    assert restored.stable_frank_wolfe_gap == report.stable_frank_wolfe_gap


def test_inactive_known_coordinate_has_its_own_kkt_inequality():
    policy = _policy(lambda_mass=10.0)
    counts = np.asarray([300, 0, 0, 0], dtype=np.int64)
    weights = np.asarray([0.0, 0.7, 0.1, 0.08, 0.07, 0.05])
    gradient = _harmonic_gradient(counts, _SIGNATURES, _BACKGROUND, weights, policy)
    multiplier = math.fsum(float(value) for value in gradient[1:]) / 5
    active_residual = max(abs(float(value) - multiplier) for value in gradient[1:])
    inactive_residual = multiplier - float(gradient[0])
    assert inactive_residual > active_residual > 0.0
    solution = _synthetic_solution(counts=counts, weights=weights, policy=policy)
    report = _audit(counts=counts, policy=policy, solution=solution)
    assert report.recomputed_kkt_residual == pytest.approx(inactive_residual, abs=2e-12)
    assert report.kkt_matches is True
    assert report.default_stationary is False


@pytest.mark.parametrize("kind", ["underflowed_concentration", "overflowed_shape_gradient"])
def test_valid_extreme_policies_conserve_unavailable_numerics_instead_of_fabricating_zero(kind):
    policy = (
        _policy(concentration=5e-324)
        if kind == "underflowed_concentration"
        else _policy(lambda_shape=1.7e308)
    )
    report = _audit(policy=policy)
    assert report.gradient_status == "numerical_failure"
    assert report.recomputed_kkt_residual is report.kkt_matches is report.default_stationary is None
    assert report.raw_frank_wolfe_gap is report.stable_frank_wolfe_gap is None
    assert report.conditioning_status == "available"
    assert report.default_conditioning_passed is True
    if kind == "underflowed_concentration":
        assert report.objective_status == report.initial_objective_status == "numerical_failure"
        assert report.recomputed_objective is report.objective_matches is None
        assert report.recomputed_initial_objective is report.initial_objective_matches is None
    else:
        assert report.objective_status == report.initial_objective_status == "available"
        assert report.recomputed_objective is not None
    assert SimplexEndpointAudit.model_validate_json(report.model_dump_json()) == report
    assert report.admission_changed is False


@pytest.mark.parametrize("term", ["nll_sum", "mass_penalty", "shape_penalty"])
def test_saved_objective_terms_must_close_and_obey_the_declared_penalties(term):
    data = _audit().model_dump(mode="python")
    if term == "nll_sum":
        data["recomputed_nll"] += 0.1
    else:
        key = "recomputed_mass_penalty" if term == "mass_penalty" else "recomputed_shape_penalty"
        data[key] += 0.1
        # Keep the total/comparison coherent: the remaining contradiction is
        # specifically penalty != declared coefficient times its source term.
        data["recomputed_objective"] = (
            data["recomputed_nll"]
            + data["recomputed_mass_penalty"]
            + data["recomputed_shape_penalty"]
        )
        data["objective_absolute_error"] = abs(
            data["reported_objective"] - data["recomputed_objective"]
        )
        data["objective_matches"] = False
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


@pytest.mark.parametrize("group", ["objective", "initial_objective"])
def test_saved_unavailable_objective_cannot_retain_available_numbers_or_flags(group):
    data = _audit().model_dump(mode="python")
    data[f"{group}_status"] = "numerical_failure"
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


def test_saved_initial_objective_difference_cannot_be_forged_with_a_coherent_match_flag():
    data = _audit().model_dump(mode="python")
    data["recomputed_initial_objective"] += 0.125
    data["initial_objective_absolute_error"] = 0.0
    data["initial_objective_matches"] = True
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


@pytest.mark.parametrize("kind", ["boundary", "numerical_failure"])
def test_saved_unavailable_gradient_cannot_fabricate_a_stationarity_observation(kind):
    if kind == "boundary":
        solution = _synthetic_solution(weights=np.asarray([0.6, 0.4, 0.0, 0.0, 0.0, 0.0]))
        report = _audit(solution=solution)
    else:
        report = _audit(policy=_policy(lambda_shape=1.7e308))
    data = report.model_dump(mode="python")
    data["recomputed_kkt_residual"] = 0.0
    data["default_stationary"] = True
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("recomputed_signature_condition_number", 1.0),
        ("smallest_signature_contrast", 0.1),
        ("condition_number_absolute_error", 0.0),
        ("default_conditioning_passed", True),
        ("condition_number_matches", True),
    ],
)
def test_saved_failed_conditioning_cannot_fabricate_a_number_or_pass(key, value):
    data = _audit().model_dump(mode="python")
    data.update(
        conditioning_status="numerical_failure",
        recomputed_signature_condition_number=None,
        smallest_signature_contrast=None,
        condition_number_absolute_error=None,
        default_conditioning_passed=False,
        condition_number_matches=False,
        legacy_benchmark_status="signature_conditioning_rejected",
    )
    # This is a lawful scalar failure summary, not evidence a particular SVD
    # actually failed. Adding any numerical or passing evidence contradicts it.
    SimplexEndpointAudit.model_validate(data)
    data[key] = value
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


@pytest.mark.parametrize("contradiction", ["condition_two", "contrast_present"])
def test_saved_single_reference_conditioning_is_exactly_one_with_no_contrast(contradiction):
    signatures = _SIGNATURES[:, :1]
    solution = _synthetic_solution(
        signatures=signatures, weights=np.asarray([0.7, 0.1, 0.08, 0.07, 0.05])
    )
    data = _audit(signatures=signatures, solution=solution).model_dump(mode="python")
    if contradiction == "condition_two":
        data["recomputed_signature_condition_number"] = 2.0
        data["condition_number_absolute_error"] = 1.0
        data["condition_number_matches"] = False
    else:
        data["smallest_signature_contrast"] = 0.1
    data["default_conditioning_passed"] = False
    data["legacy_benchmark_status"] = "signature_conditioning_rejected"
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


@pytest.mark.parametrize("contrast", [None, 0.0])
def test_saved_finite_multicolumn_condition_requires_a_positive_contrast(contrast):
    data = _audit().model_dump(mode="python")
    data["smallest_signature_contrast"] = contrast
    data["default_conditioning_passed"] = False
    data["legacy_benchmark_status"] = "signature_conditioning_rejected"
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


def test_saved_convergence_claim_cannot_disagree_with_the_unchanged_legacy_status():
    policy, solution = _midpoint_solution(0.05)
    report = audit_simplex_solution([300] * 3, _MIDPOINT, _UNIFORM, policy, solution)
    assert report.legacy_benchmark_status == "scored"
    data = report.model_dump(mode="python")
    data["reported_converged"] = False
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


def test_saved_zero_step_trace_claim_cannot_rescue_the_original_nonempty_trace_gate():
    policy, solution = _midpoint_solution(0.2)
    report = audit_simplex_solution([300] * 3, _MIDPOINT, _UNIFORM, policy, solution)
    assert report.iterations == 0 and report.zero_step_stationary is True
    data = report.model_dump(mode="python")
    data["legacy_trace_consistent"] = True
    # This status follows the forged trace flag and the unchanged reported
    # converged=False, but zero iterations still cannot prove a scalar trace.
    data["legacy_benchmark_status"] = "solver_not_converged"
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


def test_saved_coherent_simplex_error_cannot_waive_endpoint_feasibility():
    data = _audit().model_dump(mode="python")
    data["weight_simplex_sum"] = 1.0 + 1e-9
    data["weight_simplex_absolute_error"] = abs(data["weight_simplex_sum"] - 1.0)
    with pytest.raises(ValueError):
        SimplexEndpointAudit.model_validate(data)


def test_controlled_conditioning_svd_failure_keeps_other_diagnostics_and_rejects_legacy_gate(
    monkeypatch,
):
    """Explicit fault injection; this is not an observed data-dependent SVD failure."""
    solution = _synthetic_solution()
    calls = []

    def unavailable(*_args, **_kwargs):
        calls.append(True)
        raise np.linalg.LinAlgError

    monkeypatch.setattr(np.linalg, "svd", unavailable)
    report = _audit(solution=solution)
    assert calls == [True]
    assert report.conditioning_status == "numerical_failure"
    assert report.recomputed_signature_condition_number is None
    assert report.smallest_signature_contrast is report.condition_number_absolute_error is None
    assert report.default_conditioning_passed is report.condition_number_matches is False
    assert report.legacy_benchmark_status == "signature_conditioning_rejected"
    assert report.objective_status == report.initial_objective_status == "available"
    assert report.objective_matches is report.initial_objective_matches is True
    assert report.gradient_status == "available"
    assert report.recomputed_kkt_residual is not None
    assert report.reconstructed_probabilities_match is report.unknown_mass_matches is True
    assert report.admission_changed is report.numerical_interval_certified is False
