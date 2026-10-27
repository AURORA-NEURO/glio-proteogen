"""Independent point-metric and nonidentifiability oracles on synthetic counts.

The internal contexts below exercise point scoring only. They are not source
replay fixtures or evidence that synthetic receipt digests authenticate fitting.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapNumericalError
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.simplex import (
    reference_mixture_objective,
    solve_reference_mixture,
)
from glio_proteogen.research.gbmap_held_mixture_truth import (
    EmpiricalMixtureCase,
    HeldMixtureTruth,
    HeldMixtureTruthReceipt,
    LabelTruthCoverage,
    UnitCoverageLedger,
)
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixtureBenchmarkError,
    MixtureBenchmarkReceipt,
    MixturePointPolicy,
    score_replayed_fold,
)
from glio_proteogen.research.gbmap_mixture_benchmark import benchmark as bench
from glio_proteogen.research.gbmap_selected_fold_replay import SelectedFoldReplayReceipt
from glio_proteogen.research.gbmap_selected_fold_replay.model import _build_result
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

_KNOWN = ("Mural cell", "Oligodendrocyte")
_UNKNOWN = "Neuron"
_SIGNATURES = np.array([[0.5, 1 / 6], [1 / 6, 0.5], [1 / 3, 1 / 3]])
_BACKGROUND = np.ones(3) / 3


def _case(counts=(300, 300, 300), masses=(360, 360, 180), *, source_extra=0):
    selected = tuple(
        masses[(*_KNOWN, _UNKNOWN).index(label)] if label in (*_KNOWN, _UNKNOWN) else 0
        for label in PRODUCTION_SOURCE_LABELS
    )
    source = tuple(
        value + (source_extra if label == _UNKNOWN else 0)
        for label, value in zip(PRODUCTION_SOURCE_LABELS, selected, strict=True)
    )
    return EmpiricalMixtureCase(tuple(counts), source, selected, _KNOWN)


def _context(cases, *, signatures=_SIGNATURES, background=_BACKGROUND):
    """An explicitly synthetic private-builder context; no source recovery claim."""
    cases = tuple(cases)
    n = len(cases)
    labels = []
    for index, label in enumerate(PRODUCTION_SOURCE_LABELS):
        positive = sum(case.source_label_count_mass[index] > 0 for case in cases)
        selected = sum(case.selected_label_count_mass[index] > 0 for case in cases)
        labels.append(
            LabelTruthCoverage(
                modeled_label=label,
                known_in_context=label in _KNOWN,
                held_record_count=n,
                held_reference_eligible_record_count=0,
                held_source_positive_unit_count=positive,
                held_selected_positive_unit_count=selected,
                held_source_positive_selected_zero_unit_count=positive - selected,
                held_source_zero_unit_count=n - positive,
                held_missing_record_unit_count=0,
            )
        )
    truth_receipt = HeldMixtureTruthReceipt(
        fold_id="whole-study-0001",
        kind="whole_study",
        fold_evaluable=True,
        source_feature_count=4,
        selected_feature_count=3,
        known_label_count=2,
        held_unit_count=n,
        held_raw_record_count=20 * n,
        held_reference_eligible_record_count=0,
        ready_case_count=sum(case.selected_total_count_mass > 0 for case in cases),
        zero_source_depth_case_count=sum(case.source_total_count_mass == 0 for case in cases),
        zero_selected_depth_case_count=sum(
            case.source_total_count_mass > 0 and case.selected_total_count_mass == 0
            for case in cases
        ),
        labels=tuple(labels),
        unit_coverage=UnitCoverageLedger(
            source_unit_count=n,
            split_assigned_unit_count=n,
            unassigned_unit_count=0,
            whole_study_held_once_unit_count=n,
            within_study_held_once_unit_count=n,
            within_study_unheld_assigned_unit_count=0,
            source_raw_record_count=20 * n,
            split_assigned_raw_record_count=20 * n,
            unassigned_raw_record_count=0,
        ),
    )
    truth = HeldMixtureTruth(cases, truth_receipt)
    feature_indices = (2, 0, 3)
    feature_digest = sha256_digest({"synthetic_feature_axis": 4})
    digest = sha256_digest({"synthetic_receipt_not_source_evidence": True})
    receipt = SelectedFoldReplayReceipt(
        fold_id=truth_receipt.fold_id,
        kind=truth_receipt.kind,
        selected_shrinkage_index=0,
        selected_shrinkage=0.1,
        selected_feature_count=3,
        known_labels=_KNOWN,
        manifest_digest=digest,
        selection_receipt_digest=digest,
        checkpoint_set_digest=digest,
        reviewed_sha256=digest,
        feature_order_digest=feature_digest,
        selected_feature_axis_digest=sha256_digest(
            {
                "schema": "gbmap-selected-feature-axis/1.0.0",
                "feature_order_digest": feature_digest,
                "feature_indices": list(feature_indices),
            }
        ),
        profile_digest=digest,
        engine_semantic_digest=digest,
        training_configuration_digest=digest,
        replayed_checkpoint_count=2,
        held_truth=truth_receipt,
    )
    return _build_result(
        receipt=receipt,
        feature_indices=feature_indices,
        signatures=signatures,
        background=background,
        hierarchy_concentrations=(40.0, 80.0),
        held_truth=truth,
    )


def _policy(**changes):
    return MixturePointPolicy(
        **{
            "concentration": 100.0,
            "lambda_mass": 0.0,
            "lambda_shape": 0.1,
            "initial_unknown_mass": 0.05,
            **changes,
        }
    )


def _terminals(result):
    return {row.reason: row.count for row in result.terminal_counts}


def test_identical_counts_with_distinct_unknown_truth_cannot_both_be_recovered(monkeypatch):
    first = _case()
    second = _case(masses=(90, 90, 720))
    context = _context((first, second))
    policy = _policy()
    predictions = []
    original = bench.solve_reference_mixture

    def record(*args, **kwargs):
        result = original(*args, **kwargs)
        predictions.append(result)
        return result

    monkeypatch.setattr(bench, "solve_reference_mixture", record)
    receipt = score_replayed_fold(context, (policy,))
    result = receipt.results[0]
    assert len(predictions) == result.scored_case_count == result.offered_case_count == 2
    assert all(prediction.converged for prediction in predictions)
    np.testing.assert_array_equal(
        predictions[0].known_rna_weights, predictions[1].known_rna_weights
    )
    assert predictions[0].unknown_mass == predictions[1].unknown_mass
    assert first.reclassify().selected_unknown_fraction == Fraction(1, 5)
    assert second.reclassify().selected_unknown_fraction == Fraction(4, 5)
    assert result.mean_unknown_signed_error == pytest.approx(-0.45, abs=1e-12)
    assert result.mean_unknown_absolute_error == pytest.approx(0.45, abs=1e-12)
    assert result.mean_total_variation == pytest.approx(0.45, abs=1e-12)
    rows = {row.modeled_label: row for row in result.labels}
    for label in _KNOWN:
        assert rows[label].mean_signed_error == pytest.approx(0.225, abs=1e-12)
        assert rows[label].mean_absolute_error == pytest.approx(0.225, abs=1e-12)
    assert rows[_UNKNOWN].modeled is False
    assert rows[_UNKNOWN].mean_absolute_error is None
    assert receipt.policy_selection_performed is receipt.calibration_performed is False


def test_distinct_decompositions_have_identical_objective_when_background_is_the_midpoint():
    signatures = np.array([[0.8, 0.1], [0.1, 0.8], [0.1, 0.1]])
    background = np.array([0.45, 0.45, 0.1])
    objectives = []
    for unknown in (0.2, 0.8):
        known = np.array([(1 - unknown) / 2] * 2)
        residual = unknown * background
        np.testing.assert_allclose(signatures @ known + residual, background, atol=1e-15)
        objectives.append(
            reference_mixture_objective(
                [450, 450, 100],
                signatures,
                background,
                known,
                residual,
                concentration=100.0,
                lambda_mass=0.0,
                lambda_shape=0.1,
            )
        )
    assert objectives[0] == pytest.approx(objectives[1], abs=1e-14)


def test_mean_absolute_error_does_not_disappear_when_signed_errors_cancel():
    context = _context((_case(masses=(720, 90, 90)), _case(masses=(90, 720, 90))))
    result = score_replayed_fold(context, (_policy(),)).results[0]
    rows = {row.modeled_label: row for row in result.labels}
    for label in _KNOWN:
        assert rows[label].mean_signed_error == pytest.approx(0.025, abs=1e-12)
        assert rows[label].mean_absolute_error == pytest.approx(0.35, abs=1e-12)
    assert result.mean_unknown_signed_error == pytest.approx(-0.05, abs=1e-12)
    assert result.mean_unknown_absolute_error == pytest.approx(0.05, abs=1e-12)
    assert result.mean_total_variation == pytest.approx(0.375, abs=1e-12)


def test_all_offered_cases_partition_without_giving_failed_cases_zero_error():
    maximum = int(np.iinfo(np.int64).max)
    cases = (
        _case(),
        _case((0, 0, 0), (0, 0, 0)),
        _case((0, 0, 0), (0, 0, 0), source_extra=17),
        _case((maximum, 1, 0), (maximum + 1, 0, 0)),
    )
    result = score_replayed_fold(_context(cases), (_policy(),)).results[0]
    counts = _terminals(result)
    assert result.offered_case_count == 4
    assert result.scored_case_count == 1
    assert counts["zero_source_count_depth"] == 1
    assert counts["zero_selected_count_depth"] == 1
    assert counts["selected_depth_exceeds_int64"] == 1
    assert sum(counts.values()) == 3
    assert result.mean_total_variation == pytest.approx(0.15, abs=1e-12)
    row = next(row for row in result.labels if row.modeled_label == _UNKNOWN)
    assert row.offered_visibility.model_dump() == {
        "source_zero": 2,
        "source_positive_selected_zero": 1,
        "selected_positive": 1,
    }
    assert row.scored_visibility.model_dump() == {
        "source_zero": 0,
        "source_positive_selected_zero": 0,
        "selected_positive": 1,
    }


def test_original_source_depth_above_int64_does_not_gate_supported_selected_counts():
    case = _case(source_extra=2**63)
    assert case.source_total_count_mass > np.iinfo(np.int64).max
    assert case.selected_total_count_mass == 900
    result = score_replayed_fold(_context((case,)), (_policy(),)).results[0]
    assert result.scored_case_count == 1
    assert sum(_terminals(result).values()) == 0


def test_zero_truth_for_a_modeled_label_still_counts_false_positive_mass():
    case = _case(masses=(0, 0, 900))
    result = score_replayed_fold(_context((case,)), (_policy(),)).results[0]
    rows = {row.modeled_label: row for row in result.labels}
    assert result.scored_case_count == 1
    for label in _KNOWN:
        assert rows[label].scored_visibility.source_zero == 1
        assert rows[label].mean_absolute_error == pytest.approx(0.475, abs=1e-12)
    assert result.mean_total_variation == pytest.approx(0.95, abs=1e-12)


def test_column_withholding_preserves_counts_background_and_remaining_columns(monkeypatch):
    context = _context((_case(),))
    observed = []
    original = bench.solve_reference_mixture

    def record(counts, matrix, background, **kwargs):
        observed.append((counts.copy(), matrix.copy(), background.copy()))
        return original(counts, matrix, background, **kwargs)

    monkeypatch.setattr(bench, "solve_reference_mixture", record)
    result = score_replayed_fold(context, (_policy(),), omissions=((_KNOWN[0],),))
    assert len(result.results) == len(observed) == 2
    np.testing.assert_array_equal(observed[0][0], observed[1][0])
    np.testing.assert_array_equal(observed[0][2], observed[1][2])
    np.testing.assert_array_equal(observed[1][1], context.signatures[:, [1]])
    omitted = result.results[1]
    row = next(row for row in omitted.labels if row.modeled_label == _KNOWN[0])
    assert row.modeled is False
    assert row.mean_signed_error is row.mean_absolute_error is None
    assert omitted.offered_case_count == 1


def test_all_reference_withholding_retains_unsupported_cases_and_depth_precedence():
    context = _context((_case(), _case((0, 0, 0), (0, 0, 0))))
    result = score_replayed_fold(context, (_policy(),), omissions=(_KNOWN,)).results[1]
    assert result.offered_case_count == 2
    assert result.scored_case_count == 0
    assert _terminals(result)["no_reference_columns"] == 1
    assert _terminals(result)["zero_source_count_depth"] == 1
    assert result.mean_total_variation is result.mean_unknown_signed_error is None
    assert all(not row.modeled and row.mean_absolute_error is None for row in result.labels)


def test_known_signature_conditioning_rejection_keeps_zero_depth_precedence(monkeypatch):
    context = _context(
        (_case(), _case((0, 0, 0), (0, 0, 0))),
        signatures=np.column_stack((_BACKGROUND, _BACKGROUND)),
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("conditioning-rejected signatures must never reach the point solver")

    monkeypatch.setattr(bench, "solve_reference_mixture", forbidden)
    result = score_replayed_fold(context, (_policy(),)).results[0]
    assert _terminals(result)["signature_conditioning_rejected"] == 1
    assert _terminals(result)["zero_source_count_depth"] == 1
    assert result.scored_case_count == 0


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ValueError, "solver_rejected"),
        (TypeError, "solver_rejected"),
        (FloatingPointError, "solver_numerical_failure"),
        (GbmapNumericalError, "solver_numerical_failure"),
        (np.linalg.LinAlgError, "solver_numerical_failure"),
    ],
)
def test_solver_failure_categories_remain_explicit_without_echoing_errors(
    monkeypatch, error, reason
):
    def fail(*_args, **_kwargs):
        detail = "synthetic private numerical details"
        raise error(detail)

    monkeypatch.setattr(bench, "solve_reference_mixture", fail)
    result = score_replayed_fold(_context((_case(),)), (_policy(),)).results[0]
    assert _terminals(result)[reason] == 1
    assert result.scored_case_count == 0
    assert result.mean_total_variation is None
    assert "synthetic private numerical details" not in result.model_dump_json()


@pytest.mark.parametrize("invalid_trace", [False, True])
def test_solver_trace_and_convergence_gates_are_preserved(monkeypatch, invalid_trace):
    valid = solve_reference_mixture(
        (300, 300, 300),
        _SIGNATURES,
        _BACKGROUND,
        concentration=100.0,
        lambda_mass=0.0,
        lambda_shape=0.1,
    )
    changed = (
        replace(valid, trace=(), iterations=0) if invalid_trace else replace(valid, converged=False)
    )
    monkeypatch.setattr(bench, "solve_reference_mixture", lambda *args, **kwargs: changed)
    result = score_replayed_fold(_context((_case(),)), (_policy(),)).results[0]
    reason = "solver_trace_invalid" if invalid_trace else "solver_not_converged"
    assert _terminals(result)[reason] == 1
    assert result.mean_total_variation is None


def test_policy_and_scenario_input_permutations_do_not_change_any_output():
    context = _context((_case(),))
    policies = (_policy(initial_unknown_mass=0.2), _policy(initial_unknown_mass=0.8))
    omissions = ((_KNOWN[0],), (_KNOWN[1],))
    first = score_replayed_fold(context, policies, omissions=omissions)
    second = score_replayed_fold(context, policies[::-1], omissions=omissions[::-1])
    assert first == second
    assert len(first.results) == 6
    assert tuple(result.omitted_labels for result in first.results) == ((), *omissions) * 2


def test_cooperative_cancellation_propagates_without_becoming_a_failed_case(monkeypatch):
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        score_replayed_fold(_context((_case(),)), (_policy(),), cancellation=cancellation)

    def fail(*_args, **_kwargs):
        raise InferenceCancelledError

    monkeypatch.setattr(bench, "solve_reference_mixture", fail)
    with pytest.raises(InferenceCancelledError):
        score_replayed_fold(_context((_case(),)), (_policy(),))


@pytest.mark.parametrize("value", [True, 1, "1.0", math.inf, math.nan, np.float64(1)])
def test_policies_require_explicit_exact_finite_python_floats(value):
    with pytest.raises(ValueError):
        _policy(concentration=value)


@pytest.mark.parametrize(
    "changes",
    [
        {"concentration": 0.0},
        {"lambda_mass": -0.1},
        {"lambda_shape": -0.1},
        {"initial_unknown_mass": 0.0},
        {"initial_unknown_mass": 1.0},
    ],
)
def test_policy_domains_reject_undefined_optimization_settings(changes):
    with pytest.raises(ValueError):
        _policy(**changes)


def test_policy_and_omission_duplicates_are_not_silently_collapsed():
    context = _context((_case(),))
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(context, (_policy(), _policy()))
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(context, (_policy(),), omissions=((_KNOWN[0],),) * 2)
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(context, (_policy(),), omissions=((_UNKNOWN,),))
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(context, (_policy(),), omissions=((),))
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(context, ())
    with pytest.raises(MixtureBenchmarkError):
        score_replayed_fold(object(), (_policy(),))


def test_closed_json_roundtrip_preserves_unavailable_metrics_and_fixed_claim_limits():
    result = score_replayed_fold(_context((_case(),)), (_policy(),), omissions=(_KNOWN,))
    assert MixtureBenchmarkReceipt.model_validate_json(result.model_dump_json()) == result
    document = json.loads(result.model_dump_json())
    for claim in (
        "policy_selection_performed",
        "calibration_performed",
        "unbiased_performance_established",
    ):
        for value in (True, 0, 1):
            with pytest.raises(ValueError):
                MixtureBenchmarkReceipt.model_validate_json(json.dumps({**document, claim: value}))
    unsupported = document["results"][1]
    assert unsupported["mean_total_variation"] is None
    unsupported["mean_total_variation"] = 0.0
    with pytest.raises(ValueError):
        MixtureBenchmarkReceipt.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    "corruption", ["drop_label", "drop_scenario", "false_zero_error", "hide_failure"]
)
def test_saved_receipt_cannot_drop_denominators_or_invent_success(corruption):
    result = score_replayed_fold(_context((_case(),)), (_policy(),), omissions=(_KNOWN,))
    document = json.loads(result.model_dump_json())
    if corruption == "drop_label":
        document["results"][0]["labels"].pop()
    elif corruption == "drop_scenario":
        document["results"].pop()
    elif corruption == "false_zero_error":
        document["results"][0]["mean_total_variation"] = 0.0
    else:
        document["results"][1]["terminal_counts"][3]["count"] = 0
    with pytest.raises(ValueError):
        MixtureBenchmarkReceipt.model_validate_json(json.dumps(document))


def test_failed_signature_decomposition_is_counted_without_calling_the_solver(monkeypatch):
    def fail(*_args, **_kwargs):
        raise np.linalg.LinAlgError

    monkeypatch.setattr(bench.np.linalg, "svd", fail)
    result = score_replayed_fold(_context((_case(),)), (_policy(),)).results[0]
    assert _terminals(result)["signature_conditioning_rejected"] == 1
    assert result.scored_case_count == 0


def test_valid_solution_for_the_wrong_number_of_labels_cannot_become_a_score(monkeypatch):
    valid = solve_reference_mixture(
        (300, 300, 300),
        _SIGNATURES,
        _BACKGROUND,
        concentration=100.0,
        lambda_mass=0.0,
        lambda_shape=0.1,
    )
    wrong_axis = replace(valid, known_rna_weights=np.array([math.fsum(valid.known_rna_weights)]))
    monkeypatch.setattr(bench, "solve_reference_mixture", lambda *_args, **_kwargs: wrong_axis)
    result = score_replayed_fold(_context((_case(),)), (_policy(),)).results[0]
    assert _terminals(result)["solver_trace_invalid"] == 1
    assert result.scored_case_count == 0


@pytest.mark.parametrize("corruption", ["partial_error", "impossible_bias", "visibility"])
def test_saved_label_metrics_cannot_invent_observability_or_inconsistent_errors(corruption):
    result = score_replayed_fold(_context((_case(),)), (_policy(),))
    document = json.loads(result.model_dump_json())
    labels = document["results"][0]["labels"]
    if corruption == "partial_error":
        row = next(row for row in labels if row["modeled_label"] == _UNKNOWN)
        row["mean_signed_error"] = 0.0
    else:
        row = next(row for row in labels if row["modeled_label"] == _KNOWN[0])
        if corruption == "impossible_bias":
            row["mean_signed_error"] = 0.5
        else:
            # Preserve local totals and errors while contradicting the replayed
            # source visibility; the parent receipt must check the actual basis.
            row["offered_visibility"] = row["scored_visibility"] = {
                "source_zero": 1,
                "source_positive_selected_zero": 0,
                "selected_positive": 0,
            }
    with pytest.raises(ValueError):
        MixtureBenchmarkReceipt.model_validate_json(json.dumps(document))


def test_saved_terminal_partition_cannot_reclassify_a_positive_case_as_source_zero():
    result = score_replayed_fold(_context((_case(),)), (_policy(),))
    document = json.loads(result.model_dump_json())
    row = document["results"][0]
    row["scored_case_count"] = 0
    row["terminal_counts"][0]["count"] = 1
    row["mean_total_variation"] = None
    row["mean_unknown_signed_error"] = row["mean_unknown_absolute_error"] = None
    for label in row["labels"]:
        label["mean_signed_error"] = label["mean_absolute_error"] = None
        label["scored_visibility"] = {
            "source_zero": 0,
            "source_positive_selected_zero": 0,
            "selected_positive": 0,
        }
    with pytest.raises(ValueError):
        MixtureBenchmarkReceipt.model_validate_json(json.dumps(document))
