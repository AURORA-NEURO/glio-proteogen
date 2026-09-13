"""End-to-end development training for the donor-aware GBmap count model.

This module creates only an in-memory, unfitted-release *candidate*.  It does
not serialize an artifact, expose a service, or relax the source-admission
boundary.  Every validation feature set and hierarchy is learned exclusively
from that fold's training donors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .aggregate import (
    MIN_STABLE_GENES_PER_LINEAGE,
    AggregateReference,
    DonorLabelAggregate,
    lineage_eligibility,
)
from .dm import dirichlet_multinomial_per_count_nll
from .errors import GbmapInputError, GbmapNumericalError
from .hierarchy import (
    DEFAULT_HIERARCHY_CONFIGURATION,
    SIMPLEX_FLOOR,
    HierarchySolverConfiguration,
    LineageHierarchyFit,
    fit_lineage_hierarchy,
    verify_hierarchy_trace,
)
from .selection import (
    StableGeneSelection,
    _build_reference_selection_cache,
    _ReferenceSelectionCache,
    _select_fold_stable_genes_precomputed,
)
from .splits import (
    TransientValidationFold,
    ValidationKind,
    ValidationSplitPlan,
    build_validation_split_plan,
)

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

DEFAULT_SHRINKAGE_GRID: Final = (0.1, 1.0, 10.0, 100.0)
MIN_EVALUABLE_WHOLE_STUDY_FOLDS: Final = 3
MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS: Final = 5
MAX_SHRINKAGE_CANDIDATES: Final = 16

FoldEvaluationState = Literal["evaluated", "abstained"]
FoldAbstentionReason = Literal[
    "split_not_evaluable",
    "stable_gene_selection_failed",
    "fewer_than_two_eligible_lineages",
    "selected_marker_union_too_small",
    "hierarchy_fit_failed",
    "hierarchy_did_not_converge",
    "no_positive_held_marker_counts",
]


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a non-Boolean real scalar")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _exact_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be an exact positive integer")
    return value


@dataclass(frozen=True, slots=True)
class TrainingConfiguration:
    """Locked candidate-selection controls; no caller-defined scoring hook exists."""

    shrinkage_grid: tuple[float, ...] = DEFAULT_SHRINKAGE_GRID
    minimum_whole_study_folds: int = MIN_EVALUABLE_WHOLE_STUDY_FOLDS
    minimum_within_study_donor_folds: int = MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS
    hierarchy: HierarchySolverConfiguration = DEFAULT_HIERARCHY_CONFIGURATION

    def __post_init__(self) -> None:
        if type(self.shrinkage_grid) is not tuple or not self.shrinkage_grid:
            raise ValueError("shrinkage_grid must be a nonempty exact tuple")
        if len(self.shrinkage_grid) > MAX_SHRINKAGE_CANDIDATES:
            raise ValueError("shrinkage grid exceeds its fixed candidate bound")
        grid = tuple(_positive_float(value, "shrinkage") for value in self.shrinkage_grid)
        if grid != tuple(sorted(grid)) or len(grid) != len(set(grid)):
            raise ValueError("shrinkage_grid must be unique and numerically sorted")
        if self.shrinkage_grid != grid:
            object.__setattr__(self, "shrinkage_grid", grid)
        _exact_positive_int(self.minimum_whole_study_folds, "minimum_whole_study_folds")
        _exact_positive_int(
            self.minimum_within_study_donor_folds,
            "minimum_within_study_donor_folds",
        )
        if type(self.hierarchy) is not HierarchySolverConfiguration:
            raise ValueError("hierarchy must be an exact HierarchySolverConfiguration")


DEFAULT_TRAINING_CONFIGURATION: Final = TrainingConfiguration()


@dataclass(frozen=True, slots=True)
class CandidateFoldEvaluation:
    """De-identified held-evidence score for one candidate and split."""

    fold_id: str
    kind: ValidationKind
    shrinkage: float
    state: FoldEvaluationState
    abstention_reason: FoldAbstentionReason | None
    eligible_lineage_count: int
    selected_feature_count: int
    evaluated_held_record_count: int
    mean_per_count_nll: float | None

    def __post_init__(self) -> None:
        if type(self.fold_id) is not str or not self.fold_id:
            raise ValueError("fold_id must be a nonempty string")
        if self.kind not in ("whole_study", "within_study_donor"):
            raise ValueError("candidate fold kind is unsupported")
        _positive_float(self.shrinkage, "shrinkage")
        for name, value in (
            ("eligible_lineage_count", self.eligible_lineage_count),
            ("selected_feature_count", self.selected_feature_count),
            ("evaluated_held_record_count", self.evaluated_held_record_count),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be an exact nonnegative integer")
        if self.state == "evaluated":
            if self.abstention_reason is not None:
                raise ValueError("evaluated fold cannot contain an abstention reason")
            if self.eligible_lineage_count < 2 or self.selected_feature_count < 2:
                raise ValueError("evaluated fold has insufficient modeled dimensions")
            if self.evaluated_held_record_count < self.eligible_lineage_count:
                raise ValueError("evaluated fold has too few held records")
            if self.mean_per_count_nll is None or not math.isfinite(self.mean_per_count_nll):
                raise ValueError("evaluated fold requires a finite mean held NLL")
        elif self.state == "abstained":
            if self.abstention_reason is None or self.mean_per_count_nll is not None:
                raise ValueError("abstained fold must carry one reason and no score")
        else:
            raise ValueError("candidate fold state is unsupported")


def _required_fold_score(value: CandidateFoldEvaluation) -> float:
    if value.mean_per_count_nll is None:
        raise ValueError("evaluated fold score is unexpectedly absent")
    return value.mean_per_count_nll


@dataclass(frozen=True, slots=True)
class ShrinkageCandidateEvaluation:
    """Equal-family validation score for one hierarchy shrinkage value."""

    shrinkage: float
    folds: tuple[CandidateFoldEvaluation, ...]
    whole_study_fold_count: int
    within_study_donor_fold_count: int
    minimum_whole_study_folds: int
    minimum_within_study_donor_folds: int
    whole_study_mean_nll: float | None
    within_study_donor_mean_nll: float | None
    selection_score: float | None
    selectable: bool

    def __post_init__(self) -> None:
        _positive_float(self.shrinkage, "shrinkage")
        if type(self.folds) is not tuple or not self.folds:
            raise ValueError("candidate evaluation requires fold evidence")
        if any(type(item) is not CandidateFoldEvaluation for item in self.folds):
            raise ValueError("folds must contain exact CandidateFoldEvaluation values")
        if any(item.shrinkage != self.shrinkage for item in self.folds):
            raise ValueError("fold candidate shrinkage values do not reconcile")
        whole = tuple(
            _required_fold_score(item)
            for item in self.folds
            if item.state == "evaluated" and item.kind == "whole_study"
        )
        within = tuple(
            _required_fold_score(item)
            for item in self.folds
            if item.state == "evaluated" and item.kind == "within_study_donor"
        )
        if self.whole_study_fold_count != len(whole):
            raise ValueError("whole-study fold count does not reconcile")
        if self.within_study_donor_fold_count != len(within):
            raise ValueError("within-study donor fold count does not reconcile")
        minimum_whole = _exact_positive_int(
            self.minimum_whole_study_folds,
            "minimum_whole_study_folds",
        )
        minimum_within = _exact_positive_int(
            self.minimum_within_study_donor_folds,
            "minimum_within_study_donor_folds",
        )
        expected_whole = None if not whole else math.fsum(whole) / len(whole)
        expected_within = None if not within else math.fsum(within) / len(within)
        if not _optional_close(self.whole_study_mean_nll, expected_whole):
            raise ValueError("whole-study family score does not reconcile")
        if not _optional_close(self.within_study_donor_mean_nll, expected_within):
            raise ValueError("within-study donor family score does not reconcile")
        enough = len(whole) >= minimum_whole and len(within) >= minimum_within
        expected_score = (
            None
            if not enough or expected_whole is None or expected_within is None
            else math.fsum((expected_whole, expected_within)) / 2.0
        )
        if not _optional_close(self.selection_score, expected_score):
            raise ValueError("equal-family candidate score does not reconcile")
        if self.selectable is not (expected_score is not None):
            raise ValueError("candidate selectability does not reconcile with its score")


def _required_candidate_score(value: ShrinkageCandidateEvaluation) -> float:
    if value.selection_score is None:
        raise ValueError("selectable candidate score is unexpectedly absent")
    return value.selection_score


def _optional_close(observed: float | None, expected: float | None) -> bool:
    if observed is None or expected is None:
        return observed is expected
    return math.isfinite(observed) and math.isclose(
        observed, expected, rel_tol=1e-14, abs_tol=1e-14
    )


@dataclass(frozen=True, slots=True)
class CandidateLineageSummary:
    modeled_label: str
    usable_donor_count: int
    usable_study_count: int
    stable_gene_count: int
    concentration: float
    hierarchy_iterations: int
    hierarchy_kkt_residual: float

    def __post_init__(self) -> None:
        if type(self.modeled_label) is not str or not self.modeled_label:
            raise ValueError("modeled_label must be a nonempty string")
        _exact_positive_int(self.usable_donor_count, "usable_donor_count")
        _exact_positive_int(self.usable_study_count, "usable_study_count")
        if (
            _exact_positive_int(self.stable_gene_count, "stable_gene_count")
            < MIN_STABLE_GENES_PER_LINEAGE
        ):
            raise ValueError("candidate lineage has too few stable genes")
        _positive_float(self.concentration, "concentration")
        _exact_positive_int(self.hierarchy_iterations, "hierarchy_iterations")
        if not math.isfinite(self.hierarchy_kkt_residual) or self.hierarchy_kkt_residual < 0.0:
            raise ValueError("hierarchy_kkt_residual must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class DevelopmentCandidateModel:
    """In-memory numerical candidate; this is deliberately not an artifact contract."""

    fit_state: Literal["development_candidate_unadmitted"]
    feature_ids: tuple[str, ...]
    gene_symbols: tuple[str | None, ...]
    modeled_labels: tuple[str, ...]
    signature_matrix: FloatArray
    concentrations: FloatArray
    shrinkage: float
    production_artifact_permitted: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False

    def __post_init__(self) -> None:
        if self.fit_state != "development_candidate_unadmitted":
            raise ValueError("candidate fit state is invalid")
        if type(self.feature_ids) is not tuple or len(self.feature_ids) < 2:
            raise ValueError("candidate requires at least two selected features")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ValueError("candidate feature identifiers must be unique")
        if type(self.gene_symbols) is not tuple or len(self.gene_symbols) != len(self.feature_ids):
            raise ValueError("candidate gene symbols must align with features")
        if (
            type(self.modeled_labels) is not tuple
            or len(self.modeled_labels) < 2
            or self.modeled_labels != tuple(sorted(self.modeled_labels))
            or len(self.modeled_labels) != len(set(self.modeled_labels))
        ):
            raise ValueError("candidate modeled labels must be unique, sorted, and plural")
        signatures = np.array(self.signature_matrix, dtype=np.float64, copy=True, order="C")
        concentrations = np.array(self.concentrations, dtype=np.float64, copy=True)
        if signatures.shape != (len(self.modeled_labels), len(self.feature_ids)):
            raise ValueError("candidate signature dimensions are inconsistent")
        if concentrations.shape != (len(self.modeled_labels),):
            raise ValueError("candidate concentrations do not align with modeled labels")
        if (
            not bool(np.all(np.isfinite(signatures)))
            or not bool(np.all(signatures > 0.0))
            or not bool(np.all(np.isfinite(concentrations)))
            or not bool(np.all(concentrations > 0.0))
        ):
            raise ValueError("candidate numerical parameters must be finite and positive")
        if any(
            not math.isclose(math.fsum(float(value) for value in row), 1.0, abs_tol=1e-10)
            for row in signatures
        ):
            raise ValueError("every candidate signature must sum to one")
        signatures.flags.writeable = False
        concentrations.flags.writeable = False
        object.__setattr__(self, "signature_matrix", signatures)
        object.__setattr__(self, "concentrations", concentrations)
        _positive_float(self.shrinkage, "shrinkage")
        if (
            self.production_artifact_permitted is not False
            or self.runtime_mount_permitted is not False
        ):
            raise ValueError("development candidate cannot permit artifact or runtime publication")


@dataclass(frozen=True, slots=True)
class DevelopmentTrainingSummary:
    """Retainable summary with source provenance but no donor identifiers/hashes."""

    fit_state: Literal["development_candidate_unadmitted"]
    source_file_sha256: str
    source_bytes: int
    taxonomy_digest: str
    extraction_recipe_digest: str
    feature_order_digest: str
    selected_shrinkage: float
    candidate_evaluations: tuple[ShrinkageCandidateEvaluation, ...]
    selected_feature_count: int
    lineage_summaries: tuple[CandidateLineageSummary, ...]
    production_artifact_permitted: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False

    def __post_init__(self) -> None:
        if self.fit_state != "development_candidate_unadmitted":
            raise ValueError("training summary fit state is invalid")
        for name, value in (
            ("source_file_sha256", self.source_file_sha256),
            ("taxonomy_digest", self.taxonomy_digest),
            ("extraction_recipe_digest", self.extraction_recipe_digest),
            ("feature_order_digest", self.feature_order_digest),
        ):
            if type(value) is not str or not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"{name} must be a canonical sha256 digest")
        _exact_positive_int(self.source_bytes, "source_bytes")
        _positive_float(self.selected_shrinkage, "selected_shrinkage")
        if type(self.candidate_evaluations) is not tuple or not self.candidate_evaluations:
            raise ValueError("training summary requires candidate evaluations")
        if not any(
            item.selectable and item.shrinkage == self.selected_shrinkage
            for item in self.candidate_evaluations
        ):
            raise ValueError("selected shrinkage has no selectable evaluation")
        if _exact_positive_int(self.selected_feature_count, "selected_feature_count") < 2:
            raise ValueError("training summary requires at least two selected features")
        if type(self.lineage_summaries) is not tuple or len(self.lineage_summaries) < 2:
            raise ValueError("training summary requires at least two lineage fits")
        labels = tuple(item.modeled_label for item in self.lineage_summaries)
        if labels != tuple(sorted(labels)) or len(labels) != len(set(labels)):
            raise ValueError("training lineage summaries must be unique and sorted")
        if (
            self.production_artifact_permitted is not False
            or self.runtime_mount_permitted is not False
        ):
            raise ValueError("development summary cannot permit artifact or runtime publication")


@dataclass(frozen=True, slots=True)
class DevelopmentTrainingResult:
    """Transient candidate training state plus its de-identified summary."""

    split_plan: ValidationSplitPlan = field(repr=False)
    final_selection: StableGeneSelection = field(repr=False)
    lineage_fits: tuple[tuple[str, LineageHierarchyFit], ...] = field(repr=False)
    model: DevelopmentCandidateModel
    summary: DevelopmentTrainingSummary

    def __post_init__(self) -> None:
        if type(self.split_plan) is not ValidationSplitPlan:
            raise ValueError("split_plan must be an exact ValidationSplitPlan")
        if type(self.final_selection) is not StableGeneSelection:
            raise ValueError("final_selection must be an exact StableGeneSelection")
        if type(self.lineage_fits) is not tuple or len(self.lineage_fits) < 2:
            raise ValueError("lineage_fits must contain at least two fitted lineages")
        labels = tuple(label for label, _ in self.lineage_fits)
        if labels != self.model.modeled_labels:
            raise ValueError("lineage fits do not align with candidate model labels")
        if any(type(fit) is not LineageHierarchyFit for _, fit in self.lineage_fits):
            raise ValueError("lineage_fits contain an invalid fit")
        if self.summary.selected_shrinkage != self.model.shrinkage:
            raise ValueError("training summary and model shrinkage do not reconcile")
        if self.summary.selected_feature_count != len(self.model.feature_ids):
            raise ValueError("training summary and model feature counts do not reconcile")


@dataclass(frozen=True, slots=True)
class _PreparedFold:
    fold: TransientValidationFold
    feature_indices: tuple[int, ...]
    labels: tuple[str, ...]
    stable_gene_counts: tuple[tuple[str, int], ...]
    training_records: tuple[DonorLabelAggregate, ...]
    held_records: tuple[DonorLabelAggregate, ...]
    background: FloatArray


@dataclass(frozen=True, slots=True)
class _AbstainedFold:
    fold: TransientValidationFold
    reason: FoldAbstentionReason
    eligible_lineage_count: int = 0
    selected_feature_count: int = 0


def _selected_features(
    selection: StableGeneSelection,
    labels: tuple[str, ...],
) -> tuple[int, ...]:
    allowed = frozenset(labels)
    retained = {
        item.feature_id
        for group in selection.by_label
        if group.modeled_label in allowed
        for item in group.genes
    }
    return tuple(
        index
        for feature_id, index in zip(
            selection.union_feature_ids,
            selection.union_feature_indices,
            strict=True,
        )
        if feature_id in retained
    )


def _equal_label_study_background(
    records: tuple[DonorLabelAggregate, ...],
    labels: tuple[str, ...],
    feature_indices: tuple[int, ...],
) -> FloatArray:
    indices = np.asarray(feature_indices, dtype=np.int64)
    grouped: dict[tuple[str, str], list[DonorLabelAggregate]] = {}
    allowed_labels = frozenset(labels)
    for record in records:
        if record.modeled_label in allowed_labels:
            grouped.setdefault((record.modeled_label, record.study_key), []).append(record)
    label_profiles: list[FloatArray] = []
    for label in labels:
        study_profiles: list[FloatArray] = []
        studies = tuple(sorted(study for candidate, study in grouped if candidate == label))
        for study in studies:
            donor_profiles: list[FloatArray] = []
            for record in grouped[(label, study)]:
                counts = np.asarray(record.gene_counts[indices], dtype=np.float64)
                total = math.fsum(float(value) for value in counts)
                if total > 0.0:
                    donor_profiles.append(counts / total)
            if donor_profiles:
                study_profiles.append(np.mean(np.stack(donor_profiles), axis=0))
        if not study_profiles:
            raise GbmapInputError("one selected lineage has no positive training marker counts")
        label_profiles.append(np.mean(np.stack(study_profiles), axis=0))
    background = np.mean(np.stack(label_profiles), axis=0)
    background = np.maximum(background, SIMPLEX_FLOOR)
    background /= math.fsum(float(value) for value in background)
    result = np.ascontiguousarray(background, dtype=np.float64)
    result.flags.writeable = False
    return result


def _prepare_fold(
    reference: AggregateReference,
    plan: ValidationSplitPlan,
    fold: TransientValidationFold,
    cancellation: CancellationContext | None,
    selection_cache: _ReferenceSelectionCache | None = None,
) -> _PreparedFold | _AbstainedFold:
    checkpoint(cancellation)
    if not fold.evaluable:
        return _AbstainedFold(fold=fold, reason="split_not_evaluable")
    cache = (
        _build_reference_selection_cache(reference) if selection_cache is None else selection_cache
    )
    if type(cache) is not _ReferenceSelectionCache or cache.reference is not reference:
        raise GbmapInputError("fold cache does not bind the supplied aggregate reference")
    training_records, held_records = plan.partition_records(reference, fold.fold_id)
    eligible_record_ids = cache.normalized
    usable_training = tuple(
        record for record in training_records if id(record) in eligible_record_ids
    )
    usable_held = tuple(record for record in held_records if id(record) in eligible_record_ids)
    try:
        selection = _select_fold_stable_genes_precomputed(
            reference,
            cache,
            training_records=training_records,
        )
    except (GbmapInputError, ValueError):
        return _AbstainedFold(fold=fold, reason="stable_gene_selection_failed")
    stable_counts = selection.stable_gene_counts
    evaluable_from_split = {item.modeled_label for item in fold.label_support if item.evaluable}
    labels = tuple(
        label
        for label in sorted(evaluable_from_split)
        if stable_counts.get(label, 0) >= MIN_STABLE_GENES_PER_LINEAGE
    )
    if len(labels) < 2:
        return _AbstainedFold(
            fold=fold,
            reason="fewer_than_two_eligible_lineages",
            eligible_lineage_count=len(labels),
        )
    features = _selected_features(selection, labels)
    if len(features) < 2:
        return _AbstainedFold(
            fold=fold,
            reason="selected_marker_union_too_small",
            eligible_lineage_count=len(labels),
            selected_feature_count=len(features),
        )
    background = _equal_label_study_background(usable_training, labels, features)
    return _PreparedFold(
        fold=fold,
        feature_indices=features,
        labels=labels,
        stable_gene_counts=tuple((label, stable_counts[label]) for label in labels),
        training_records=usable_training,
        held_records=usable_held,
        background=background,
    )


def _fit_label(
    records: tuple[DonorLabelAggregate, ...],
    *,
    label: str,
    feature_indices: tuple[int, ...],
    background: FloatArray,
    shrinkage: float,
    configuration: HierarchySolverConfiguration,
    cancellation: CancellationContext | None,
) -> LineageHierarchyFit:
    selected = tuple(record for record in records if record.modeled_label == label)
    indices = np.asarray(feature_indices, dtype=np.int64)
    counts = np.stack(
        tuple(np.asarray(record.gene_counts[indices], dtype=np.int64) for record in selected)
    )
    studies = tuple(record.study_key for record in selected)
    return fit_lineage_hierarchy(
        counts,
        studies,
        background,
        shrinkage=shrinkage,
        configuration=configuration,
        cancellation=cancellation,
    )


def _abstained_evaluation(
    fold: TransientValidationFold,
    shrinkage: float,
    reason: FoldAbstentionReason,
    *,
    lineage_count: int = 0,
    feature_count: int = 0,
) -> CandidateFoldEvaluation:
    return CandidateFoldEvaluation(
        fold_id=fold.fold_id,
        kind=fold.kind,
        shrinkage=shrinkage,
        state="abstained",
        abstention_reason=reason,
        eligible_lineage_count=lineage_count,
        selected_feature_count=feature_count,
        evaluated_held_record_count=0,
        mean_per_count_nll=None,
    )


def _evaluate_prepared_fold(
    prepared: _PreparedFold | _AbstainedFold,
    shrinkage: float,
    configuration: HierarchySolverConfiguration,
    cancellation: CancellationContext | None,
) -> CandidateFoldEvaluation:
    checkpoint(cancellation)
    if isinstance(prepared, _AbstainedFold):
        return _abstained_evaluation(
            prepared.fold,
            shrinkage,
            prepared.reason,
            lineage_count=prepared.eligible_lineage_count,
            feature_count=prepared.selected_feature_count,
        )
    fits: dict[str, LineageHierarchyFit] = {}
    try:
        for label in prepared.labels:
            checkpoint(cancellation)
            fits[label] = _fit_label(
                prepared.training_records,
                label=label,
                feature_indices=prepared.feature_indices,
                background=prepared.background,
                shrinkage=shrinkage,
                configuration=configuration,
                cancellation=cancellation,
            )
    except (GbmapInputError, GbmapNumericalError, ValueError):
        return _abstained_evaluation(
            prepared.fold,
            shrinkage,
            "hierarchy_fit_failed",
            lineage_count=len(prepared.labels),
            feature_count=len(prepared.feature_indices),
        )
    if any(not fit.converged or not verify_hierarchy_trace(fit) for fit in fits.values()):
        return _abstained_evaluation(
            prepared.fold,
            shrinkage,
            "hierarchy_did_not_converge",
            lineage_count=len(prepared.labels),
            feature_count=len(prepared.feature_indices),
        )

    indices = np.asarray(prepared.feature_indices, dtype=np.int64)
    label_scores: list[float] = []
    held_count = 0
    for label in prepared.labels:
        fit = fits[label]
        scores_by_study: dict[str, list[float]] = {}
        for record in prepared.held_records:
            if record.modeled_label != label:
                continue
            counts = np.asarray(record.gene_counts[indices], dtype=np.int64)
            if int(np.sum(counts, dtype=np.int64)) == 0:
                continue
            scores_by_study.setdefault(record.study_key, []).append(
                dirichlet_multinomial_per_count_nll(
                    counts,
                    fit.global_signature,
                    fit.concentration,
                )
            )
        if not scores_by_study:
            return _abstained_evaluation(
                prepared.fold,
                shrinkage,
                "no_positive_held_marker_counts",
                lineage_count=len(prepared.labels),
                feature_count=len(prepared.feature_indices),
            )
        held_count += sum(len(scores) for scores in scores_by_study.values())
        study_scores = tuple(
            math.fsum(scores_by_study[study]) / len(scores_by_study[study])
            for study in sorted(scores_by_study)
        )
        label_scores.append(math.fsum(study_scores) / len(study_scores))
    return CandidateFoldEvaluation(
        fold_id=prepared.fold.fold_id,
        kind=prepared.fold.kind,
        shrinkage=shrinkage,
        state="evaluated",
        abstention_reason=None,
        eligible_lineage_count=len(prepared.labels),
        selected_feature_count=len(prepared.feature_indices),
        evaluated_held_record_count=held_count,
        mean_per_count_nll=math.fsum(label_scores) / len(label_scores),
    )


def _candidate_evaluation(
    prepared_folds: tuple[_PreparedFold | _AbstainedFold, ...],
    shrinkage: float,
    configuration: TrainingConfiguration,
    cancellation: CancellationContext | None,
) -> ShrinkageCandidateEvaluation:
    folds = tuple(
        _evaluate_prepared_fold(
            prepared,
            shrinkage,
            configuration.hierarchy,
            cancellation,
        )
        for prepared in prepared_folds
    )
    whole = tuple(
        _required_fold_score(item)
        for item in folds
        if item.state == "evaluated" and item.kind == "whole_study"
    )
    within = tuple(
        _required_fold_score(item)
        for item in folds
        if item.state == "evaluated" and item.kind == "within_study_donor"
    )
    whole_mean = None if not whole else math.fsum(whole) / len(whole)
    within_mean = None if not within else math.fsum(within) / len(within)
    enough = (
        len(whole) >= configuration.minimum_whole_study_folds
        and len(within) >= configuration.minimum_within_study_donor_folds
    )
    score = (
        math.fsum((whole_mean, within_mean)) / 2.0
        if enough and whole_mean is not None and within_mean is not None
        else None
    )
    return ShrinkageCandidateEvaluation(
        shrinkage=shrinkage,
        folds=folds,
        whole_study_fold_count=len(whole),
        within_study_donor_fold_count=len(within),
        minimum_whole_study_folds=configuration.minimum_whole_study_folds,
        minimum_within_study_donor_folds=configuration.minimum_within_study_donor_folds,
        whole_study_mean_nll=whole_mean,
        within_study_donor_mean_nll=within_mean,
        selection_score=score,
        selectable=score is not None,
    )


def _final_fit(
    reference: AggregateReference,
    shrinkage: float,
    configuration: TrainingConfiguration,
    cancellation: CancellationContext | None,
    selection_cache: _ReferenceSelectionCache | None = None,
) -> tuple[
    StableGeneSelection,
    tuple[int, ...],
    tuple[str, ...],
    tuple[tuple[str, LineageHierarchyFit], ...],
]:
    checkpoint(cancellation)
    cache = (
        _build_reference_selection_cache(reference) if selection_cache is None else selection_cache
    )
    if type(cache) is not _ReferenceSelectionCache or cache.reference is not reference:
        raise GbmapInputError("final-fit cache does not bind the supplied aggregate reference")
    selection = _select_fold_stable_genes_precomputed(
        reference,
        cache,
        training_records=reference.records,
    )
    eligibility = lineage_eligibility(reference, selection.stable_gene_counts)
    labels = tuple(item.modeled_label for item in eligibility if item.eligible)
    if len(labels) < 2:
        raise GbmapInputError("final training has fewer than two eligible modeled lineages")
    features = _selected_features(selection, labels)
    if len(features) < 2:
        raise GbmapInputError("final training marker union has fewer than two features")
    usable = tuple(record for record in reference.records if id(record) in cache.normalized)
    background = _equal_label_study_background(usable, labels, features)
    fits: list[tuple[str, LineageHierarchyFit]] = []
    for label in labels:
        checkpoint(cancellation)
        fit = _fit_label(
            usable,
            label=label,
            feature_indices=features,
            background=background,
            shrinkage=shrinkage,
            configuration=configuration.hierarchy,
            cancellation=cancellation,
        )
        if not fit.converged or not verify_hierarchy_trace(fit):
            raise GbmapNumericalError("final lineage hierarchy did not converge")
        fits.append((label, fit))
    return selection, features, labels, tuple(fits)


def train_development_candidate(
    reference: AggregateReference,
    *,
    configuration: TrainingConfiguration = DEFAULT_TRAINING_CONFIGURATION,
    cancellation: CancellationContext | None = None,
) -> DevelopmentTrainingResult:
    """Fit and validate an in-memory candidate without authorizing publication."""

    checkpoint(cancellation)
    if type(reference) is not AggregateReference:
        raise GbmapInputError("reference must be an exact AggregateReference instance")
    if type(configuration) is not TrainingConfiguration:
        raise GbmapInputError("configuration must be an exact TrainingConfiguration")
    selection_cache = _build_reference_selection_cache(reference)
    plan = build_validation_split_plan(reference, cancellation=cancellation)
    prepared = tuple(
        _prepare_fold(
            reference,
            plan,
            fold,
            cancellation,
            selection_cache,
        )
        for fold in plan.folds
    )
    evaluations = tuple(
        _candidate_evaluation(prepared, shrinkage, configuration, cancellation)
        for shrinkage in configuration.shrinkage_grid
    )
    selectable = tuple(item for item in evaluations if item.selectable)
    if not selectable:
        raise GbmapInputError("no shrinkage candidate satisfies both validation-family gates")
    selected = min(
        selectable,
        key=lambda item: (_required_candidate_score(item), item.shrinkage),
    )
    selection, feature_indices, labels, fits = _final_fit(
        reference,
        selected.shrinkage,
        configuration,
        cancellation,
        selection_cache,
    )
    feature_ids = tuple(reference.feature_ids[index] for index in feature_indices)
    gene_symbols = tuple(reference.gene_symbols[index] for index in feature_indices)
    model = DevelopmentCandidateModel(
        fit_state="development_candidate_unadmitted",
        feature_ids=feature_ids,
        gene_symbols=gene_symbols,
        modeled_labels=labels,
        signature_matrix=np.stack(tuple(fit.global_signature for _, fit in fits)),
        concentrations=np.asarray(tuple(fit.concentration for _, fit in fits), dtype=np.float64),
        shrinkage=selected.shrinkage,
    )
    eligibility = {
        item.modeled_label: item
        for item in lineage_eligibility(reference, selection.stable_gene_counts)
    }
    lineage_summaries = tuple(
        CandidateLineageSummary(
            modeled_label=label,
            usable_donor_count=eligibility[label].usable_donor_count,
            usable_study_count=eligibility[label].usable_study_count,
            stable_gene_count=eligibility[label].stable_gene_count,
            concentration=fit.concentration,
            hierarchy_iterations=fit.iterations,
            hierarchy_kkt_residual=fit.kkt_residual,
        )
        for label, fit in fits
    )
    summary = DevelopmentTrainingSummary(
        fit_state="development_candidate_unadmitted",
        source_file_sha256=reference.source_file_sha256,
        source_bytes=reference.source_bytes,
        taxonomy_digest=reference.taxonomy_digest,
        extraction_recipe_digest=reference.extraction_recipe_digest,
        feature_order_digest=reference.feature_order_digest,
        selected_shrinkage=selected.shrinkage,
        candidate_evaluations=evaluations,
        selected_feature_count=len(feature_ids),
        lineage_summaries=lineage_summaries,
    )
    return DevelopmentTrainingResult(
        split_plan=plan,
        final_selection=selection,
        lineage_fits=fits,
        model=model,
        summary=summary,
    )


__all__ = [
    "DEFAULT_SHRINKAGE_GRID",
    "DEFAULT_TRAINING_CONFIGURATION",
    "MAX_SHRINKAGE_CANDIDATES",
    "MIN_EVALUABLE_WHOLE_STUDY_FOLDS",
    "MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS",
    "CandidateFoldEvaluation",
    "CandidateLineageSummary",
    "DevelopmentCandidateModel",
    "DevelopmentTrainingResult",
    "DevelopmentTrainingSummary",
    "FoldAbstentionReason",
    "FoldEvaluationState",
    "ShrinkageCandidateEvaluation",
    "TrainingConfiguration",
    "train_development_candidate",
]
