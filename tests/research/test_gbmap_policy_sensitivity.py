"""Independent common-set estimands on synthetic, unauthenticated contexts.

Controlled point outcomes below test set arithmetic and metric denominators.
The separate stationary midpoint test executes unchanged default point solvers.
Internal synthetic builders do not authenticate source/checkpoint recovery.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.simplex import solve_reference_mixture
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixtureBenchmarkPlan,
    MixtureBenchmarkReceipt,
    score_replayed_fold,
)
from glio_proteogen.research.gbmap_mixture_benchmark import benchmark as point
from glio_proteogen.research.gbmap_policy_sensitivity import (
    MatchedPolicySensitivityReceipt,
    PolicySensitivityError,
    score_matched_policy_sensitivity,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)
from tests.research import test_gbmap_mixture_benchmark as fixture

_A, _B = fixture._KNOWN
_TRUTH = (0.4, 0.4, 0.2)
_POLICIES = (fixture._policy(concentration=10.0), fixture._policy(concentration=20.0))


def _cases(n):
    return tuple(
        fixture._case(counts=(300 * unit,) * 3, masses=(360 * unit, 360 * unit, 180 * unit))
        for unit in range(1, n + 1)
    )


def _controlled(monkeypatch, outcomes):
    """Explicit routing oracle; no numerical-fit claim is made for this helper."""
    calls = []

    def kernel(  # noqa: PLR0913 -- unchanged point-kernel interface for controlled routing.
        case,
        matrix,
        _background,
        policy,
        omitted,
        *,
        conditioning_rejected,
        configuration,
        cancellation,
    ):
        del configuration, cancellation
        key = (policy.concentration, int(case.selected_counts[0]) // 300)
        calls.append((key, omitted))
        if case.source_total_count_mass == 0:
            return "zero_source_count_depth"
        if case.selected_total_count_mass == 0:
            return "zero_selected_count_depth"
        if not matrix.shape[1]:
            return "no_reference_columns"
        if conditioning_rejected:
            return "signature_conditioning_rejected"
        predicted = outcomes[key]
        if isinstance(predicted, str):
            return predicted
        remaining = case.reclassify(omitted).remaining_known_labels
        truth = case.selected_rna_fractions
        assert truth is not None
        errors = tuple(
            predicted[fixture._KNOWN.index(label)]
            - float(truth[PRODUCTION_SOURCE_LABELS.index(label)])
            for label in remaining
        )
        unknown = predicted[2] + math.fsum(
            predicted[fixture._KNOWN.index(label)] for label in omitted
        )
        target = case.reclassify(omitted).selected_unknown_fraction
        assert target is not None
        unknown_error = unknown - float(target)
        return errors, unknown_error, 0.5 * math.fsum((*map(abs, errors), abs(unknown_error)))

    monkeypatch.setattr(point, "_score_case", kernel)
    return calls


def _run(context, policies=_POLICIES, *, omissions=()):
    plan = MixtureBenchmarkPlan(policies=policies, omissions=omissions)
    parent = score_replayed_fold(context, policies, omissions=omissions)
    return parent, score_matched_policy_sensitivity(context, plan, parent_benchmark=parent)


def test_equal_policy_counts_do_not_imply_equal_support(monkeypatch):
    outcomes = {
        (concentration, unit): _TRUTH
        if (concentration == 10.0) == (unit <= 2)
        else "solver_not_converged"
        for concentration in (10.0, 20.0)
        for unit in range(1, 5)
    }
    _controlled(monkeypatch, outcomes)
    parent, report = _run(fixture._context(_cases(4)))
    assert [row.scored_case_count for row in parent.results] == [2, 2]
    result = report.scenarios[0]
    assert (result.offered_case_count, result.all_policy_scored_case_count) == (4, 0)
    assert (result.some_policy_scored_case_count, result.no_policy_scored_case_count) == (4, 0)
    assert [row.excluded_from_common_case_count for row in result.policies] == [2, 2]
    assert all(row.mean_total_variation is None for row in result.policies)
    assert result.mean_unknown_mass_spread is result.max_unknown_mass_spread is None


def test_unmatched_apparent_ordering_reverses_on_the_common_case(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.3, 0.4, 0.3),
            (10.0, 2): (0.0, 0.0, 1.0),
            (10.0, 3): "solver_not_converged",
            (20.0, 1): (0.2, 0.4, 0.4),
            (20.0, 2): "solver_not_converged",
            (20.0, 3): _TRUTH,
        },
    )
    parent, report = _run(fixture._context(_cases(3)))
    assert [row.mean_total_variation for row in parent.results] == pytest.approx([0.45, 0.1])
    result = report.scenarios[0]
    assert (result.all_policy_scored_case_count, result.some_policy_scored_case_count) == (1, 2)
    assert [row.mean_total_variation for row in result.policies] == pytest.approx([0.1, 0.2])
    assert [row.original_scored_case_count for row in result.policies] == [2, 2]
    assert [row.excluded_from_common_case_count for row in result.policies] == [1, 1]
    assert report.policy_selection_performed is False


def test_full_support_reproduces_every_parent_metric_including_zero_truth_errors(monkeypatch):
    cases = (
        fixture._case(masses=(900, 0, 0)),
        fixture._case(counts=(600,) * 3, masses=(720, 720, 360)),
    )
    calls = _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.7, 0.2, 0.1),
            (10.0, 2): _TRUTH,
            (20.0, 1): (0.6, 0.3, 0.1),
            (20.0, 2): (0.3, 0.3, 0.4),
        },
    )
    parent, report = _run(fixture._context(cases))
    result = report.scenarios[0]
    assert result.all_policy_scored_case_count == result.offered_case_count == 2
    assert result.some_policy_scored_case_count == result.no_policy_scored_case_count == 0
    assert len(calls) == 8  # One parent pass, one independent reconstruction pass.
    for matched, original in zip(result.policies, parent.results, strict=True):
        assert matched.excluded_from_common_case_count == 0
        assert matched.mean_total_variation == original.mean_total_variation
        assert matched.mean_unknown_signed_error == original.mean_unknown_signed_error
        assert matched.mean_unknown_absolute_error == original.mean_unknown_absolute_error
        assert matched.labels == original.labels
        rows = {row.modeled_label: row for row in matched.labels}
        assert rows[_B].scored_visibility.source_zero == 1
        assert rows[_B].mean_absolute_error > 0.0
        assert rows[fixture._UNKNOWN].mean_absolute_error is None


def test_one_failed_policy_does_not_trigger_subset_rescue(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (concentration, unit): _TRUTH if concentration == 10.0 else "solver_rejected"
            for concentration in (10.0, 20.0)
            for unit in range(1, 4)
        },
    )
    parent, report = _run(fixture._context(_cases(3)))
    result = report.scenarios[0]
    assert [row.scored_case_count for row in parent.results] == [3, 0]
    assert [row.excluded_from_common_case_count for row in result.policies] == [3, 0]
    assert result.all_policy_scored_case_count == result.no_policy_scored_case_count == 0
    assert result.some_policy_scored_case_count == 3
    assert all(row.mean_total_variation is None for row in result.policies)
    assert all(row.scored_visibility.total == 0 for p in result.policies for row in p.labels)


def test_unknown_spread_uses_only_common_cases_and_is_not_an_interval(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.45, 0.45, 0.1),
            (20.0, 1): (0.3, 0.3, 0.4),
            (10.0, 2): (0.4, 0.4, 0.2),
            (20.0, 2): (0.1, 0.1, 0.8),
            (10.0, 3): (0.0, 0.0, 1.0),
            (20.0, 3): "solver_numerical_failure",
        },
    )
    _, report = _run(fixture._context(_cases(3)))
    result = report.scenarios[0]
    assert result.all_policy_scored_case_count == 2
    assert result.mean_unknown_mass_spread == pytest.approx(0.45)
    assert result.max_unknown_mass_spread == pytest.approx(0.6)
    assert report.calibration_performed is report.empirical_unit_independence_established is False
    assert report.clinical_validity_established is False


def test_genuine_midpoint_solvers_reconstruct_identically_with_different_unknown_mass():
    context = fixture._context((fixture._case(),))
    policies = tuple(fixture._policy(lambda_shape=1.0, initial_unknown_mass=u) for u in (0.05, 0.8))
    solutions = tuple(
        solve_reference_mixture(
            context.held_truth.cases[0].selected_counts,
            context.signatures,
            context.background,
            concentration=policy.concentration,
            lambda_mass=policy.lambda_mass,
            lambda_shape=policy.lambda_shape,
            initial_unknown_mass=policy.initial_unknown_mass,
        )
        for policy in policies
    )
    assert all(solution.converged for solution in solutions)
    np.testing.assert_allclose(
        solutions[0].fitted_probabilities, solutions[1].fitted_probabilities, rtol=0.0, atol=1e-12
    )
    parent, report = _run(context, policies)
    assert [row.scored_case_count for row in parent.results] == [1, 1]
    result = report.scenarios[0]
    assert result.all_policy_scored_case_count == 1
    assert result.mean_unknown_mass_spread == pytest.approx(0.75, abs=1e-12)
    assert result.max_unknown_mass_spread == pytest.approx(0.75, abs=1e-12)
    assert [row.mean_total_variation for row in result.policies] == pytest.approx([0.15, 0.6])


def test_original_trace_rejection_remains_a_failure_in_the_common_set():
    policies = tuple(fixture._policy(initial_unknown_mass=u) for u in (0.05, 0.2))
    parent, report = _run(fixture._context((fixture._case(),)), policies)
    assert [row.scored_case_count for row in parent.results] == [1, 0]
    rejected = {row.reason: row.count for row in parent.results[1].terminal_counts}
    assert rejected["solver_trace_invalid"] == 1
    assert report.scenarios[0].all_policy_scored_case_count == 0
    assert report.scenarios[0].mean_unknown_mass_spread is None


def test_source_and_selected_zero_cases_keep_their_original_denominators(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): _TRUTH, (20.0, 1): _TRUTH})
    context = fixture._context(
        (
            fixture._case(counts=(0,) * 3, masses=(0,) * 3),
            fixture._case(counts=(0,) * 3, masses=(0,) * 3, source_extra=900),
            fixture._case(),
        )
    )
    parent, report = _run(context)
    result = report.scenarios[0]
    assert result.offered_case_count == 3
    assert result.all_policy_scored_case_count == 1
    assert result.no_policy_scored_case_count == 2
    assert result.some_policy_scored_case_count == 0
    assert all(row.scored_case_count == 1 for row in parent.results)
    assert all(row.offered_visibility.total == 3 for p in result.policies for row in p.labels)
    assert all(row.scored_visibility.total == 1 for p in result.policies for row in p.labels)


def test_omission_scenarios_keep_separate_targets_and_all_column_failure(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (20.0, 1): (0.2, 0.4, 0.4)})
    _, report = _run(fixture._context((fixture._case(),)), omissions=((_A, _B), (_A,)))
    assert [row.omitted_labels for row in report.scenarios] == [(), (_A,), (_A, _B)]
    for scenario in report.scenarios[:2]:
        assert scenario.all_policy_scored_case_count == 1
        for policy in scenario.policies:
            labels = {row.modeled_label: row for row in policy.labels}
            assert labels[_A].modeled is (_A not in scenario.omitted_labels)
            if _A in scenario.omitted_labels:
                assert labels[_A].mean_absolute_error is None
    # Coarsening merges the entire baseline error into unknown truth here;
    # lower cross-scenario TV is therefore not an accuracy improvement.
    omitted = report.scenarios[1]
    assert [row.mean_total_variation for row in omitted.policies] == pytest.approx([0.0, 0.0])
    assert omitted.mean_unknown_mass_spread == pytest.approx(0.0)
    empty = report.scenarios[-1]
    assert (empty.all_policy_scored_case_count, empty.no_policy_scored_case_count) == (0, 1)
    assert all(not label.modeled for p in empty.policies for label in p.labels)


def test_case_and_outer_policy_permutations_preserve_the_aggregate(monkeypatch):
    outcomes = {
        (concentration, unit): _TRUTH if unit != int(concentration / 10) else "solver_not_converged"
        for concentration in (10.0, 20.0)
        for unit in range(1, 4)
    }
    _controlled(monkeypatch, outcomes)
    cases = _cases(3)
    _, first = _run(fixture._context(cases))
    _, second = _run(fixture._context((cases[2], cases[0], cases[1])), tuple(reversed(_POLICIES)))
    assert first == second


def test_one_policy_has_full_own_support_and_zero_spread(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (10.0, 2): "solver_not_converged"})
    _, report = _run(fixture._context(_cases(2)), (_POLICIES[0],))
    result = report.scenarios[0]
    assert (result.all_policy_scored_case_count, result.some_policy_scored_case_count) == (1, 0)
    assert result.no_policy_scored_case_count == 1
    assert result.policies[0].excluded_from_common_case_count == 0
    assert result.mean_unknown_mass_spread == result.max_unknown_mass_spread == 0.0


def test_parent_aggregate_parity_cannot_authenticate_original_case_assignments(monkeypatch):
    first = {
        (concentration, unit): _TRUTH if unit <= 2 else "solver_not_converged"
        for concentration in (10.0, 20.0)
        for unit in range(1, 5)
    }
    _controlled(monkeypatch, first)
    context = fixture._context(_cases(4))
    plan = MixtureBenchmarkPlan(policies=_POLICIES)
    parent = score_replayed_fold(context, plan.policies)
    second = {
        (concentration, unit): _TRUTH
        if (concentration == 10.0) == (unit <= 2)
        else "solver_not_converged"
        for concentration in (10.0, 20.0)
        for unit in range(1, 5)
    }
    _controlled(monkeypatch, second)
    assert score_replayed_fold(context, plan.policies) == parent
    report = score_matched_policy_sensitivity(context, plan, parent_benchmark=parent)
    assert report.parent_benchmark == parent
    assert report.scenarios[0].all_policy_scored_case_count == 0


def test_common_label_observability_cannot_differ_between_policies(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): _TRUTH,
            (10.0, 2): _TRUTH,
            (20.0, 1): _TRUTH,
            (20.0, 2): "solver_not_converged",
        },
    )
    cases = (fixture._case(), fixture._case(counts=(600,) * 3, masses=(0, 1800, 0)))
    _, report = _run(fixture._context(cases))
    data = report.model_dump(mode="python")
    label = next(
        row for row in data["scenarios"][0]["policies"][0]["labels"] if row["modeled_label"] == _A
    )
    label["scored_visibility"]["selected_positive"] = 0
    label["scored_visibility"]["source_zero"] = 1
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_closed_consistent_parent_with_forged_metrics_fails_exact_reconstruction(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3)})
    context = fixture._context((fixture._case(),))
    policies = (_POLICIES[0],)
    parent = score_replayed_fold(context, policies)
    data = parent.model_dump(mode="python")
    row = data["results"][0]
    row["mean_total_variation"] = 0.2
    row["mean_unknown_signed_error"] = row["mean_unknown_absolute_error"] = 0.2
    label = next(label for label in row["labels"] if label["modeled_label"] == _A)
    label["mean_signed_error"], label["mean_absolute_error"] = -0.2, 0.2
    forged = MixtureBenchmarkReceipt.model_validate(data)
    with pytest.raises(PolicySensitivityError):
        score_matched_policy_sensitivity(
            context, MixtureBenchmarkPlan(policies=policies), parent_benchmark=forged
        )


@pytest.mark.parametrize("change", ["policies", "omissions", "context"])
def test_parent_plan_or_context_mismatch_stops_before_point_work(monkeypatch, change):
    _controlled(monkeypatch, {(10.0, 1): _TRUTH})
    context = fixture._context((fixture._case(),))
    plan = MixtureBenchmarkPlan(policies=(_POLICIES[0],))
    parent = score_replayed_fold(context, plan.policies)
    if change == "policies":
        plan = MixtureBenchmarkPlan(policies=(_POLICIES[1],))
    elif change == "omissions":
        plan = MixtureBenchmarkPlan(policies=plan.policies, omissions=((_A,),))
    else:
        payload = parent.model_dump(mode="python")
        payload["context_receipt"]["reviewed_sha256"] = "sha256:" + "a" * 64
        parent = MixtureBenchmarkReceipt.model_validate(payload)

    def unexpected(*_args, **_kwargs):
        pytest.fail("parent mismatch must stop before numerical work")

    monkeypatch.setattr(point, "_score_case", unexpected)
    with pytest.raises(PolicySensitivityError):
        score_matched_policy_sensitivity(context, plan, parent_benchmark=parent)


def test_cancellation_propagates_before_any_point_work():
    context = fixture._context((fixture._case(),))
    plan = MixtureBenchmarkPlan(policies=(_POLICIES[0],))
    parent = score_replayed_fold(context, plan.policies)
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        score_matched_policy_sensitivity(
            context, plan, parent_benchmark=parent, cancellation=cancellation
        )


def test_closed_report_roundtrip_preserves_singleton_aggregate_values(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (20.0, 1): (0.2, 0.4, 0.4)})
    _, report = _run(fixture._context((fixture._case(),)))
    assert MatchedPolicySensitivityReceipt.model_validate_json(report.model_dump_json()) == report
    assert report.scenarios[0].policies[0].mean_total_variation == pytest.approx(0.1)
    assert set(report.model_dump()) == {
        "scope_version",
        "parent_benchmark",
        "scenarios",
        "policy_selection_performed",
        "calibration_performed",
        "empirical_unit_independence_established",
        "clinical_validity_established",
    }


def _forge_transfer(policy, error):
    """A closed-simplex error forgery, independent of retained parent totals."""
    policy["mean_total_variation"] = error
    policy["mean_unknown_signed_error"] = policy["mean_unknown_absolute_error"] = error
    label = next(row for row in policy["labels"] if row["modeled_label"] == _A)
    label["mean_signed_error"], label["mean_absolute_error"] = -error, error


def test_parent_error_means_cannot_change_when_common_support_is_full(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3)})
    _, report = _run(fixture._context((fixture._case(),)), (_POLICIES[0],))
    data = report.model_dump(mode="python")
    _forge_transfer(data["scenarios"][0]["policies"][0], 0.2)
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_parent_error_totals_bound_the_common_subset_error(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.3, 0.4, 0.3),
            (10.0, 2): _TRUTH,
            (20.0, 1): (0.3, 0.4, 0.3),
            (20.0, 2): "solver_not_converged",
        },
    )
    _, report = _run(fixture._context(_cases(2)))
    data = report.model_dump(mode="python")
    scenario = data["scenarios"][0]
    _forge_transfer(scenario["policies"][0], 0.2)
    # Parent A has total absolute error .1 over two cases. Its common subset
    # cannot alone contribute .2, even though both summaries close a simplex.
    scenario["mean_unknown_mass_spread"] = scenario["max_unknown_mass_spread"] = 0.1
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


@pytest.mark.parametrize(
    "corruption",
    [
        "partition",
        "policy_scored",
        "excluded",
        "label_common",
        "arithmetic",
        "scenario",
        "flag",
        "private_extra",
    ],
)
def test_saved_report_rejects_inconsistent_support_metrics_or_extra_records(
    monkeypatch, corruption
):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (20.0, 1): (0.2, 0.4, 0.4)})
    _, report = _run(fixture._context((fixture._case(),)))
    data = copy.deepcopy(report.model_dump(mode="python"))
    scenario = data["scenarios"][0]
    policy = scenario["policies"][0]
    if corruption == "partition":
        scenario["some_policy_scored_case_count"] = 1
    elif corruption == "policy_scored":
        policy["original_scored_case_count"] = 2
    elif corruption == "excluded":
        policy["excluded_from_common_case_count"] = 1
    elif corruption == "label_common":
        policy["labels"][0]["scored_visibility"]["source_zero"] += 1
    elif corruption == "arithmetic":
        policy["mean_total_variation"] = 0.9
    elif corruption == "scenario":
        data["scenarios"] = ()
    elif corruption == "flag":
        data["calibration_performed"] = True
    else:
        scenario["case_errors"] = [0.1]
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


@pytest.mark.parametrize(("mean", "maximum"), [(0.8, 0.1), (0.0, 0.0), (0.1, 0.2)])
def test_saved_singleton_spread_respects_bias_range_and_mean_max_identity(
    monkeypatch, mean, maximum
):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (20.0, 1): (0.2, 0.4, 0.4)})
    _, report = _run(fixture._context((fixture._case(),)))
    data = report.model_dump(mode="python")
    data["scenarios"][0]["mean_unknown_mass_spread"] = mean
    data["scenarios"][0]["max_unknown_mass_spread"] = maximum
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


@pytest.mark.parametrize("argument", ["context", "plan", "parent_benchmark"])
def test_exact_private_api_types_are_required_before_point_work(monkeypatch, argument):
    _controlled(monkeypatch, {(10.0, 1): _TRUTH})
    context = fixture._context((fixture._case(),))
    plan = MixtureBenchmarkPlan(policies=(_POLICIES[0],))
    parent = score_replayed_fold(context, plan.policies)
    inputs = {"context": context, "plan": plan, "parent_benchmark": parent}
    inputs[argument] = object()

    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid API types must stop before point work")

    monkeypatch.setattr(point, "_score_case", unexpected)
    with pytest.raises(PolicySensitivityError):
        score_matched_policy_sensitivity(**inputs)


@pytest.mark.parametrize("has_common", [False, True])
def test_spread_availability_tracks_common_success_not_offered_depth(monkeypatch, has_common):
    _controlled(
        monkeypatch,
        {(10.0, 1): _TRUTH, (20.0, 1): _TRUTH if has_common else "solver_not_converged"},
    )
    _, report = _run(fixture._context((fixture._case(),)))
    data = report.model_dump(mode="python")
    data["scenarios"][0]["mean_unknown_mass_spread"] = None if has_common else 0.0
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_saved_report_cannot_remove_a_policy_from_the_declared_comparison(monkeypatch):
    _controlled(monkeypatch, {(10.0, 1): (0.3, 0.4, 0.3), (20.0, 1): (0.2, 0.4, 0.4)})
    _, report = _run(fixture._context((fixture._case(),)))
    data = report.model_dump(mode="python")
    scenario = data["scenarios"][0]
    scenario["policies"] = scenario["policies"][:1]
    scenario["mean_unknown_mass_spread"] = scenario["max_unknown_mass_spread"] = 0.0
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_saved_report_cannot_swap_original_policy_success_counts(monkeypatch):
    outcomes = {
        (concentration, unit): _TRUTH
        if unit in ({1, 2, 3} if concentration == 10.0 else {1, 4})
        else "solver_not_converged"
        for concentration in (10.0, 20.0)
        for unit in range(1, 5)
    }
    _controlled(monkeypatch, outcomes)
    _, report = _run(fixture._context(_cases(4)))
    data = report.model_dump(mode="python")
    first, second = data["scenarios"][0]["policies"]
    first["original_scored_case_count"], first["excluded_from_common_case_count"] = 2, 1
    second["original_scored_case_count"], second["excluded_from_common_case_count"] = 3, 2
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_saved_report_cannot_change_the_parent_offered_label_population(monkeypatch):
    _controlled(
        monkeypatch,
        {(10.0, 1): _TRUTH, (10.0, 2): _TRUTH, (20.0, 1): _TRUTH, (20.0, 2): "solver_rejected"},
    )
    cases = (fixture._case(), fixture._case(counts=(600,) * 3, masses=(0, 1800, 0)))
    _, report = _run(fixture._context(cases))
    data = report.model_dump(mode="python")
    for policy in data["scenarios"][0]["policies"]:
        label = next(row for row in policy["labels"] if row["modeled_label"] == _A)
        label["offered_visibility"]["source_zero"] = 0
        label["offered_visibility"]["selected_positive"] = 2
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_excluded_signed_error_cannot_exceed_its_remaining_absolute_error(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.3, 0.4, 0.3),
            (10.0, 2): (0.3, 0.4, 0.3),
            (20.0, 1): (0.5, 0.4, 0.1),
            (20.0, 2): "solver_not_converged",
        },
    )
    _, report = _run(fixture._context(_cases(2)))
    data = report.model_dump(mode="python")
    scenario = data["scenarios"][0]
    policy = scenario["policies"][0]
    policy["mean_unknown_signed_error"] = -0.1
    label = next(row for row in policy["labels"] if row["modeled_label"] == _A)
    label["mean_signed_error"] = 0.1
    scenario["mean_unknown_mass_spread"] = scenario["max_unknown_mass_spread"] = 0.0
    # Parent unknown error sum is +.2 and MAE sum .2. The forged common
    # bias -.1 leaves excluded bias +.3 with only .1 absolute error.
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_common_visibility_obeys_categorywise_frechet_intersection_bounds(monkeypatch):
    outcomes = {
        (10.0, 1): (1.0, 0.0, 0.0),
        (10.0, 2): (0.0, 1.0, 0.0),
        (10.0, 3): "solver_not_converged",
        (20.0, 1): (1.0, 0.0, 0.0),
        (20.0, 2): "solver_not_converged",
        (20.0, 3): (0.0, 1.0, 0.0),
    }
    _controlled(monkeypatch, outcomes)
    cases = (
        fixture._case(masses=(900, 0, 0)),
        fixture._case(counts=(600,) * 3, masses=(0, 1800, 0)),
        fixture._case(counts=(900,) * 3, masses=(0, 2700, 0)),
    )
    _, report = _run(fixture._context(cases))
    data = report.model_dump(mode="python")
    for policy in data["scenarios"][0]["policies"]:
        label = next(row for row in policy["labels"] if row["modeled_label"] == _A)
        label["scored_visibility"]["selected_positive"] = 0
        label["scored_visibility"]["source_zero"] = 1
    # Both parents score the only A-positive offered case. Their common
    # population necessarily includes it, despite the valid categorywise maxima.
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_zero_unknown_error_under_every_policy_forces_zero_spread(monkeypatch):
    _controlled(
        monkeypatch,
        {(concentration, unit): _TRUTH for concentration in (10.0, 20.0) for unit in (1, 2)},
    )
    _, report = _run(fixture._context(_cases(2)))
    data = report.model_dump(mode="python")
    data["scenarios"][0]["mean_unknown_mass_spread"] = 0.5
    data["scenarios"][0]["max_unknown_mass_spread"] = 0.5
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)


def test_spread_is_at_least_the_range_of_absolute_unknown_errors(monkeypatch):
    _controlled(
        monkeypatch,
        {
            (10.0, 1): (0.15, 0.15, 0.7),
            (10.0, 2): (0.35, 0.35, 0.3),
            (20.0, 1): (0.05, 0.05, 0.9),
            (20.0, 2): (0.45, 0.45, 0.1),
        },
    )
    cases = (
        fixture._case(masses=(225, 225, 450)),
        fixture._case(counts=(600,) * 3, masses=(450, 450, 900)),
    )
    _, report = _run(fixture._context(cases))
    data = report.model_dump(mode="python")
    data["scenarios"][0]["mean_unknown_mass_spread"] = 0.0
    data["scenarios"][0]["max_unknown_mass_spread"] = 0.0
    # Signed biases cancel under both policies, while MAEs differ by .2.
    with pytest.raises(ValueError):
        MatchedPolicySensitivityReceipt.model_validate(data)
