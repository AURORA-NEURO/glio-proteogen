"""Post hoc empirical source-refit and external-patient sensitivity.

Original point admission is immutable. Bootstrap copies are frequency mass,
never additional biological patients. Percentile ranges describe the admitted
empirical resampling procedure; calibrated inferential coverage is unproved.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from math import ceil, isfinite
from typing import Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)

from . import transfer
from .resampling import REPLICATES, TwoCohortDraw, generate_two_cohort_draws

PROFILE_ID: Final = "cptac-gbm-provider-transfer-two-cohort-sensitivity/1.0.0"
REQUIRED: Final = 103
FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]
BoolArray = npt.NDArray[np.bool_]
MODEL_ORDER: Final = (*transfer.CANDIDATE_ORDER, "selected_policy")


def _immutable[Scalar: np.generic](values: npt.NDArray[Scalar]) -> npt.NDArray[Scalar]:
    return np.frombuffer(np.ascontiguousarray(values).tobytes(), dtype=values.dtype).reshape(
        values.shape
    )


@dataclass(frozen=True, slots=True, eq=False)
class SourceGeneInputs:
    cnv: FloatArray = field(repr=False)
    rna: FloatArray = field(repr=False)
    protein: FloatArray = field(repr=False)
    folds: FoldArray = field(repr=False)

    def __post_init__(self) -> None:
        arrays = nested._validated_inputs(self.cnv, self.rna, self.protein, self.folds)
        for name, value in zip(("cnv", "rna", "protein"), arrays[:3], strict=True):
            object.__setattr__(self, name, _immutable(value))
        object.__setattr__(self, "folds", _immutable(arrays[3]))

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient source measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient source measurements cannot be serialized")


@dataclass(frozen=True, slots=True, eq=False)
class ExternalGeneInputs:
    cnv: FloatArray = field(repr=False)
    rna: FloatArray = field(repr=False)
    protein: FloatArray = field(repr=False)

    def __post_init__(self) -> None:
        arrays = transfer._external_arrays(self.cnv, self.rna, self.protein)
        for name, value in zip(("cnv", "rna", "protein"), arrays, strict=True):
            object.__setattr__(self, name, _immutable(value))

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient external measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient external measurements cannot be serialized")


@dataclass(frozen=True, slots=True)
class DistributionSummary:
    minimum: float
    median: float
    maximum: float
    draws: int


@dataclass(frozen=True, slots=True)
class SamplingDiagnostics:
    source_cohort_unique: DistributionSummary
    external_cohort_unique: DistributionSummary
    source_joint_complete_mass: DistributionSummary
    source_joint_complete_unique: DistributionSummary
    source_joint_complete_effective_count: DistributionSummary
    external_joint_complete_mass: DistributionSummary
    external_joint_complete_unique: DistributionSummary
    external_joint_complete_effective_count: DistributionSummary
    source_outer_training_unique_minimum: DistributionSummary
    source_inner_training_unique_minimum: DistributionSummary
    source_outer_training_effective_minimum: DistributionSummary
    source_inner_training_effective_minimum: DistributionSummary
    source_fold_joint_unique: tuple[DistributionSummary, ...]
    source_fold_joint_effective: tuple[DistributionSummary, ...]
    draws_with_source_joint_unique_at_least60: int
    draws_with_all_distinct_source_legacy_counts: int
    unique_diagnostics_are_gates: bool = False
    bootstrap_mass_is_independent_patient_count: bool = False


@dataclass(frozen=True, slots=True)
class PercentileRange:
    point_estimate: float
    lower: float
    upper: float
    nominal_level: float
    replicates: int
    calibrated_coverage_established: bool = False


@dataclass(frozen=True, slots=True)
class SensitivityMetricRanges:
    candidate: str
    mae: PercentileRange
    rmse: PercentileRange
    r2_vs_source_training_median: PercentileRange | None


@dataclass(frozen=True, slots=True)
class PairedVarianceIdentity:
    joint_variance: float
    frozen_reference_variance: float
    source_perturbation_variance: float
    twice_covariance: float
    reconstruction_error: float
    replicates: int
    reconstructed_variance: float
    degrees_of_freedom: int = 1
    causal_variance_partition: bool = False


@dataclass(frozen=True, slots=True)
class MatchedSensitivityRanges:
    joint_model_intervals: tuple[SensitivityMetricRanges, ...]
    frozen_reference_intervals: tuple[SensitivityMetricRanges, ...]
    primary_joint: PercentileRange
    primary_frozen_reference: PercentileRange
    primary_refit_minus_frozen: PercentileRange
    secondary_joint: PercentileRange
    secondary_frozen_reference: PercentileRange
    secondary_refit_minus_frozen: PercentileRange
    primary_variance_identity: PairedVarianceIdentity
    secondary_variance_identity: PairedVarianceIdentity
    matched_joint_successful_draws: int
    source_fitting_repeated: bool = True
    source_selection_repeated: bool = True
    fixed_original_folds: bool = True
    post_hoc: bool = True


@dataclass(frozen=True, slots=True)
class SelectionFrequency:
    candidate: str
    accepted_source_refits: int
    successful_joint_comparisons: int


@dataclass(frozen=True, slots=True)
class FailureCount:
    stage: str
    reason: str
    replicates: int


@dataclass(frozen=True, slots=True)
class TwoCohortSensitivityResult:
    profile_id: str
    request_digest: str
    parent_result: transfer.TransferGeneResult
    accepted: bool
    draws_attempted: int
    draws_successful: int
    draws_required: int
    uncertainty: MatchedSensitivityRanges | None
    failure_reason: str | None
    source_sampling_diagnostics: SamplingDiagnostics | None
    selection_frequencies: tuple[SelectionFrequency, ...]
    accepted_source_refits: int
    failure_counts: tuple[FailureCount, ...]
    frozen_reference_available_draws: int = 0
    reference_available_but_unmatched_draws: int = 0
    unavailable_source_selections: int = 0
    original_point_estimates_changed: bool = False
    post_hoc: bool = True
    calibrated_coverage_established: bool = False
    aligned_external_validation: bool = False
    clinical_validation: bool = False
    default_promotion: bool = False


@dataclass(frozen=True, slots=True)
class PanelSensitivityResult:
    profile_id: str
    request_digest: str
    gene_results: tuple[TwoCohortSensitivityResult, ...]
    point_eligible_genes: int
    jointly_successful_draws_all_eligible: int | None
    shared_replicates: int = REPLICATES
    cross_gene_inference_established: bool = False


@dataclass(frozen=True, slots=True)
class _GeneExecution:
    result: TwoCohortSensitivityResult
    successful: BoolArray = field(repr=False)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient replicate masks cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient replicate masks cannot be serialized")


def _request_digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("a canonical whole-request digest is required")
    return value


def _complete(cnv: FloatArray, rna: FloatArray, protein: FloatArray) -> BoolArray:
    return np.isfinite(cnv) & np.isfinite(rna) & np.isfinite(protein)


def _scores(
    source: transfer.FrozenSourceGeneFit, cnv: FloatArray, rna: FloatArray, protein: FloatArray
) -> tuple[transfer.TransferMetrics, ...] | None:
    complete = _complete(cnv, rna, protein)
    if int(complete.sum()) < transfer.EXTERNAL_MINIMUM:
        return None
    if (
        not source.receipt.accepted
        or tuple(item.candidate for item in source._predictors) != transfer.CANDIDATE_ORDER
        or source.receipt.selected_candidate not in transfer.CANDIDATE_ORDER
    ):
        raise ValueError("accepted source predictor contract is invalid")
    fixed = tuple(item.predict(cnv[complete], rna[complete]) for item in source._predictors)
    predictions = (*fixed, fixed[transfer.CANDIDATE_ORDER.index(source.receipt.selected_candidate)])
    if not all(bool(np.all(np.isfinite(values))) for values in predictions):
        return None
    median = source._predictors[0].median
    if median is None:
        raise ValueError("source training-median predictor is unavailable")
    metrics = tuple(
        transfer._metrics(candidate, protein[complete], values, median)
        for candidate, values in zip(MODEL_ORDER, predictions, strict=True)
    )
    return metrics if all(isfinite(item.mae) and isfinite(item.rmse) for item in metrics) else None


def _range(values: list[float], point: float) -> PercentileRange:
    ordered = sorted(values)
    count = len(ordered)
    if count < REQUIRED or not isfinite(point) or not all(isfinite(value) for value in ordered):
        raise ValueError("sensitivity ranges require sufficient finite resampling evaluations")
    return PercentileRange(
        point, ordered[max(1, ceil(count * 0.05)) - 1], ordered[ceil(count * 0.95) - 1], 0.9, count
    )


def _variance_identity(joint: list[float], reference: list[float]) -> PairedVarianceIdentity:
    a, b = np.asarray(joint), np.asarray(reference)
    if len(a) != len(b) or len(a) < REQUIRED:
        raise ValueError("paired variance accounting requires identical successful draws")
    delta = a - b
    va, vb, vd = (float(np.var(values, ddof=1)) for values in (a, b, delta))
    twice = 2.0 * float(np.dot(b - np.mean(b), delta - np.mean(delta))) / (len(a) - 1)
    values = (va, vb, vd, twice, va - (vb + vd + twice))
    if not all(isfinite(value) for value in values):
        raise ValueError("paired variance accounting is non-finite")
    return PairedVarianceIdentity(*values, len(a), vb + vd + twice)


def _uncertainty(
    joint: list[tuple[transfer.TransferMetrics, ...]],
    reference: list[tuple[transfer.TransferMetrics, ...]],
    point: transfer.TransferGeneResult,
) -> MatchedSensitivityRanges:
    joint_intervals: list[SensitivityMetricRanges] = []
    reference_intervals: list[SensitivityMetricRanges] = []
    for index, candidate in enumerate(MODEL_ORDER):
        pairs = tuple((a[index], b[index]) for a, b in zip(joint, reference, strict=True))
        paired_r2 = tuple(
            (a.r2_vs_source_training_median, b.r2_vs_source_training_median)
            for a, b in pairs
            if a.r2_vs_source_training_median is not None
            and b.r2_vs_source_training_median is not None
            and isfinite(a.r2_vs_source_training_median)
            and isfinite(b.r2_vs_source_training_median)
        )
        anchor = point.point_metrics[index]
        for side, target in ((0, joint_intervals), (1, reference_intervals)):
            metrics = [pair[side] for pair in pairs]
            r2_values = [float(pair[side]) for pair in paired_r2 if pair[side] is not None]
            target.append(
                SensitivityMetricRanges(
                    candidate,
                    _range([item.mae for item in metrics], anchor.mae),
                    _range([item.rmse for item in metrics], anchor.rmse),
                    _range(r2_values, anchor.r2_vs_source_training_median)
                    if len(r2_values) >= REQUIRED
                    and anchor.r2_vs_source_training_median is not None
                    else None,
                )
            )
    primary_a = [row[3].mae - row[2].mae for row in joint]
    primary_b = [row[3].mae - row[2].mae for row in reference]
    secondary_a = [row[4].mae - row[3].mae for row in joint]
    secondary_b = [row[4].mae - row[3].mae for row in reference]
    primary_point, secondary_point = (
        point.primary_full_minus_cnv_mae,
        point.secondary_selected_minus_full_mae,
    )
    if primary_point is None or secondary_point is None:
        raise ValueError("admitted parent comparison lacks its frozen point contrasts")
    return MatchedSensitivityRanges(
        tuple(joint_intervals),
        tuple(reference_intervals),
        _range(primary_a, primary_point),
        _range(primary_b, primary_point),
        _range([a - b for a, b in zip(primary_a, primary_b, strict=True)], 0.0),
        _range(secondary_a, secondary_point),
        _range(secondary_b, secondary_point),
        _range([a - b for a, b in zip(secondary_a, secondary_b, strict=True)], 0.0),
        _variance_identity(primary_a, primary_b),
        _variance_identity(secondary_a, secondary_b),
        len(joint),
    )


def _summary(values: list[float]) -> DistributionSummary:
    return DistributionSummary(min(values), float(np.median(values)), max(values), len(values))


def _effective(indices: npt.NDArray[np.int64]) -> float:
    if len(indices) == 0:
        return 0.0
    _, counts = np.unique(indices, return_counts=True)
    return len(indices) ** 2 / float(np.dot(counts, counts))


def _diagnostics(
    source: SourceGeneInputs, external: ExternalGeneInputs, draws: tuple[TwoCohortDraw, ...]
) -> SamplingDiagnostics:
    source_complete = _complete(source.cnv, source.rna, source.protein)
    external_complete = _complete(external.cnv, external.rna, external.protein)
    columns: tuple[list[float], ...] = tuple([] for _ in range(12))
    fold_unique: tuple[list[float], ...] = tuple([] for _ in range(5))
    fold_effective: tuple[list[float], ...] = tuple([] for _ in range(5))
    strict_oof = strict_all = 0
    for draw in draws:
        source_indices = draw.source_indices[source_complete[draw.source_indices]]
        external_indices = draw.external_indices[external_complete[draw.external_indices]]
        unique = np.unique(source_indices)
        counts = tuple(int(np.sum(source.folds[unique] == fold)) for fold in range(5))
        outer_train = tuple(len(unique) - count for count in counts)
        inner_train = tuple(
            len(unique) - counts[a] - counts[b] for a in range(5) for b in range(5) if a != b
        )
        occurrence_folds = source.folds[source_indices]
        outer_effective = tuple(
            _effective(source_indices[occurrence_folds != fold]) for fold in range(5)
        )
        inner_effective = tuple(
            _effective(source_indices[(occurrence_folds != a) & (occurrence_folds != b)])
            for a in range(5)
            for b in range(5)
            if a != b
        )
        for fold in range(5):
            fold_unique[fold].append(float(counts[fold]))
            fold_effective[fold].append(_effective(source_indices[occurrence_folds == fold]))
        row = (
            float(draw.receipt.source_unique_count),
            float(draw.receipt.external_unique_count),
            float(len(source_indices)),
            float(len(unique)),
            _effective(source_indices),
            float(len(external_indices)),
            float(len(np.unique(external_indices))),
            _effective(external_indices),
            float(min(outer_train)),
            float(min(inner_train)),
            min(outer_effective),
            min(inner_effective),
        )
        for values, value in zip(columns, row, strict=True):
            values.append(value)
        strict_oof += len(unique) >= 60
        strict_all += (
            len(unique) >= 60
            and min(outer_train) >= 48
            and min(counts) >= 3
            and min(inner_train) >= 32
        )
    return SamplingDiagnostics(
        source_cohort_unique=_summary(columns[0]),
        external_cohort_unique=_summary(columns[1]),
        source_joint_complete_mass=_summary(columns[2]),
        source_joint_complete_unique=_summary(columns[3]),
        source_joint_complete_effective_count=_summary(columns[4]),
        external_joint_complete_mass=_summary(columns[5]),
        external_joint_complete_unique=_summary(columns[6]),
        external_joint_complete_effective_count=_summary(columns[7]),
        source_outer_training_unique_minimum=_summary(columns[8]),
        source_inner_training_unique_minimum=_summary(columns[9]),
        source_outer_training_effective_minimum=_summary(columns[10]),
        source_inner_training_effective_minimum=_summary(columns[11]),
        source_fold_joint_unique=tuple(_summary(values) for values in fold_unique),
        source_fold_joint_effective=tuple(_summary(values) for values in fold_effective),
        draws_with_source_joint_unique_at_least60=strict_oof,
        draws_with_all_distinct_source_legacy_counts=strict_all,
    )


def _run_gene(
    *,
    source_fit: transfer.FrozenSourceGeneFit,
    source_inputs: SourceGeneInputs,
    external_inputs: ExternalGeneInputs,
    parent_result: transfer.TransferGeneResult,
    request_digest: str,
) -> _GeneExecution:
    digest = _request_digest(request_digest)
    if (
        not isinstance(source_fit, transfer.FrozenSourceGeneFit)
        or not isinstance(source_inputs, SourceGeneInputs)
        or not isinstance(external_inputs, ExternalGeneInputs)
        or not isinstance(parent_result, transfer.TransferGeneResult)
    ):
        raise TypeError(
            "sensitivity requires validated transient inputs and a frozen parent result"
        )
    replay_fit = transfer.fit_source_gene(
        source_inputs.cnv, source_inputs.rna, source_inputs.protein, source_inputs.folds
    )
    if (
        replay_fit != source_fit
        or source_fit.receipt != parent_result.source
        or parent_result.profile_id != transfer.PROFILE_ID
    ):
        raise ValueError("source inputs, frozen fit and parent result do not agree")
    replay = transfer.evaluate_external_gene(
        source_fit,
        external_inputs.cnv,
        external_inputs.rna,
        external_inputs.protein,
        request_digest=parent_result.request_digest,
    )
    if replay != parent_result:
        raise ValueError("external inputs do not reproduce the immutable parent result")
    successful = np.zeros(REPLICATES, dtype=np.bool_)
    if not parent_result.accepted:
        return _GeneExecution(
            TwoCohortSensitivityResult(
                profile_id=PROFILE_ID,
                request_digest=digest,
                parent_result=parent_result,
                accepted=False,
                draws_attempted=0,
                draws_successful=0,
                draws_required=REQUIRED,
                uncertainty=None,
                failure_reason="original point abstention retained; resampling cannot rescue eligibility",
                source_sampling_diagnostics=None,
                selection_frequencies=(),
                accepted_source_refits=0,
                failure_counts=(),
            ),
            _immutable(successful),
        )
    draws = generate_two_cohort_draws(
        source_folds=source_inputs.folds,
        external_count=len(external_inputs.protein),
        request_digest=digest,
    )
    joint: list[tuple[transfer.TransferMetrics, ...]] = []
    reference: list[tuple[transfer.TransferMetrics, ...]] = []
    source_choices: Counter[str] = Counter()
    joint_choices: Counter[str] = Counter()
    failures: Counter[tuple[str, str]] = Counter()
    reference_available = 0
    for draw in draws:
        indices = draw.source_indices
        refit = transfer.fit_source_gene(
            source_inputs.cnv[indices],
            source_inputs.rna[indices],
            source_inputs.protein[indices],
            draw.source_folds,
        )
        external_indices = draw.external_indices
        arrays = (
            external_inputs.cnv[external_indices],
            external_inputs.rna[external_indices],
            external_inputs.protein[external_indices],
        )
        b = _scores(source_fit, *arrays)
        reference_available += b is not None
        if not refit.receipt.accepted:
            failures[
                ("source_refit", refit.receipt.failure_reason or "source refit not accepted")
            ] += 1
            continue
        choice = refit.receipt.selected_candidate
        if choice is None:
            raise ValueError("accepted source refit lost its selected family")
        source_choices[choice] += 1
        a = _scores(refit, *arrays)
        if a is None or b is None:
            failures[
                ("external_comparison", "common external mass or finite predictions unavailable")
            ] += 1
            continue
        joint.append(a)
        reference.append(b)
        joint_choices[choice] += 1
        successful[draw.receipt.draw_ordinal] = True
    count = len(joint)
    uncertainty = _uncertainty(joint, reference, parent_result) if count >= REQUIRED else None
    result = TwoCohortSensitivityResult(
        PROFILE_ID,
        digest,
        parent_result,
        uncertainty is not None,
        REPLICATES,
        count,
        REQUIRED,
        uncertainty,
        None if uncertainty is not None else "joint source-refit sensitivity support below103of128",
        _diagnostics(source_inputs, external_inputs, draws),
        tuple(
            SelectionFrequency(candidate, source_choices[candidate], joint_choices[candidate])
            for candidate in transfer.CANDIDATE_ORDER
        ),
        sum(source_choices.values()),
        tuple(
            FailureCount(stage, reason, frequency)
            for (stage, reason), frequency in sorted(failures.items())
        ),
        frozen_reference_available_draws=reference_available,
        reference_available_but_unmatched_draws=reference_available - count,
        unavailable_source_selections=REPLICATES - sum(source_choices.values()),
    )
    return _GeneExecution(result, _immutable(successful))


def evaluate_two_cohort_sensitivity(
    *,
    source_fit: transfer.FrozenSourceGeneFit,
    source_inputs: SourceGeneInputs,
    external_inputs: ExternalGeneInputs,
    parent_result: transfer.TransferGeneResult,
    request_digest: str,
) -> TwoCohortSensitivityResult:
    """Repeat the source procedure under one globally seeded cohort schedule."""
    return _run_gene(
        source_fit=source_fit,
        source_inputs=source_inputs,
        external_inputs=external_inputs,
        parent_result=parent_result,
        request_digest=request_digest,
    ).result


def evaluate_panel_sensitivity(
    *,
    source_fits: tuple[transfer.FrozenSourceGeneFit, ...],
    source_inputs: tuple[SourceGeneInputs, ...],
    external_inputs: tuple[ExternalGeneInputs, ...],
    parent_results: tuple[transfer.TransferGeneResult, ...],
    request_digest: str,
) -> PanelSensitivityResult:
    """Run shared patient draws; expose only the aggregate success intersection."""
    digest = _request_digest(request_digest)
    if (
        any(
            type(value) is not tuple
            for value in (source_fits, source_inputs, external_inputs, parent_results)
        )
        or len(
            {len(value) for value in (source_fits, source_inputs, external_inputs, parent_results)}
        )
        != 1
        or not 1 <= len(source_fits) <= 32
    ):
        raise ValueError("panel inputs must be aligned bounded tuples")
    if (
        any(not isinstance(value, transfer.FrozenSourceGeneFit) for value in source_fits)
        or any(not isinstance(value, SourceGeneInputs) for value in source_inputs)
        or any(not isinstance(value, ExternalGeneInputs) for value in external_inputs)
        or any(not isinstance(value, transfer.TransferGeneResult) for value in parent_results)
    ):
        raise TypeError("panel members must use the validated source, external and parent types")
    reference_folds = source_inputs[0].folds
    reference_external_count = len(external_inputs[0].protein)
    if any(not np.array_equal(value.folds, reference_folds) for value in source_inputs) or any(
        len(value.protein) != reference_external_count for value in external_inputs
    ):
        raise ValueError("all genes must share one source fold assignment and cohort sizes")
    executions = tuple(
        _run_gene(
            source_fit=fit,
            source_inputs=source,
            external_inputs=external,
            parent_result=parent,
            request_digest=digest,
        )
        for fit, source, external, parent in zip(
            source_fits, source_inputs, external_inputs, parent_results, strict=True
        )
    )
    eligible = tuple(
        execution for execution in executions if execution.result.parent_result.accepted
    )
    common = (
        int(np.all(np.vstack([execution.successful for execution in eligible]), axis=0).sum())
        if eligible
        else None
    )
    return PanelSensitivityResult(
        PROFILE_ID,
        digest,
        tuple(execution.result for execution in executions),
        len(eligible),
        common,
    )
