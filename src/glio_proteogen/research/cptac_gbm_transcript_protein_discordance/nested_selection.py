"""Separate, nested held-out comparator selection over exact local gene inputs.

Selection sees only outer-training observations. The independent inner32 policy
does not alter the legacy outer48/3/4/60 or 103-of-128 bootstrap gates. All main
comparisons use identical outer-test support, and no biological label is emitted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from importlib.resources import files
from math import isfinite, sqrt
from typing import TYPE_CHECKING, Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest

from . import model as legacy
from .convergence import fit_huber_with_budget
from .profile import algorithm_profile

if TYPE_CHECKING:
    from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit

PROFILE_ID: Final = "cptac-gbm-nested-comparator-selection/1.0.0"
CANDIDATE_ORDER: Final = ("training_median", "rna_only", "cnv_only", "full")
ITERATION_BUDGET: Final = 240
INNER_MIN_TRAIN: Final = 32
INNER_MIN_TEST: Final = 3
BOOTSTRAP_REPLICATES: Final = 128
BOOTSTRAP_REQUIRED: Final = 103
MAX_ABSOLUTE_INPUT: Final = 1_000_000_000_000.0
FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class CandidateFit:
    candidate: str
    median: float | None
    model: RobustFit | None
    failure_reason: str | None

    @property
    def available(self) -> bool:
        return self.failure_reason is None and (self.median is not None or self.model is not None)

    def predict(self, cnv: FloatArray, rna: FloatArray) -> FloatArray:
        if not self.available:
            raise ValueError("an unavailable candidate cannot predict")
        if self.median is not None:
            return np.full(len(cnv), self.median, dtype=np.float64)
        if self.model is None:  # pragma: no cover - available enforces a predictor.
            raise AssertionError("available candidate lost its predictor")
        if self.candidate == "full":
            design = np.column_stack((rna, cnv))
        elif self.candidate == "rna_only":
            design = rna[:, None]
        else:
            design = cnv[:, None]
        return self.model.predict(design)


@dataclass(frozen=True, slots=True)
class CandidateSelectionEvidence:
    candidate: str
    eligible: bool
    inner_oof_count: int
    inner_mae: float | None
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InnerSelection:
    selected_candidate: str
    selection_basis: str
    fallback_reason: str | None
    candidates: tuple[CandidateSelectionEvidence, ...]


@dataclass(frozen=True, slots=True)
class OuterFitEvidence:
    candidate: str
    available: bool
    iterations: int | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class OuterSelectionTrace:
    fold: int
    training_complete: int
    held_out_complete: int
    selected_candidate: str
    selection_basis: str
    fallback_reason: str | None
    candidates: tuple[CandidateSelectionEvidence, ...]
    outer_fits: tuple[OuterFitEvidence, ...]
    selected_prediction_available: bool
    comparison_accepted: bool
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class ReconstructionMetrics:
    candidate: str
    observed_count: int
    mae: float
    rmse: float
    r2_vs_fold_train_median: float


@dataclass(frozen=True, slots=True)
class PairedMetricDelta:
    candidate: str
    mae_difference: float
    r2_difference: float


@dataclass(frozen=True, slots=True)
class SelectionCount:
    candidate: str
    fold_decisions: int
    comparison_observations: int


@dataclass(frozen=True, slots=True)
class NestedPointSummary:
    common_oof_count: int
    valid_outer_folds: int
    selected: ReconstructionMetrics
    fixed: tuple[ReconstructionMetrics, ...]
    deltas: tuple[PairedMetricDelta, ...]
    selection_counts: tuple[SelectionCount, ...]
    selection_decision_denominator: int


@dataclass(frozen=True, slots=True)
class NestedPointFit:
    complete_count: int
    common_oof_count: int
    selected_oof_count: int
    accepted: bool
    fold_trace: tuple[OuterSelectionTrace, ...]
    summary: NestedPointSummary | None
    observed: FloatArray = field(repr=False)
    selected_predictions: FloatArray = field(repr=False)
    fixed_predictions: tuple[FloatArray, ...] = field(repr=False)
    comparison_mask: npt.NDArray[np.bool_] = field(repr=False)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient nested-selection arrays cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient nested-selection arrays cannot be serialized")


@dataclass(frozen=True, slots=True)
class PairedDeltaInterval:
    candidate: str
    mae_difference: legacy.FiniteSampleInterval
    r2_difference: legacy.FiniteSampleInterval


@dataclass(frozen=True, slots=True)
class NestedBootstrapSummary:
    seed: int
    replicates_requested: int
    replicates_successful: int
    selected_mae: legacy.FiniteSampleInterval
    selected_r2: legacy.FiniteSampleInterval
    paired_deltas: tuple[PairedDeltaInterval, ...]
    selection_counts: tuple[SelectionCount, ...]
    selection_decision_denominator: int
    comparison_observation_denominator: int


@dataclass(frozen=True, slots=True)
class NestedSelectionGeneResult:
    profile_id: str
    profile_digest: str
    request_digest: str
    accepted: bool
    complete_count: int
    common_oof_count: int
    selected_oof_count: int
    point_folds: tuple[OuterSelectionTrace, ...]
    point_summary: NestedPointSummary | None
    bootstrap_requested: int
    bootstrap_attempted: int
    bootstrap_successful: int
    bootstrap_required: int
    uncertainty: NestedBootstrapSummary | None
    failure_reason: str | None
    limitations: tuple[str, ...]


def nested_selection_profile_digest() -> str:
    profile = algorithm_profile()
    root = files(__package__)
    return sha256_digest(
        {
            "profile_id": PROFILE_ID,
            "legacy_profile_digest": profile.profile_digest,
            "legacy_semantic_digest": profile.engine_semantic_digest,
            "source_digests": {
                name: "sha256:"
                + hashlib.sha256(
                    root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in ("nested_selection.py", "convergence.py")
            },
            "outer_gates": {"training": 48, "held_out": 3, "folds": 4, "oof": 60},
            "inner_gates": {"training": INNER_MIN_TRAIN, "held_out": INNER_MIN_TEST, "folds": 4},
            "candidates_in_exact_tie_order": CANDIDATE_ORDER,
            "iteration_budget": ITERATION_BUDGET,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_required": BOOTSTRAP_REQUIRED,
            "comparison_draw_basis": "legacy request-digest PCG outer-fold-stratified patient bootstrap",
            "legacy_artifact_promotion": False,
        }
    )


def _fit_candidate(
    candidate: str,
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    *,
    outer_fold: int,
    inner_fold: int | None,
) -> CandidateFit:
    # Context arguments make the training boundary directly auditable without
    # introducing global state or consulting held-out outcomes.
    del outer_fold, inner_fold
    if candidate not in CANDIDATE_ORDER:
        raise ValueError("unknown nested-selection candidate")
    if candidate == "training_median":
        return CandidateFit(candidate, float(np.median(protein)), None, None)
    design = (
        np.column_stack((rna, cnv))
        if candidate == "full"
        else (rna if candidate == "rna_only" else cnv)[:, None]
    )
    model = fit_huber_with_budget(design, protein, max_iterations=ITERATION_BUDGET)
    reason = (
        "candidate is numerically unidentified"
        if model is None
        else (None if model.converged else "candidate did not converge within 240 iterations")
    )
    return CandidateFit(candidate, None, model, reason)


def _empty_candidates(reason: str) -> tuple[CandidateSelectionEvidence, ...]:
    return tuple(
        CandidateSelectionEvidence(
            candidate=candidate,
            eligible=False,
            inner_oof_count=0,
            inner_mae=None,
            failure_reasons=(reason,),
        )
        for candidate in CANDIDATE_ORDER
    )


def _inner_select(
    cnv: FloatArray, rna: FloatArray, protein: FloatArray, folds: FoldArray, *, outer_fold: int
) -> InnerSelection:
    inner_folds = tuple(fold for fold in range(5) if fold != outer_fold)
    counts = tuple((int(np.sum(folds != fold)), int(np.sum(folds == fold))) for fold in inner_folds)
    if any(
        training < INNER_MIN_TRAIN or held_out < INNER_MIN_TEST for training, held_out in counts
    ):
        reason = "inner support gates failed; training-median fallback without a MAE winner"
        return InnerSelection(
            "training_median", "fallback_inner_support", reason, _empty_candidates(reason)
        )
    evidence = []
    for candidate in CANDIDATE_ORDER:
        prediction = np.full(len(protein), np.nan, dtype=np.float64)
        reasons = []
        for fold in inner_folds:
            training, held_out = folds != fold, folds == fold
            attempt = _fit_candidate(
                candidate,
                cnv[training],
                rna[training],
                protein[training],
                outer_fold=outer_fold,
                inner_fold=fold,
            )
            if not attempt.available:
                reasons.append(f"inner fold {fold}: {attempt.failure_reason}")
                continue
            values = attempt.predict(cnv[held_out], rna[held_out])
            if not bool(np.all(np.isfinite(values))):
                reasons.append(f"inner fold {fold}: non-finite prediction")
                continue
            prediction[held_out] = values
        observed = int(np.isfinite(prediction).sum())
        candidate_eligible = not reasons and observed == len(protein)
        mae = float(np.mean(np.abs(protein - prediction))) if candidate_eligible else None
        if mae is not None and not isfinite(mae):
            reasons.append("non-finite inner OOF MAE")
            candidate_eligible, mae = False, None
        evidence.append(
            CandidateSelectionEvidence(candidate, candidate_eligible, observed, mae, tuple(reasons))
        )
    eligible_candidates = tuple(
        item for item in evidence if item.eligible and item.inner_mae is not None
    )
    # A supported training median is always finite; preserving an explicit
    # fallback here also makes future solver failures fail closed.
    if not eligible_candidates:
        reason = "no candidate had complete finite inner OOF support"
        return InnerSelection("training_median", "fallback_inner_support", reason, tuple(evidence))
    winner = min(
        eligible_candidates,
        key=lambda item: (
            item.inner_mae if item.inner_mae is not None else float("inf"),
            CANDIDATE_ORDER.index(item.candidate),
        ),
    )
    return InnerSelection(winner.candidate, "inner_mae", None, tuple(evidence))


def _metrics(
    candidate: str, truth: FloatArray, prediction: FloatArray, baseline: FloatArray
) -> ReconstructionMetrics | None:
    if len(truth) < 3:
        return None
    residual, null_residual = truth - prediction, truth - baseline
    sse, null_sse = float(np.dot(residual, residual)), float(np.dot(null_residual, null_residual))
    if not isfinite(sse) or not isfinite(null_sse) or null_sse <= 1e-12:
        return None
    return ReconstructionMetrics(
        candidate,
        len(truth),
        float(np.mean(np.abs(residual))),
        sqrt(sse / len(truth)),
        1.0 - sse / null_sse,
    )


def _point_summary(
    protein: FloatArray,
    selected: FloatArray,
    fixed: tuple[FloatArray, ...],
    common: npt.NDArray[np.bool_],
    folds: FoldArray,
    *,
    traces: tuple[OuterSelectionTrace, ...],
) -> NestedPointSummary | None:
    selected_metric = _metrics(
        "selected_policy", protein[common], selected[common], fixed[0][common]
    )
    fixed_metrics = tuple(
        _metrics(candidate, protein[common], values[common], fixed[0][common])
        for candidate, values in zip(CANDIDATE_ORDER, fixed, strict=True)
    )
    if selected_metric is None or any(metric is None for metric in fixed_metrics):
        return None
    present = tuple(metric for metric in fixed_metrics if metric is not None)
    decisions = tuple(trace for trace in traces if trace.comparison_accepted)
    counts = tuple(
        SelectionCount(
            candidate,
            sum(trace.selected_candidate == candidate for trace in decisions),
            int(
                np.sum(
                    common
                    & np.isin(
                        folds,
                        [
                            trace.fold
                            for trace in decisions
                            if trace.selected_candidate == candidate
                        ],
                    )
                )
            ),
        )
        for candidate in CANDIDATE_ORDER
    )
    return NestedPointSummary(
        common_oof_count=int(common.sum()),
        valid_outer_folds=len(decisions),
        selected=selected_metric,
        fixed=present,
        deltas=tuple(
            PairedMetricDelta(
                metric.candidate,
                selected_metric.mae - metric.mae,
                selected_metric.r2_vs_fold_train_median - metric.r2_vs_fold_train_median,
            )
            for metric in present
        ),
        selection_counts=counts,
        selection_decision_denominator=len(decisions),
    )


def _immutable_float(values: FloatArray) -> FloatArray:
    return np.frombuffer(np.ascontiguousarray(values).tobytes(), dtype=np.float64)


def _validated_inputs(
    cnv: object, rna: object, protein: object, folds: object
) -> tuple[FloatArray, FloatArray, FloatArray, FoldArray]:
    arrays = legacy._validate_inputs(cnv, rna, protein, folds, legacy.DiscordanceFitConfiguration())
    if any(
        bool(np.any(np.abs(values[np.isfinite(values)]) > MAX_ABSOLUTE_INPUT))
        for values in arrays[:3]
    ):
        raise ValueError("nested-selection inputs exceed the finite magnitude bound")
    return arrays


def nested_point_fit(cnv: object, rna: object, protein: object, folds: object) -> NestedPointFit:
    """Development-only nested point refit, preserving supplied bootstrap order."""

    cnv_values, rna_values, protein_values, fold_values = _validated_inputs(
        cnv, rna, protein, folds
    )
    complete = np.isfinite(cnv_values) & np.isfinite(rna_values) & np.isfinite(protein_values)
    selected = np.full(len(protein_values), np.nan, dtype=np.float64)
    fixed = tuple(np.full(len(protein_values), np.nan, dtype=np.float64) for _ in CANDIDATE_ORDER)
    traces = []
    for fold in range(5):
        training, held_out = complete & (fold_values != fold), complete & (fold_values == fold)
        train_count, test_count = int(training.sum()), int(held_out.sum())
        if train_count < 48 or test_count < 3:
            support_reason = (
                "insufficient outer training complete cases"
                if train_count < 48
                else "insufficient outer held-out complete cases"
            )
            traces.append(
                OuterSelectionTrace(
                    fold=fold,
                    training_complete=train_count,
                    held_out_complete=test_count,
                    selected_candidate="training_median",
                    selection_basis="outer_support_abstention",
                    fallback_reason=None,
                    candidates=_empty_candidates(support_reason),
                    outer_fits=(),
                    selected_prediction_available=False,
                    comparison_accepted=False,
                    failure_reason=support_reason,
                )
            )
            continue
        selection = _inner_select(
            cnv_values[training],
            rna_values[training],
            protein_values[training],
            fold_values[training],
            outer_fold=fold,
        )
        attempts = tuple(
            _fit_candidate(
                candidate,
                cnv_values[training],
                rna_values[training],
                protein_values[training],
                outer_fold=fold,
                inner_fold=None,
            )
            for candidate in CANDIDATE_ORDER
        )
        outer_fits = []
        for candidate, attempt, values in zip(CANDIDATE_ORDER, attempts, fixed, strict=True):
            reason = attempt.failure_reason
            available = attempt.available
            if available:
                prediction = attempt.predict(cnv_values[held_out], rna_values[held_out])
                available = bool(np.all(np.isfinite(prediction)))
                if available:
                    values[held_out] = prediction
                else:
                    reason = "non-finite outer prediction"
            outer_fits.append(
                OuterFitEvidence(
                    candidate,
                    available,
                    None if attempt.model is None else attempt.model.iterations,
                    reason,
                )
            )
        selected_candidate, basis, fallback = (
            selection.selected_candidate,
            selection.selection_basis,
            selection.fallback_reason,
        )
        selected_index = CANDIDATE_ORDER.index(selected_candidate)
        if not outer_fits[selected_index].available:
            inner_winner = selected_candidate
            selected_candidate, selected_index, basis = (
                "training_median",
                0,
                "fallback_selected_refit",
            )
            fallback = f"selected {inner_winner} outer-training refit failed; training-median fallback without consulting outer-test outcomes"
        available = outer_fits[selected_index].available
        if available:
            selected[held_out] = fixed[selected_index][held_out]
        accepted = available and all(item.available for item in outer_fits)
        traces.append(
            OuterSelectionTrace(
                fold,
                train_count,
                test_count,
                selected_candidate,
                basis,
                fallback,
                selection.candidates,
                tuple(outer_fits),
                available,
                accepted,
                None
                if accepted
                else "one or more fixed outer refits unavailable on common comparison support",
            )
        )
    common = (
        complete
        & np.isfinite(selected)
        & np.all(np.column_stack(tuple(np.isfinite(values) for values in fixed)), axis=1)
    )
    summary = _point_summary(
        protein_values, selected, fixed, common, fold_values, traces=tuple(traces)
    )
    accepted = (
        summary is not None and summary.valid_outer_folds >= 4 and summary.common_oof_count >= 60
    )
    observed = np.where(np.isfinite(selected), protein_values, np.nan)
    return NestedPointFit(
        int(complete.sum()),
        int(common.sum()),
        int(np.isfinite(selected).sum()),
        accepted,
        tuple(traces),
        summary,
        _immutable_float(observed),
        _immutable_float(selected),
        tuple(_immutable_float(values) for values in fixed),
        np.frombuffer(np.ascontiguousarray(common).tobytes(), dtype=np.bool_),
    )


def _bootstrap(
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    *,
    point: NestedPointSummary,
    request_digest: str,
) -> tuple[int, NestedBootstrapSummary | None]:
    seed = legacy._bootstrap_seed(request_digest)
    rng = np.random.default_rng(seed)
    selected_mae, selected_r2 = [], []
    mae_deltas: tuple[list[float], ...] = tuple([] for _ in CANDIDATE_ORDER)
    r2_deltas: tuple[list[float], ...] = tuple([] for _ in CANDIDATE_ORDER)
    decisions = [0] * 4
    observations = [0] * 4
    for _ in range(BOOTSTRAP_REPLICATES):
        indices = legacy._stratified_patient_bootstrap_indices(folds, rng)
        refit = nested_point_fit(cnv[indices], rna[indices], protein[indices], folds[indices])
        summary = refit.summary
        if not refit.accepted or summary is None:
            continue
        selected_mae.append(summary.selected.mae)
        selected_r2.append(summary.selected.r2_vs_fold_train_median)
        for index, (delta, count) in enumerate(
            zip(summary.deltas, summary.selection_counts, strict=True)
        ):
            mae_deltas[index].append(delta.mae_difference)
            r2_deltas[index].append(delta.r2_difference)
            decisions[index] += count.fold_decisions
            observations[index] += count.comparison_observations
    successful = len(selected_mae)
    if successful < BOOTSTRAP_REQUIRED:
        return successful, None
    return successful, NestedBootstrapSummary(
        seed,
        BOOTSTRAP_REPLICATES,
        successful,
        legacy._finite_sample_interval(selected_mae, point.selected.mae),
        legacy._finite_sample_interval(selected_r2, point.selected.r2_vs_fold_train_median),
        tuple(
            PairedDeltaInterval(
                candidate,
                legacy._finite_sample_interval(
                    mae_deltas[index], point.deltas[index].mae_difference
                ),
                legacy._finite_sample_interval(r2_deltas[index], point.deltas[index].r2_difference),
            )
            for index, candidate in enumerate(CANDIDATE_ORDER)
        ),
        tuple(
            SelectionCount(candidate, decisions[index], observations[index])
            for index, candidate in enumerate(CANDIDATE_ORDER)
        ),
        sum(decisions),
        sum(observations),
    )


def fit_nested_selection_gene(
    cnv: object, rna: object, protein: object, folds: object, *, request_digest: str
) -> NestedSelectionGeneResult:
    """Run the complete, versioned selection policy and its 128 paired refits."""

    digest = legacy._validate_request_digest(request_digest)
    arrays = _validated_inputs(cnv, rna, protein, folds)
    order = legacy._canonical_row_order(*arrays)
    cnv_array, rna_array, protein_array, fold_array = arrays
    canonical = cnv_array[order], rna_array[order], protein_array[order], fold_array[order]
    point = nested_point_fit(*canonical)
    attempted = successful = 0
    uncertainty = None
    failure: str | None = (
        "nested point fit failed unchanged outer fold/common-OOF/finite-metric gates"
    )
    if point.accepted and point.summary is not None:
        attempted = BOOTSTRAP_REPLICATES
        successful, uncertainty = _bootstrap(*canonical, point=point.summary, request_digest=digest)
        failure = (
            "fewer than 103 of 128 full nested bootstrap refits passed"
            if uncertainty is None
            else None
        )
    return NestedSelectionGeneResult(
        PROFILE_ID,
        nested_selection_profile_digest(),
        digest,
        uncertainty is not None,
        point.complete_count,
        point.common_oof_count,
        point.selected_oof_count,
        point.fold_trace,
        point.summary,
        BOOTSTRAP_REPLICATES,
        attempted,
        successful,
        BOOTSTRAP_REQUIRED,
        uncertainty,
        failure,
        (
            "This separately versioned nested policy does not change the legacy estimator, artifact, or outer support gates.",
            "The independent inner32 policy was introduced for this source-cohort selection study and is not an independent validation threshold.",
            "Inner MAE compares every eligible candidate on the same complete outer-training cases; a failed candidate is disqualified rather than scored on fewer rows.",
            "Main outer comparisons require common selected/fixed-family support; selected-only coverage is descriptive and does not supply unmatched performance comparisons.",
            "Every bootstrap draw repeats selection and refitting within fixed outer-fold patient strata; unsuccessful draws are counted and not replaced.",
            "Selection counts describe algorithm instability among accepted comparison-support fold decisions, not biological probabilities or independent patient evidence.",
            "Nominal 90% percentile intervals are source-cohort sampling summaries, not calibrated patient intervals, multiplicity-controlled discovery tests, or external validation.",
            "Upstream whole-cohort preprocessing, complete-case selection, and omitted covariates limit interpretation; no pooled slope, biological pattern, patient prediction, or clinical claim is emitted.",
        ),
    )


__all__ = [
    "BOOTSTRAP_REPLICATES",
    "BOOTSTRAP_REQUIRED",
    "CANDIDATE_ORDER",
    "INNER_MIN_TEST",
    "INNER_MIN_TRAIN",
    "ITERATION_BUDGET",
    "PROFILE_ID",
    "NestedPointFit",
    "NestedSelectionGeneResult",
    "fit_nested_selection_gene",
    "nested_point_fit",
    "nested_selection_profile_digest",
]
