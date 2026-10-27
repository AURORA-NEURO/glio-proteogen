"""Synthetic two-cohort refit, paired-support and uncertainty scope oracles."""

from __future__ import annotations

import json
import pickle
from collections import Counter
from dataclasses import FrozenInstanceError, asdict, replace
from statistics import median
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission import transfer_sensitivity as method
from glio_proteogen.research.cptac_gbm_external_admission.resampling import (
    generate_two_cohort_draws,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)

REQUEST = "sha256:" + "b" * 64
PARENT_REQUEST = "sha256:" + "a" * 64
ORDER = ("training_median", "rna_only", "cnv_only", "full")
MODELS = (*ORDER, "selected_policy")


@pytest.fixture(scope="module")
def context():
    rng = np.random.default_rng(271828)
    cnv, rna = rng.normal(size=72), rng.normal(size=72)
    protein = 2 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=72)
    folds = transfer.deterministic_patient_folds(tuple(f"SYNTHETIC-{i:03}" for i in range(72)))
    source = method.SourceGeneInputs(cnv, rna, protein, folds)
    external_cnv, external_rna = rng.normal(size=56), rng.normal(size=56)
    external = method.ExternalGeneInputs(
        external_cnv,
        external_rna,
        2 * external_rna + 0.4 * external_cnv + rng.normal(scale=0.1, size=56),
    )
    fit = transfer.fit_source_gene(source.cnv, source.rna, source.protein, source.folds)
    parent = transfer.evaluate_external_gene(
        fit, external.cnv, external.rna, external.protein, request_digest=PARENT_REQUEST
    )
    assert fit.receipt.accepted and parent.accepted
    return SimpleNamespace(source=source, external=external, fit=fit, parent=parent)


def _arguments(context):
    return {
        "source_fit": context.fit,
        "source_inputs": context.source,
        "external_inputs": context.external,
        "parent_result": context.parent,
        "request_digest": REQUEST,
    }


@pytest.fixture(scope="module")
def actual_execution(context):
    """The one genuine128-source-refit synthetic run in this test module."""
    fits, bootstrap_calls, training_calls = [], [], []
    source = context.source
    source_index = {float(value): index for index, value in enumerate(source.cnv)}
    original_fit, original_bootstrap = transfer.fit_source_gene, transfer._bootstrap
    original_candidate = nested._fit_candidate

    def fit_spy(cnv, rna, protein, folds):
        indices = np.array([source_index[float(value)] for value in cnv])
        np.testing.assert_array_equal(folds, source.folds[indices])
        np.testing.assert_array_equal(rna, source.rna[indices])
        np.testing.assert_array_equal(protein, source.protein[indices])
        fits.append(len(indices))
        return original_fit(cnv, rna, protein, folds)

    def candidate_spy(candidate, cnv, rna, protein, *, outer_fold, inner_fold):  # noqa: PLR0913
        indices = np.array([source_index[float(value)] for value in cnv])
        if outer_fold >= 0:
            assert np.all(source.folds[indices] != outer_fold)
        if inner_fold is not None:
            assert np.all(source.folds[indices] != inner_fold)
        training_calls.append((outer_fold, inner_fold))
        return original_candidate(
            candidate, cnv, rna, protein, outer_fold=outer_fold, inner_fold=inner_fold
        )

    def bootstrap_spy(*args, **kwargs):
        bootstrap_calls.append(True)
        return original_bootstrap(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(transfer, "fit_source_gene", fit_spy)
        patch.setattr(nested, "_fit_candidate", candidate_spy)
        patch.setattr(transfer, "_bootstrap", bootstrap_spy)
        result = method.evaluate_two_cohort_sensitivity(**_arguments(context))
    return SimpleNamespace(
        result=result, fits=fits, bootstrap_calls=bootstrap_calls, training_calls=training_calls
    )


@pytest.fixture
def programmed(context, monkeypatch):
    """Program only source/scoring boundaries; public scheduling/accounting stays real."""
    draws = generate_two_cohort_draws(
        source_folds=context.source.folds, external_count=56, request_digest=REQUEST
    )
    source_lookup = {
        tuple(
            value[draw.source_indices].tobytes()
            for value in (context.source.cnv, context.source.rna, context.source.protein)
        ): draw.receipt.draw_ordinal
        for draw in draws
    }
    external_lookup = {
        tuple(
            value[draw.external_indices].tobytes()
            for value in (context.external.cnv, context.external.rna, context.external.protein)
        ): draw.receipt.draw_ordinal
        for draw in draws
    }
    state = SimpleNamespace(
        fail_source=set(),
        fail_joint=set(),
        fail_reference=set(),
        missing_joint_r2=set(),
        missing_reference_r2=set(),
        fit_calls=[],
        score_calls=[],
        parent_calls=[],
        generated=[],
    )
    original_source_bytes = tuple(
        value.tobytes()
        for value in (context.source.cnv, context.source.rna, context.source.protein)
    )

    def fit(cnv, rna, protein, folds):
        key = tuple(value.tobytes() for value in (cnv, rna, protein))
        if key == original_source_bytes:
            state.fit_calls.append("point")
            np.testing.assert_array_equal(folds, context.source.folds)
            return context.fit
        ordinal = source_lookup[key]
        state.fit_calls.append(ordinal)
        np.testing.assert_array_equal(folds, draws[ordinal].source_folds)
        np.testing.assert_array_equal(folds, context.source.folds[draws[ordinal].source_indices])
        if ordinal in state.fail_source:
            return replace(
                context.fit,
                receipt=replace(
                    context.fit.receipt, accepted=False, failure_reason="synthetic source cap"
                ),
                _predictors=(),
            )
        return replace(
            context.fit, receipt=replace(context.fit.receipt, selected_candidate=ORDER[ordinal % 4])
        )

    def parent_replay(source, cnv, rna, protein, *, request_digest):
        assert source is context.fit and request_digest == PARENT_REQUEST
        for actual, wanted in zip(
            (cnv, rna, protein),
            (context.external.cnv, context.external.rna, context.external.protein),
            strict=True,
        ):
            np.testing.assert_array_equal(actual, wanted)
        state.parent_calls.append(True)
        return context.parent

    def scores(source, cnv, rna, protein):
        ordinal = external_lookup[tuple(value.tobytes() for value in (cnv, rna, protein))]
        frozen = source is context.fit
        state.score_calls.append((ordinal, frozen))
        if ordinal in (state.fail_reference if frozen else state.fail_joint):
            return None
        t = (ordinal - 63.5) / 64
        full = 4 + t if frozen else 4 - t
        losses = (6.0, 3.0, 4.0, full)
        selected = losses[ORDER.index(source.receipt.selected_candidate)]
        missing = ordinal in (state.missing_reference_r2 if frozen else state.missing_joint_r2)
        return tuple(
            transfer.TransferMetrics(
                candidate,
                56,
                loss,
                loss + 1,
                None if missing else (index + 1) / 10 + ordinal / 1000,
            )
            for index, (candidate, loss) in enumerate(zip(MODELS, (*losses, selected), strict=True))
        )

    def schedule(**kwargs):
        assert kwargs["request_digest"] == REQUEST and kwargs["external_count"] == 56
        np.testing.assert_array_equal(kwargs["source_folds"], context.source.folds)
        state.generated.append(True)
        return draws

    monkeypatch.setattr(transfer, "fit_source_gene", fit)
    monkeypatch.setattr(transfer, "evaluate_external_gene", parent_replay)
    monkeypatch.setattr(method, "_scores", scores)
    monkeypatch.setattr(method, "generate_two_cohort_draws", schedule)
    return SimpleNamespace(
        context=context,
        state=state,
        draws=draws,
        run=lambda: method.evaluate_two_cohort_sensitivity(**_arguments(context)),
    )


def test_actual128_refit_run_preserves_group_folds_and_replays_parent_only_once(
    context, actual_execution
):
    result = actual_execution.result
    assert result.accepted, result.failure_counts
    assert result.draws_attempted == 128 and result.draws_successful >= 103
    assert actual_execution.fits == [72] * 129
    assert len(actual_execution.bootstrap_calls) == 1
    assert actual_execution.training_calls
    assert result.parent_result == context.parent
    assert result.original_point_estimates_changed is False
    assert result.uncertainty.source_fitting_repeated is True
    assert result.uncertainty.source_selection_repeated is True
    assert result.uncertainty.fixed_original_folds is True
    assert (
        result.calibrated_coverage_established
        is result.aligned_external_validation
        is result.clinical_validation
        is result.default_promotion
        is False
    )


def test_paired_ranges_have_independent_rank_and_negative_covariance_oracles(
    programmed,
):
    result = programmed.run()
    assert result.accepted and result.draws_successful == 128
    ranges = result.uncertainty
    t = [(index - 63.5) / 64 for index in range(128)]
    assert (ranges.primary_joint.lower, ranges.primary_joint.upper) == pytest.approx(
        np.quantile([-value for value in t], [0.05, 0.95], method="inverted_cdf")
    )
    assert (
        ranges.primary_frozen_reference.lower,
        ranges.primary_frozen_reference.upper,
    ) == pytest.approx(np.quantile(t, [0.05, 0.95], method="inverted_cdf"))
    assert (
        ranges.primary_refit_minus_frozen.lower,
        ranges.primary_refit_minus_frozen.upper,
    ) == pytest.approx(
        np.quantile([-2 * value for value in t], [0.05, 0.95], method="inverted_cdf")
    )
    variance = sum((value - sum(t) / len(t)) ** 2 for value in t) / 127
    accounting = ranges.primary_variance_identity
    assert accounting.joint_variance == pytest.approx(variance)
    assert accounting.frozen_reference_variance == pytest.approx(variance)
    assert accounting.source_perturbation_variance == pytest.approx(4 * variance)
    assert accounting.twice_covariance == pytest.approx(-4 * variance)
    assert accounting.reconstructed_variance == pytest.approx(variance)
    assert abs(accounting.reconstruction_error) < 1e-12
    assert accounting.causal_variance_partition is False
    assert accounting.degrees_of_freedom == 1
    assert ranges.primary_refit_minus_frozen.point_estimate == 0
    assert (
        ranges.primary_joint.point_estimate == programmed.context.parent.primary_full_minus_cnv_mae
    )
    assert ranges.primary_frozen_reference.point_estimate == ranges.primary_joint.point_estimate
    assert programmed.state.fit_calls == ["point", *range(128)]
    assert len(programmed.state.parent_calls) == len(programmed.state.generated) == 1
    assert sum(frozen for _, frozen in programmed.state.score_calls) == 128


@pytest.mark.parametrize(("failed", "accepted"), [(25, True), (26, False)])
@pytest.mark.parametrize("stage", ["source", "joint", "reference"])
def test_103_gate_no_redraw_and_reference_failure_conditioning(programmed, failed, accepted, stage):
    getattr(programmed.state, "fail_" + stage).update(range(failed))
    result = programmed.run()
    assert result.accepted is accepted
    assert result.draws_attempted == 128 and result.draws_successful == 128 - failed
    assert programmed.state.fit_calls == ["point", *range(128)]
    assert sum(frozen for _, frozen in programmed.state.score_calls) == 128
    assert sum(item.replicates for item in result.failure_counts) == failed
    assert result.frozen_reference_available_draws == (
        128 - failed if stage == "reference" else 128
    )
    assert result.reference_available_but_unmatched_draws == (0 if stage == "reference" else failed)
    assert result.unavailable_source_selections == (failed if stage == "source" else 0)
    assert (
        sum(item.accepted_source_refits for item in result.selection_frequencies)
        == result.accepted_source_refits
        == (128 - failed if stage == "source" else 128)
    )
    assert (
        sum(item.successful_joint_comparisons for item in result.selection_frequencies)
        == 128 - failed
    )
    if accepted:
        assert result.uncertainty.matched_joint_successful_draws == 103
        assert (
            result.uncertainty.primary_joint.replicates
            == result.uncertainty.primary_frozen_reference.replicates
            == 103
        )
        expected_reference = [(index - 63.5) / 64 for index in range(failed, 128)]
        assert (
            result.uncertainty.primary_frozen_reference.lower,
            result.uncertainty.primary_frozen_reference.upper,
        ) == pytest.approx(np.quantile(expected_reference, [0.05, 0.95], method="inverted_cdf"))
    else:
        assert result.uncertainty is None and "below103of128" in result.failure_reason
        assert result.parent_result == programmed.context.parent


def test_failure_and_selection_denominators_conserve_all128_attempts(programmed):
    programmed.state.fail_source.update(range(10))
    programmed.state.fail_joint.update(range(10, 20))
    programmed.state.fail_reference.update(range(20, 25))
    result = programmed.run()
    assert result.accepted and result.draws_successful == 103
    assert result.accepted_source_refits == 118
    assert result.unavailable_source_selections == 10
    assert result.frozen_reference_available_draws == 123
    assert result.reference_available_but_unmatched_draws == 20
    stages = Counter()
    for failure in result.failure_counts:
        stages[failure.stage] += failure.replicates
    assert stages == {"source_refit": 10, "external_comparison": 15}
    for index, item in enumerate(result.selection_frequencies):
        assert item.candidate == ORDER[index]
        assert item.accepted_source_refits == sum(b % 4 == index for b in range(10, 128))
        assert item.successful_joint_comparisons == sum(b % 4 == index for b in range(25, 128))
    assert (
        sum(item.accepted_source_refits for item in result.selection_frequencies)
        + stages["source_refit"]
        == 128
    )
    assert result.accepted_source_refits + result.unavailable_source_selections == 128


@pytest.mark.parametrize(
    ("missing_a", "missing_b", "paired"), [(13, 13, 102), (12, 13, 103), (0, 0, 128)]
)
def test_r2_both_sides_require_same_paired_finite_subset(programmed, missing_a, missing_b, paired):
    programmed.state.missing_joint_r2.update(range(missing_a))
    programmed.state.missing_reference_r2.update(range(missing_a, missing_a + missing_b))
    result = programmed.run()
    assert result.accepted and result.draws_successful == 128
    for a, b in zip(
        result.uncertainty.joint_model_intervals,
        result.uncertainty.frozen_reference_intervals,
        strict=True,
    ):
        assert a.mae.replicates == b.mae.replicates == 128
        if paired < 103:
            assert a.r2_vs_source_training_median is b.r2_vs_source_training_median is None
        else:
            assert (
                a.r2_vs_source_training_median.replicates
                == b.r2_vs_source_training_median.replicates
                == paired
            )
            expected = [
                (MODELS.index(a.candidate) + 1) / 10 + index / 1000
                for index in range(missing_a + missing_b, 128)
            ]
            wanted = np.quantile(expected, [0.05, 0.95], method="inverted_cdf")
            assert (
                a.r2_vs_source_training_median.lower,
                a.r2_vs_source_training_median.upper,
            ) == pytest.approx(wanted)
            assert (
                b.r2_vs_source_training_median.lower,
                b.r2_vs_source_training_median.upper,
            ) == pytest.approx(wanted)


@pytest.mark.parametrize("kind", ["negative", "zero", "positive"])
def test_sample_variance_identity_handles_covariance_without_clipping(kind):
    reference = [-1.0, -1.0, 1.0, 1.0] * 32
    delta = (
        [-value for value in reference]
        if kind == "negative"
        else ([-1.0, 1.0, -1.0, 1.0] * 32 if kind == "zero" else reference)
    )
    joint = [a + b for a, b in zip(reference, delta, strict=True)]
    result = method._variance_identity(joint, reference)
    mean_b, mean_d = sum(reference) / 128, sum(delta) / 128
    covariance = (
        sum((b - mean_b) * (d - mean_d) for b, d in zip(reference, delta, strict=True)) / 127
    )
    assert result.twice_covariance == pytest.approx(2 * covariance)
    assert result.joint_variance == pytest.approx(
        result.frozen_reference_variance
        + result.source_perturbation_variance
        + result.twice_covariance
    )
    assert result.reconstruction_error == pytest.approx(0, abs=1e-12)
    assert result.reconstructed_variance == pytest.approx(result.joint_variance)
    assert (result.twice_covariance < 0) is (kind == "negative")
    assert result.causal_variance_partition is False


@pytest.mark.parametrize(
    "values", [[], list(range(102)), [float("nan")] * 128, [float("inf")] * 128]
)
def test_percentile_ranges_refuse_insufficient_or_nonfinite_support(values):
    with pytest.raises(ValueError):
        method._range(values, 0.0)


def test_percentile_nearest_ranks_are_not_interpolated():
    result = method._range(list(range(128)), -999.0)
    assert result.lower == 6 and result.upper == 121 and result.point_estimate == -999
    assert result.nominal_level == 0.9 and result.calibrated_coverage_established is False
    short = method._range(list(range(103)), 0.0)
    assert short.lower == 5 and short.upper == 97
    with pytest.raises(ValueError):
        method._range(list(range(128)), float("nan"))
    with pytest.raises(ValueError):
        method._variance_identity([0.0] * 102, [0.0] * 102)
    with pytest.raises(ValueError):
        method._variance_identity([0.0] * 128, [0.0] * 127)
    with pytest.raises(ValueError):
        method._variance_identity([float("nan")] * 128, [0.0] * 128)


def _ess(values):
    counts = Counter(int(value) for value in values)
    return len(values) ** 2 / sum(count**2 for count in counts.values()) if counts else 0.0


def _assert_distribution(summary, values):
    assert summary.draws == len(values)
    assert summary.minimum == pytest.approx(min(values))
    assert summary.median == pytest.approx(median(values))
    assert summary.maximum == pytest.approx(max(values))


def test_diagnostics_have_independent_frequency_unique_fold_and_training_ess_oracles(programmed):
    result = programmed.run()
    diagnostic = result.source_sampling_diagnostics
    draws, source = programmed.draws, programmed.context.source
    _assert_distribution(diagnostic.source_joint_complete_mass, [72] * 128)
    _assert_distribution(diagnostic.external_joint_complete_mass, [56] * 128)
    _assert_distribution(
        diagnostic.source_joint_complete_unique, [len(set(draw.source_indices)) for draw in draws]
    )
    _assert_distribution(
        diagnostic.external_joint_complete_unique,
        [len(set(draw.external_indices)) for draw in draws],
    )
    _assert_distribution(
        diagnostic.source_joint_complete_effective_count,
        [_ess(draw.source_indices) for draw in draws],
    )
    _assert_distribution(
        diagnostic.external_joint_complete_effective_count,
        [_ess(draw.external_indices) for draw in draws],
    )
    outer_unique, inner_unique, outer_ess, inner_ess = [], [], [], []
    strict60 = strict_all = 0
    for draw in draws:
        unique = {int(index) for index in draw.source_indices}
        unique_counts = [sum(source.folds[index] == fold for index in unique) for fold in range(5)]
        train_unique = [len(unique) - count for count in unique_counts]
        inner = [
            len(unique) - unique_counts[a] - unique_counts[b]
            for a in range(5)
            for b in range(5)
            if a != b
        ]
        outer_unique.append(min(train_unique))
        inner_unique.append(min(inner))
        outer_ess.append(
            min(
                _ess([index for index in draw.source_indices if source.folds[index] != fold])
                for fold in range(5)
            )
        )
        inner_ess.append(
            min(
                _ess([index for index in draw.source_indices if source.folds[index] not in (a, b)])
                for a in range(5)
                for b in range(5)
                if a != b
            )
        )
        strict60 += len(unique) >= 60
        strict_all += (
            len(unique) >= 60
            and min(train_unique) >= 48
            and min(unique_counts) >= 3
            and min(inner) >= 32
        )
    for summary, values in (
        (diagnostic.source_outer_training_unique_minimum, outer_unique),
        (diagnostic.source_inner_training_unique_minimum, inner_unique),
        (diagnostic.source_outer_training_effective_minimum, outer_ess),
        (diagnostic.source_inner_training_effective_minimum, inner_ess),
    ):
        _assert_distribution(summary, values)
    for fold in range(5):
        subsets = [
            [index for index in draw.source_indices if source.folds[index] == fold]
            for draw in draws
        ]
        _assert_distribution(
            diagnostic.source_fold_joint_unique[fold], [len(set(values)) for values in subsets]
        )
        _assert_distribution(
            diagnostic.source_fold_joint_effective[fold], [_ess(values) for values in subsets]
        )
    assert diagnostic.draws_with_source_joint_unique_at_least60 == strict60
    assert diagnostic.draws_with_all_distinct_source_legacy_counts == strict_all
    assert (
        diagnostic.unique_diagnostics_are_gates
        is diagnostic.bootstrap_mass_is_independent_patient_count
        is False
    )
    assert diagnostic.source_joint_complete_unique.maximum < 72
    assert result.accepted


def test_missing_complete_support_and_zeros_stay_distinct_in_descriptive_diagnostics(context):
    protein = context.source.protein.copy()
    protein[:3] = np.nan
    cnv = context.source.cnv.copy()
    cnv[3] = 0
    source = method.SourceGeneInputs(cnv, context.source.rna, protein, context.source.folds)
    external_protein = context.external.protein.copy()
    external_protein[:2] = np.nan
    external = method.ExternalGeneInputs(
        context.external.cnv, context.external.rna, external_protein
    )
    draws = generate_two_cohort_draws(
        source_folds=source.folds, external_count=56, request_digest=REQUEST
    )
    result = method._diagnostics(source, external, draws)
    _assert_distribution(
        result.source_joint_complete_mass,
        [sum(index >= 3 for index in draw.source_indices) for draw in draws],
    )
    _assert_distribution(
        result.external_joint_complete_mass,
        [sum(index >= 2 for index in draw.external_indices) for draw in draws],
    )
    assert result.source_joint_complete_mass.minimum < 72
    assert source.cnv[3] == 0 and np.isfinite(source.protein[3])
    assert method._effective(np.array([], dtype=np.int64)) == 0
    assert method._effective(np.array([0, 0, 0, 1], dtype=np.int64)) == 1.6


def _known_predictors(context):
    predictors = (
        transfer._FrozenPredictor("training_median", 2.0, (), (), (), 0.0, 1.0),
        transfer._FrozenPredictor("rna_only", None, (0.0,), (1.0,), (0.0, 1.0), 0.0, 1.0),
        transfer._FrozenPredictor("cnv_only", None, (0.0,), (1.0,), (0.0, 0.5), 0.0, 1.0),
        transfer._FrozenPredictor("full", None, (0.0, 0.0), (1.0, 1.0), (1.0, 2.0, -0.5), 0.0, 1.0),
    )
    return replace(
        context.fit,
        receipt=replace(context.fit.receipt, selected_candidate="full"),
        _predictors=predictors,
    )


def test_common_support_losses_have_independent_scalar_oracles_with_finite_zero(context):
    source = _known_predictors(context)
    cnv = np.arange(56, dtype=np.float64) - 28
    rna = np.arange(56, dtype=np.float64) / 4 - 7
    protein = 1 + 2 * rna - 0.5 * cnv + np.sin(np.arange(56))
    cnv[0], rna[1], protein[2] = np.nan, np.nan, np.nan
    rows = [i for i in range(56) if i not in (0, 1, 2)]
    expected = (
        [2.0 for _i in rows],
        [float(rna[i]) for i in rows],
        [0.5 * float(cnv[i]) for i in rows],
        [1 + 2 * float(rna[i]) - 0.5 * float(cnv[i]) for i in rows],
    )
    metrics = method._scores(source, cnv, rna, protein)
    assert metrics is not None and metrics[4].mae == metrics[3].mae
    assert cnv[28] == rna[28] == 0 and 28 in rows
    null_sse = sum((float(protein[i]) - 2) ** 2 for i in rows)
    for metric, predictions in zip(metrics, (*expected, expected[3]), strict=True):
        errors = [
            float(protein[i]) - prediction for i, prediction in zip(rows, predictions, strict=True)
        ]
        sse = sum(error**2 for error in errors)
        assert metric.observed_count == len(rows) == 53
        assert metric.mae == pytest.approx(sum(abs(error) for error in errors) / len(rows))
        assert metric.rmse == pytest.approx((sse / len(rows)) ** 0.5)
        assert metric.r2_vs_source_training_median == pytest.approx(1 - sse / null_sse)


@pytest.mark.parametrize("mode", ["support", "order", "median", "prediction", "loss"])
def test_scoring_refuses_unavailable_support_and_invalid_predictor_contracts(
    context, monkeypatch, mode
):
    source = _known_predictors(context)
    cnv, rna, protein = (np.ones(56, dtype=np.float64) for _ in range(3))
    if mode == "support":
        protein[:9] = np.nan
    elif mode == "order":
        source = replace(source, _predictors=tuple(reversed(source._predictors)))
    elif mode == "median":
        source = replace(
            source,
            _predictors=(
                replace(
                    source._predictors[0], median=None, center=(0.0,), scale=(1.0,), beta=(0.0, 1.0)
                ),
                *source._predictors[1:],
            ),
        )
    elif mode == "prediction":
        source = replace(
            source,
            _predictors=(
                replace(source._predictors[0], median=float("inf")),
                *source._predictors[1:],
            ),
        )
    else:
        original = transfer._metrics

        def unavailable(*args):
            return replace(original(*args), mae=float("inf"))

        monkeypatch.setattr(transfer, "_metrics", unavailable)
    if mode in ("order", "median"):
        with pytest.raises(ValueError):
            method._scores(source, cnv, rna, protein)
    else:
        assert method._scores(source, cnv, rna, protein) is None


def test_panel_includes_new_uncertainty_failures_in_all_originally_eligible_intersection(
    programmed, monkeypatch
):
    result = programmed.run()
    first = np.ones(128, dtype=bool)
    first[:25] = False
    second = np.ones(128, dtype=bool)
    second[-26:] = False
    unsupported = replace(result.parent_result, accepted=False)
    executions = iter(
        (
            method._GeneExecution(replace(result, draws_successful=103), first),
            method._GeneExecution(
                replace(result, accepted=False, draws_successful=102, uncertainty=None), second
            ),
            method._GeneExecution(
                replace(
                    result,
                    accepted=False,
                    parent_result=unsupported,
                    draws_successful=0,
                    uncertainty=None,
                ),
                np.zeros(128, dtype=bool),
            ),
        )
    )
    monkeypatch.setattr(method, "_run_gene", lambda **_kwargs: next(executions))
    context = programmed.context
    panel = method.evaluate_panel_sensitivity(
        source_fits=(context.fit,) * 3,
        source_inputs=(context.source,) * 3,
        external_inputs=(context.external,) * 3,
        parent_results=(context.parent, context.parent, unsupported),
        request_digest=REQUEST,
    )
    assert panel.point_eligible_genes == 2
    assert panel.jointly_successful_draws_all_eligible == 77
    assert panel.gene_results[1].accepted is False
    assert panel.cross_gene_inference_established is False


def test_panel_reuses_the_identical_cohort_schedule_for_all_genes(programmed):
    context = programmed.context
    result = method.evaluate_panel_sensitivity(
        source_fits=(context.fit,) * 2,
        source_inputs=(context.source,) * 2,
        external_inputs=(context.external,) * 2,
        parent_results=(context.parent,) * 2,
        request_digest=REQUEST,
    )
    assert result.point_eligible_genes == 2 and result.jointly_successful_draws_all_eligible == 128
    assert result.gene_results[0] == result.gene_results[1]
    assert programmed.state.fit_calls == ["point", *range(128)] * 2
    assert len(programmed.state.generated) == 2


def test_original_point_abstention_never_attempts_bootstrap_rescue(context, monkeypatch):
    external = method.ExternalGeneInputs(
        context.external.cnv, context.external.rna, np.full(56, np.nan)
    )
    parent = transfer.evaluate_external_gene(
        context.fit, external.cnv, external.rna, external.protein, request_digest=PARENT_REQUEST
    )
    assert not parent.accepted

    def forbidden(**_kwargs):
        pytest.fail("point abstention reached resampling")

    monkeypatch.setattr(method, "generate_two_cohort_draws", forbidden)
    result = method.evaluate_two_cohort_sensitivity(
        source_fit=context.fit,
        source_inputs=context.source,
        external_inputs=external,
        parent_result=parent,
        request_digest=REQUEST,
    )
    assert not result.accepted and result.draws_attempted == result.draws_successful == 0
    assert (
        result.parent_result == parent
        and result.uncertainty is result.source_sampling_diagnostics is None
    )
    assert result.failure_counts == result.selection_frequencies == ()
    assert "cannot rescue eligibility" in result.failure_reason


def test_source_and_external_mismatch_fail_before_any_new_schedule(context, monkeypatch):
    def forbidden(**_kwargs):
        pytest.fail("mismatched original inputs reached resampling")

    monkeypatch.setattr(method, "generate_two_cohort_draws", forbidden)
    altered = context.source.protein.copy()
    altered[0] += 1
    source = method.SourceGeneInputs(
        context.source.cnv, context.source.rna, altered, context.source.folds
    )
    with pytest.raises(ValueError, match="source inputs"):
        method.evaluate_two_cohort_sensitivity(**{**_arguments(context), "source_inputs": source})
    altered = context.external.protein.copy()
    altered[0] += 1
    external = method.ExternalGeneInputs(context.external.cnv, context.external.rna, altered)
    with pytest.raises(ValueError, match="external inputs"):
        method.evaluate_two_cohort_sensitivity(
            **{**_arguments(context), "external_inputs": external}
        )


@pytest.mark.parametrize(
    "mutation", ["source_receipt", "profile", "point_metric", "interval", "validation_flag"]
)
def test_whole_parent_result_and_source_receipt_are_replayed_not_only_point_counts(
    context, monkeypatch, mutation
):
    parent = context.parent
    if mutation == "source_receipt":
        parent = replace(parent, source=replace(parent.source, complete_count=71))
    elif mutation == "profile":
        parent = replace(parent, profile_id="another-profile/1.0.0")
    elif mutation == "point_metric":
        parent = replace(
            parent,
            point_metrics=(replace(parent.point_metrics[0], mae=999.0), *parent.point_metrics[1:]),
        )
    elif mutation == "interval":
        parent = replace(
            parent, uncertainty=replace(parent.uncertainty, seed=parent.uncertainty.seed + 1)
        )
    else:
        parent = replace(parent, aligned_external_validation=True)

    def forbidden(**_kwargs):
        pytest.fail("counterfeit parent reached new resampling")

    monkeypatch.setattr(method, "generate_two_cohort_draws", forbidden)
    with pytest.raises(ValueError):
        method.evaluate_two_cohort_sensitivity(**{**_arguments(context), "parent_result": parent})


@pytest.mark.parametrize(
    "field", ["source_fit", "source_inputs", "external_inputs", "parent_result"]
)
def test_public_single_gene_requires_validated_transient_types(context, field):
    with pytest.raises(TypeError):
        method.evaluate_two_cohort_sensitivity(**{**_arguments(context), field: object()})


@pytest.mark.parametrize("bad", [None, 7, "", "a" * 64, "sha256:" + "A" * 64])
def test_whole_request_digest_is_strict_and_canonical(context, bad):
    with pytest.raises(ValueError):
        method.evaluate_two_cohort_sensitivity(**{**_arguments(context), "request_digest": bad})


@pytest.mark.parametrize(
    "mode",
    [
        "list",
        "integer",
        "two_dimensions",
        "infinite",
        "too_large",
        "misaligned",
        "fold_dtype",
        "fold_missing",
    ],
)
def test_source_input_contract_rejects_bad_array_types_and_bounds(context, mode):
    values = [
        context.source.cnv.copy(),
        context.source.rna.copy(),
        context.source.protein.copy(),
        context.source.folds.copy(),
    ]
    if mode == "list":
        values[0] = values[0].tolist()
    elif mode == "integer":
        values[0] = values[0].astype(int)
    elif mode == "two_dimensions":
        values[0] = values[0][:, None]
    elif mode == "infinite":
        values[0][0] = np.inf
    elif mode == "too_large":
        values[0][0] = 1e12 + 1
    elif mode == "misaligned":
        values[0] = values[0][:-1]
    elif mode == "fold_dtype":
        values[3] = values[3].astype(np.int64)
    else:
        values[3][:] = 0
    with pytest.raises((TypeError, ValueError)):
        method.SourceGeneInputs(*values)


@pytest.mark.parametrize(
    "mode", ["list", "integer", "two_dimensions", "infinite", "too_large", "empty", "misaligned"]
)
def test_external_input_contract_retains_strict_array_semantics(context, mode):
    values = [
        context.external.cnv.copy(),
        context.external.rna.copy(),
        context.external.protein.copy(),
    ]
    if mode == "list":
        values[0] = values[0].tolist()
    elif mode == "integer":
        values[0] = values[0].astype(int)
    elif mode == "two_dimensions":
        values[0] = values[0][:, None]
    elif mode == "infinite":
        values[0][0] = np.inf
    elif mode == "too_large":
        values[0][0] = 1e12 + 1
    elif mode == "empty":
        values[0] = np.array([], dtype=float)
    else:
        values[0] = values[0][:-1]
    with pytest.raises((TypeError, ValueError)):
        method.ExternalGeneInputs(*values)


@pytest.mark.parametrize(
    "field", ["source_fits", "source_inputs", "external_inputs", "parent_results"]
)
def test_panel_member_types_fail_safely_before_attribute_access(context, field):
    arguments = {
        "source_fits": (context.fit,),
        "source_inputs": (context.source,),
        "external_inputs": (context.external,),
        "parent_results": (context.parent,),
        "request_digest": REQUEST,
    }
    arguments[field] = (object(),)
    with pytest.raises(TypeError):
        method.evaluate_panel_sensitivity(**arguments)


@pytest.mark.parametrize(
    "mode",
    ["not_tuple", "empty", "unequal", "too_many", "different_folds", "different_external_count"],
)
def test_panel_inventory_and_shared_patient_axis_are_required(context, mode):
    arguments = {
        "source_fits": (context.fit,) * 2,
        "source_inputs": (context.source,) * 2,
        "external_inputs": (context.external,) * 2,
        "parent_results": (context.parent,) * 2,
        "request_digest": REQUEST,
    }
    if mode == "not_tuple":
        arguments["source_fits"] = list(arguments["source_fits"])
    elif mode == "empty":
        arguments.update(source_fits=(), source_inputs=(), external_inputs=(), parent_results=())
    elif mode == "unequal":
        arguments["source_inputs"] = (context.source,)
    elif mode == "too_many":
        arguments.update(
            source_fits=(context.fit,) * 33,
            source_inputs=(context.source,) * 33,
            external_inputs=(context.external,) * 33,
            parent_results=(context.parent,) * 33,
        )
    elif mode == "different_folds":
        arguments["source_inputs"] = (
            context.source,
            method.SourceGeneInputs(
                context.source.cnv,
                context.source.rna,
                context.source.protein,
                np.roll(context.source.folds, 1),
            ),
        )
    else:
        arguments["external_inputs"] = (
            context.external,
            method.ExternalGeneInputs(
                context.external.cnv[:-1], context.external.rna[:-1], context.external.protein[:-1]
            ),
        )
    with pytest.raises(ValueError):
        method.evaluate_panel_sensitivity(**arguments)


def test_private_inputs_and_masks_cannot_be_mutated_or_pickled_and_public_result_has_no_arrays(
    programmed,
):
    context = programmed.context
    for private in (context.source, context.external):
        assert "array" not in repr(private)
        with pytest.raises(TypeError):
            pickle.dumps(private)
        with pytest.raises(TypeError):
            private.__getstate__()
        with pytest.raises(FrozenInstanceError):
            private.cnv = np.zeros(72)
        for value in (private.cnv, private.rna, private.protein):
            assert not value.flags.writeable
            with pytest.raises(ValueError):
                value.setflags(write=True)
    execution = method._run_gene(**_arguments(context))
    with pytest.raises(TypeError):
        pickle.dumps(execution)
    with pytest.raises(TypeError):
        execution.__getstate__()
    assert ", successful=" not in repr(execution)
    assert not execution.successful.flags.writeable
    with pytest.raises(ValueError):
        execution.successful.setflags(write=True)
    result = execution.result
    encoded = json.dumps(asdict(result), allow_nan=False)
    assert "SYNTHETIC-" not in encoded
    stack = [asdict(result)]
    while stack:
        item = stack.pop()
        assert not isinstance(item, np.ndarray)
        if isinstance(item, dict):
            assert not {
                "source_indices",
                "external_indices",
                "successful",
                "cnv",
                "rna",
                "protein",
                "beta",
                "predictions",
                "residuals",
            }.intersection(item)
            stack.extend(item.values())
        elif isinstance(item, (tuple, list)):
            assert len(item) not in (56, 72, 128)
            stack.extend(item)
