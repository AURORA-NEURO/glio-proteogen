"""Fold-local stable-gene selection for the unfitted GBmap candidate.

Every enrichment statistic is constructed exclusively from an explicitly
admitted training partition.  Same-donor other-lineage aggregates are the
preferred comparator.  When a training donor has no usable other-lineage
aggregate, the fallback is an equal-lineage background from other admitted
donors in the same training study.  No record outside the admitted partition
is consulted after partition validation.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real
from typing import Final

import numpy as np
import numpy.typing as npt

from .aggregate import (
    REFERENCE_EFFECTIVE_DEPTH,
    AggregateReference,
    DonorLabelAggregate,
    _largest_remainder_scale_prevalidated,
    donor_label_is_eligible,
)
from .errors import GbmapInputError, GbmapNumericalError

SELECTION_PSEUDOCOUNT: Final = 32.0
MIN_MEDIAN_LOG2_ENRICHMENT: Final = 0.75
MIN_DONOR_POSITIVE_FRACTION: Final = 0.70
MIN_STUDY_POSITIVE_MEDIAN_FRACTION: Final = 0.75
MIN_MEDIAN_DETECTION_FRACTION: Final = 0.10
MIN_LABEL_MARGIN: Final = 0.50
MAX_GENES_PER_LABEL: Final = 32
MAX_UNION_GENES: Final = 512
MAD_SCALE: Final = 1.4826

FloatVector = npt.NDArray[np.float64]
FloatMatrix = npt.NDArray[np.float64]


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GbmapInputError(f"{name} must be nonempty text without surrounding whitespace")
    return value


def _identifier_tuple(value: object, name: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise GbmapInputError(f"{name} must be a nonempty exact tuple")
    identifiers = tuple(_identifier(item, f"{name} item") for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise GbmapInputError(f"{name} must contain unique identifiers")
    return tuple(sorted(identifiers))


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise GbmapInputError(f"{name} must be a non-Boolean real value")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise GbmapInputError(f"{name} must be finite")
    return numeric


def _fraction(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if not 0.0 <= numeric <= 1.0:
        raise GbmapInputError(f"{name} must be between zero and one")
    return numeric


def stable_gene_passes_gates(
    *,
    median_log2_enrichment: object,
    donor_positive_fraction: object,
    study_positive_median_fraction: object,
    median_detection_fraction: object,
    label_margin: object,
) -> bool:
    """Apply the inclusive fixed stable-gene gates with strict numeric input."""

    median = _finite_real(median_log2_enrichment, "median_log2_enrichment")
    donor = _fraction(donor_positive_fraction, "donor_positive_fraction")
    study = _fraction(
        study_positive_median_fraction,
        "study_positive_median_fraction",
    )
    detection = _fraction(median_detection_fraction, "median_detection_fraction")
    margin = _finite_real(label_margin, "label_margin")
    return (
        median >= MIN_MEDIAN_LOG2_ENRICHMENT
        and donor >= MIN_DONOR_POSITIVE_FRACTION
        and study >= MIN_STUDY_POSITIVE_MEDIAN_FRACTION
        and detection >= MIN_MEDIAN_DETECTION_FRACTION
        and margin >= MIN_LABEL_MARGIN
    )


def stable_gene_score(
    *,
    median_log2_enrichment: object,
    donor_stability: object,
    study_stability: object,
    median_detection_fraction: object,
    mad_log2_enrichment: object,
) -> float:
    """Return the fixed stability/detection score used for deterministic ranking."""

    median = _finite_real(median_log2_enrichment, "median_log2_enrichment")
    donor = _fraction(donor_stability, "donor_stability")
    study = _fraction(study_stability, "study_stability")
    detection = _fraction(median_detection_fraction, "median_detection_fraction")
    mad = _finite_real(mad_log2_enrichment, "mad_log2_enrichment")
    if mad < 0.0:
        raise GbmapInputError("mad_log2_enrichment must be nonnegative")
    score = max(median, 0.0) * donor * study * math.sqrt(detection) / (1.0 + MAD_SCALE * mad)
    if not math.isfinite(score):
        raise GbmapNumericalError("stable-gene score is not finite")
    return score


@dataclass(frozen=True, slots=True)
class StableGeneEvidence:
    """One selected feature with all fixed gate and ranking diagnostics."""

    modeled_label: str
    feature_id: str
    feature_index: int
    gene_symbol: str | None
    median_log2_enrichment: float
    donor_positive_fraction: float
    study_positive_median_fraction: float
    median_detection_fraction: float
    mad_log2_enrichment: float
    label_margin: float
    score: float
    donor_count: int
    study_count: int

    def __post_init__(self) -> None:
        _identifier(self.modeled_label, "modeled_label")
        _identifier(self.feature_id, "feature_id")
        if type(self.feature_index) is not int or self.feature_index < 0:
            raise ValueError("feature_index must be an exact nonnegative integer")
        if self.gene_symbol is not None:
            _identifier(self.gene_symbol, "gene_symbol")
        if type(self.donor_count) is not int or self.donor_count < 1:
            raise ValueError("donor_count must be an exact positive integer")
        if type(self.study_count) is not int or self.study_count < 1:
            raise ValueError("study_count must be an exact positive integer")
        if not stable_gene_passes_gates(
            median_log2_enrichment=self.median_log2_enrichment,
            donor_positive_fraction=self.donor_positive_fraction,
            study_positive_median_fraction=self.study_positive_median_fraction,
            median_detection_fraction=self.median_detection_fraction,
            label_margin=self.label_margin,
        ):
            raise ValueError("selected stable-gene evidence does not satisfy all fixed gates")
        expected_score = stable_gene_score(
            median_log2_enrichment=self.median_log2_enrichment,
            donor_stability=self.donor_positive_fraction,
            study_stability=self.study_positive_median_fraction,
            median_detection_fraction=self.median_detection_fraction,
            mad_log2_enrichment=self.mad_log2_enrichment,
        )
        if not math.isclose(self.score, expected_score, rel_tol=1e-15, abs_tol=1e-15):
            raise ValueError("stable-gene score does not match its fixed formula")


@dataclass(frozen=True, slots=True)
class LabelStableGeneSelection:
    """Deterministically ranked stable features retained for one modeled label."""

    modeled_label: str
    passing_gene_count: int
    pre_union_selected_count: int
    genes: tuple[StableGeneEvidence, ...]

    def __post_init__(self) -> None:
        _identifier(self.modeled_label, "modeled_label")
        for name, value in (
            ("passing_gene_count", self.passing_gene_count),
            ("pre_union_selected_count", self.pre_union_selected_count),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be an exact nonnegative integer")
        if type(self.genes) is not tuple:
            raise ValueError("genes must be an exact tuple")
        if len(self.genes) > MAX_GENES_PER_LABEL:
            raise ValueError("one label cannot retain more than 32 stable genes")
        if self.pre_union_selected_count > min(self.passing_gene_count, MAX_GENES_PER_LABEL):
            raise ValueError("pre-union selection count is inconsistent with passing genes")
        if len(self.genes) > self.pre_union_selected_count:
            raise ValueError("union pruning cannot increase a label selection")
        if any(item.modeled_label != self.modeled_label for item in self.genes):
            raise ValueError("label selection contains evidence for another modeled label")
        feature_ids = tuple(item.feature_id for item in self.genes)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("label selection feature identifiers must be unique")
        expected = tuple(sorted(self.genes, key=lambda item: (-item.score, item.feature_id)))
        if self.genes != expected:
            raise ValueError("label selection must be score-ranked with exact feature-ID ties")


@dataclass(frozen=True, slots=True)
class StableGeneSelection:
    """One immutable fold-local selection receipt without held-record identities."""

    training_donor_keys: tuple[str, ...]
    training_study_keys: tuple[str, ...]
    usable_record_count: int
    by_label: tuple[LabelStableGeneSelection, ...]
    union_feature_ids: tuple[str, ...]
    union_feature_indices: tuple[int, ...]
    pseudocount: float = SELECTION_PSEUDOCOUNT
    effective_depth: int = REFERENCE_EFFECTIVE_DEPTH

    def __post_init__(self) -> None:
        donors = _identifier_tuple(self.training_donor_keys, "training_donor_keys")
        studies = _identifier_tuple(self.training_study_keys, "training_study_keys")
        if self.training_donor_keys != donors or self.training_study_keys != studies:
            raise ValueError("training donor and study keys must be sorted")
        if type(self.usable_record_count) is not int or self.usable_record_count < 1:
            raise ValueError("usable_record_count must be an exact positive integer")
        if type(self.by_label) is not tuple or len(self.by_label) < 2:
            raise ValueError("by_label must contain at least two label selections")
        labels = tuple(item.modeled_label for item in self.by_label)
        if labels != tuple(sorted(labels)) or len(labels) != len(set(labels)):
            raise ValueError("label selections must be unique and sorted")
        if (
            type(self.union_feature_ids) is not tuple
            or type(self.union_feature_indices) is not tuple
        ):
            raise ValueError("union feature identifiers and indices must be exact tuples")
        retained = tuple(
            sorted(
                (gene for item in self.by_label for gene in item.genes),
                key=lambda item: (-item.score, item.feature_id),
            )
        )
        if len(retained) > MAX_UNION_GENES:
            raise ValueError("stable-gene union exceeds 512 features")
        if len({item.feature_id for item in retained}) != len(retained):
            raise ValueError("stable-gene union feature identifiers must be unique")
        if self.union_feature_ids != tuple(item.feature_id for item in retained):
            raise ValueError("union feature identifiers must preserve deterministic ranking")
        if self.union_feature_indices != tuple(item.feature_index for item in retained):
            raise ValueError("union feature indices must align with ranked identifiers")
        if self.pseudocount != SELECTION_PSEUDOCOUNT:
            raise ValueError("selection pseudocount must equal 32")
        if self.effective_depth != REFERENCE_EFFECTIVE_DEPTH:
            raise ValueError("selection effective depth does not match the aggregate contract")

    @property
    def stable_gene_counts(self) -> dict[str, int]:
        return {item.modeled_label: len(item.genes) for item in self.by_label}


def _record_sort_key(record: DonorLabelAggregate) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        record.study_key,
        record.donor_key,
        record.modeled_label,
        record.source_labels,
    )


@dataclass(frozen=True, slots=True)
class _ReferenceSelectionCache:
    """Reference-owned record transforms reusable across leakage-safe folds."""

    reference: AggregateReference
    record_identities: frozenset[int]
    record_ranks: dict[int, int]
    normalized: dict[int, FloatVector]
    detections: dict[int, FloatVector]


@dataclass(frozen=True, slots=True)
class _FoldSelectionIndex:
    """One fold's admitted records and comparator groups only."""

    records: tuple[DonorLabelAggregate, ...]
    normalized: dict[int, FloatVector]
    detections: dict[int, FloatVector]
    by_label: dict[str, tuple[DonorLabelAggregate, ...]]
    by_donor: dict[str, tuple[DonorLabelAggregate, ...]]
    by_study: dict[str, tuple[DonorLabelAggregate, ...]]


def _build_reference_selection_cache(reference: AggregateReference) -> _ReferenceSelectionCache:
    """Precompute exact record-local transforms once for one immutable reference."""

    if type(reference) is not AggregateReference:
        raise GbmapInputError("reference must be an exact AggregateReference instance")
    normalized: dict[int, FloatVector] = {}
    detections: dict[int, FloatVector] = {}
    for record in reference.records:
        if not donor_label_is_eligible(record):
            continue
        scaled = _largest_remainder_scale_prevalidated(
            record.gene_counts,
            reference.feature_ids,
            total=record.total_umis,
            target_depth=REFERENCE_EFFECTIVE_DEPTH,
        )
        normalized_record = np.asarray(scaled, dtype=np.float64)
        normalized_record.flags.writeable = False
        detection = np.asarray(record.detected_cell_counts, dtype=np.float64) / float(
            record.cell_count
        )
        detection.flags.writeable = False
        normalized[id(record)] = normalized_record
        detections[id(record)] = detection
    return _ReferenceSelectionCache(
        reference=reference,
        record_identities=frozenset(id(record) for record in reference.records),
        record_ranks={id(record): rank for rank, record in enumerate(reference.records)},
        normalized=normalized,
        detections=detections,
    )


def _record_groups(
    records: tuple[DonorLabelAggregate, ...],
    key: Callable[[DonorLabelAggregate], str],
) -> dict[str, tuple[DonorLabelAggregate, ...]]:
    groups: dict[str, list[DonorLabelAggregate]] = defaultdict(list)
    for record in records:
        groups[key(record)].append(record)
    return {group_key: tuple(group) for group_key, group in groups.items()}


def _fold_selection_index(
    records: tuple[DonorLabelAggregate, ...],
    cache: _ReferenceSelectionCache,
) -> _FoldSelectionIndex:
    normalized = {id(record): cache.normalized[id(record)] for record in records}
    detections = {id(record): cache.detections[id(record)] for record in records}
    return _FoldSelectionIndex(
        records=records,
        normalized=normalized,
        detections=detections,
        by_label=_record_groups(records, lambda record: record.modeled_label),
        by_donor=_record_groups(records, lambda record: record.donor_key),
        by_study=_record_groups(records, lambda record: record.study_key),
    )


def _training_partition(
    reference: AggregateReference,
    *,
    training_donor_keys: tuple[str, ...] | None,
    training_study_keys: tuple[str, ...] | None,
    training_records: tuple[DonorLabelAggregate, ...] | None,
    cache: _ReferenceSelectionCache | None = None,
) -> tuple[
    tuple[DonorLabelAggregate, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    records_mode = training_records is not None
    keys_mode = training_donor_keys is not None or training_study_keys is not None
    keys_complete = training_donor_keys is not None and training_study_keys is not None
    if (records_mode and keys_mode) or (not records_mode and not keys_complete):
        raise GbmapInputError(
            "provide either training_records or both training donor/study key tuples"
        )

    if records_mode:
        if type(training_records) is not tuple or not training_records:
            raise GbmapInputError("training_records must be a nonempty exact tuple")
        reference_identities = (
            cache.record_identities
            if cache is not None
            else frozenset(id(record) for record in reference.records)
        )
        seen: set[int] = set()
        admitted: list[DonorLabelAggregate] = []
        for record in training_records:
            if type(record) is not DonorLabelAggregate:
                raise GbmapInputError(
                    "training_records must contain exact DonorLabelAggregate instances"
                )
            identity = id(record)
            if identity not in reference_identities:
                raise GbmapInputError("training_records contains a record outside the reference")
            if identity in seen:
                raise GbmapInputError("training_records cannot contain duplicate records")
            seen.add(identity)
            admitted.append(record)
        if cache is None:
            records = tuple(sorted(admitted, key=_record_sort_key))
        else:
            ranks = cache.record_ranks
            records = tuple(sorted(admitted, key=lambda record: ranks[id(record)]))
        donors = tuple(sorted({record.donor_key for record in records}))
        studies = tuple(sorted({record.study_key for record in records}))
        return records, donors, studies

    donors = _identifier_tuple(training_donor_keys, "training_donor_keys")
    studies = _identifier_tuple(training_study_keys, "training_study_keys")
    donor_studies = {record.donor_key: record.study_key for record in reference.records}
    unknown_donors = set(donors) - set(donor_studies)
    if unknown_donors:
        raise GbmapInputError("training_donor_keys contains a donor outside the reference")
    known_studies = {record.study_key for record in reference.records}
    if set(studies) - known_studies:
        raise GbmapInputError("training_study_keys contains a study outside the reference")
    selected_studies = {donor_studies[donor] for donor in donors}
    if selected_studies != set(studies):
        raise GbmapInputError(
            "training_study_keys must exactly match the studies of the admitted donors"
        )
    donor_set = set(donors)
    records = tuple(record for record in reference.records if record.donor_key in donor_set)
    return records, donors, studies


def _mean_vectors(vectors: tuple[FloatVector, ...]) -> FloatVector:
    if not vectors:
        raise GbmapInputError("equal-label background cannot be empty")
    result = np.zeros(vectors[0].shape, dtype=np.float64)
    for vector in vectors:
        result += vector
    result /= float(len(vectors))
    return result


def _equal_label_background(
    records: tuple[DonorLabelAggregate, ...],
    normalized: dict[int, FloatVector],
) -> FloatVector:
    by_label: dict[str, list[FloatVector]] = defaultdict(list)
    for record in records:
        by_label[record.modeled_label].append(normalized[id(record)])
    centroids = tuple(_mean_vectors(tuple(by_label[label])) for label in sorted(by_label))
    return _mean_vectors(centroids)


def _training_background(
    target: DonorLabelAggregate,
    index: _FoldSelectionIndex,
) -> FloatVector:
    same_donor = tuple(
        record
        for record in index.by_donor[target.donor_key]
        if record.modeled_label != target.modeled_label
    )
    if same_donor:
        return _equal_label_background(same_donor, index.normalized)
    study_fallback = tuple(
        record
        for record in index.by_study[target.study_key]
        if record.donor_key != target.donor_key and record.modeled_label != target.modeled_label
    )
    if study_fallback:
        return _equal_label_background(study_fallback, index.normalized)
    raise GbmapInputError(
        "training record has neither a same-donor comparator nor an other-donor "
        "same-study training fallback"
    )


@dataclass(frozen=True, slots=True)
class _LabelMetrics:
    records: tuple[DonorLabelAggregate, ...]
    median: FloatVector
    donor_stability: FloatVector
    study_stability: FloatVector
    detection: FloatVector
    mad: FloatVector


def _label_metrics(
    label: str,
    index: _FoldSelectionIndex,
) -> _LabelMetrics:
    targets = index.by_label[label]
    enrichments: list[FloatVector] = []
    detections: list[FloatVector] = []
    for target in targets:
        background = _training_background(target, index)
        target_counts = index.normalized[id(target)]
        with np.errstate(divide="raise", invalid="raise", over="raise"):
            try:
                enrichment = np.log2(
                    (target_counts + SELECTION_PSEUDOCOUNT) / (background + SELECTION_PSEUDOCOUNT)
                )
            except FloatingPointError as error:
                raise GbmapNumericalError(
                    "stable-gene enrichment left the finite domain"
                ) from error
        enrichments.append(np.asarray(enrichment, dtype=np.float64))
        detections.append(index.detections[id(target)])

    values = np.stack(enrichments, axis=0)
    detection_values = np.stack(detections, axis=0)
    median = np.asarray(np.median(values, axis=0), dtype=np.float64)
    donor_stability = np.asarray(np.mean(values > 0.0, axis=0), dtype=np.float64)
    detection = np.asarray(np.median(detection_values, axis=0), dtype=np.float64)
    mad = np.asarray(np.median(np.abs(values - median), axis=0), dtype=np.float64)

    studies = tuple(sorted({record.study_key for record in targets}))
    positive_study_count = np.zeros(median.shape, dtype=np.int64)
    for study in studies:
        indices = tuple(index for index, record in enumerate(targets) if record.study_key == study)
        study_median = np.median(values[np.asarray(indices, dtype=np.int64), :], axis=0)
        positive_study_count += study_median > 0.0
    study_stability = np.asarray(
        positive_study_count / float(len(studies)),
        dtype=np.float64,
    )
    for name, vector in (
        ("median enrichment", median),
        ("donor stability", donor_stability),
        ("study stability", study_stability),
        ("median detection", detection),
        ("MAD", mad),
    ):
        if not bool(np.all(np.isfinite(vector))):
            raise GbmapNumericalError(f"{name} contains a non-finite value")
    return _LabelMetrics(
        records=targets,
        median=median,
        donor_stability=donor_stability,
        study_stability=study_stability,
        detection=detection,
        mad=mad,
    )


def _candidate_genes(
    reference: AggregateReference,
    label: str,
    metrics: _LabelMetrics,
    other_label_maximum: FloatVector,
) -> tuple[StableGeneEvidence, ...]:
    candidates: list[StableGeneEvidence] = []
    margin = metrics.median - other_label_maximum
    donor_count = len(metrics.records)
    study_count = len({record.study_key for record in metrics.records})
    for index, feature_id in enumerate(reference.feature_ids):
        median = float(metrics.median[index])
        donor_stability = float(metrics.donor_stability[index])
        study_stability = float(metrics.study_stability[index])
        detection = float(metrics.detection[index])
        label_margin = float(margin[index])
        if median <= float(other_label_maximum[index]):
            continue
        if not stable_gene_passes_gates(
            median_log2_enrichment=median,
            donor_positive_fraction=donor_stability,
            study_positive_median_fraction=study_stability,
            median_detection_fraction=detection,
            label_margin=label_margin,
        ):
            continue
        mad = float(metrics.mad[index])
        score = stable_gene_score(
            median_log2_enrichment=median,
            donor_stability=donor_stability,
            study_stability=study_stability,
            median_detection_fraction=detection,
            mad_log2_enrichment=mad,
        )
        candidates.append(
            StableGeneEvidence(
                modeled_label=label,
                feature_id=feature_id,
                feature_index=index,
                gene_symbol=reference.gene_symbols[index],
                median_log2_enrichment=median,
                donor_positive_fraction=donor_stability,
                study_positive_median_fraction=study_stability,
                median_detection_fraction=detection,
                mad_log2_enrichment=mad,
                label_margin=label_margin,
                score=score,
                donor_count=donor_count,
                study_count=study_count,
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.feature_id)))


def _select_fold_stable_genes_precomputed(
    reference: AggregateReference,
    cache: _ReferenceSelectionCache,
    *,
    training_donor_keys: tuple[str, ...] | None = None,
    training_study_keys: tuple[str, ...] | None = None,
    training_records: tuple[DonorLabelAggregate, ...] | None = None,
) -> StableGeneSelection:
    """Select one fold using transforms bound to the exact immutable reference.

    ``training_records`` is an alternative to the donor/study key pair.  Every
    record in that tuple must be the exact object already owned by ``reference``;
    this prevents callers from injecting an unbound aggregate.  Key-based mode
    admits all reference records for the named donors and requires the study
    tuple to close exactly over those donors.
    """

    if type(reference) is not AggregateReference:
        raise GbmapInputError("reference must be an exact AggregateReference instance")
    if type(cache) is not _ReferenceSelectionCache or cache.reference is not reference:
        raise GbmapInputError("selection cache does not bind the supplied aggregate reference")
    partition, donors, studies = _training_partition(
        reference,
        training_donor_keys=training_donor_keys,
        training_study_keys=training_study_keys,
        training_records=training_records,
        cache=cache,
    )
    usable = tuple(record for record in partition if donor_label_is_eligible(record))
    if not usable:
        raise GbmapInputError("training partition contains no eligible aggregate records")
    usable_studies = {record.study_key for record in usable}
    if usable_studies != set(studies):
        raise GbmapInputError("every training study must contribute an eligible aggregate record")
    labels = tuple(sorted({record.modeled_label for record in usable}))
    if len(labels) < 2:
        raise GbmapInputError("stable-gene selection requires at least two modeled labels")

    index = _fold_selection_index(usable, cache)
    metrics = {label: _label_metrics(label, index) for label in labels}
    median_matrix = np.stack(tuple(metrics[label].median for label in labels), axis=0)
    candidates: dict[str, tuple[StableGeneEvidence, ...]] = {}
    for label_index, label in enumerate(labels):
        other_indices = tuple(index for index in range(len(labels)) if index != label_index)
        other_maximum = np.max(
            median_matrix[np.asarray(other_indices, dtype=np.int64), :],
            axis=0,
        )
        candidates[label] = _candidate_genes(
            reference,
            label,
            metrics[label],
            np.asarray(other_maximum, dtype=np.float64),
        )

    pre_union = {label: candidates[label][:MAX_GENES_PER_LABEL] for label in labels}
    globally_ranked = tuple(
        sorted(
            (gene for label in labels for gene in pre_union[label]),
            key=lambda item: (-item.score, item.feature_id),
        )[:MAX_UNION_GENES]
    )
    keep = {(item.modeled_label, item.feature_id) for item in globally_ranked}
    by_label = tuple(
        LabelStableGeneSelection(
            modeled_label=label,
            passing_gene_count=len(candidates[label]),
            pre_union_selected_count=len(pre_union[label]),
            genes=tuple(
                item for item in pre_union[label] if (item.modeled_label, item.feature_id) in keep
            ),
        )
        for label in labels
    )
    retained = tuple(
        sorted(
            (gene for selection in by_label for gene in selection.genes),
            key=lambda item: (-item.score, item.feature_id),
        )
    )
    return StableGeneSelection(
        training_donor_keys=donors,
        training_study_keys=studies,
        usable_record_count=len(usable),
        by_label=by_label,
        union_feature_ids=tuple(item.feature_id for item in retained),
        union_feature_indices=tuple(item.feature_index for item in retained),
    )


def select_fold_stable_genes(
    reference: AggregateReference,
    *,
    training_donor_keys: tuple[str, ...] | None = None,
    training_study_keys: tuple[str, ...] | None = None,
    training_records: tuple[DonorLabelAggregate, ...] | None = None,
) -> StableGeneSelection:
    """Select stable genes from one explicit training fold without held leakage.

    Standalone callers receive the same strict boundary and construct one
    bounded reference cache for this call. The offline trainer reuses that
    exact-reference cache across folds through the private preparation path.
    """

    cache = _build_reference_selection_cache(reference)
    return _select_fold_stable_genes_precomputed(
        reference,
        cache,
        training_donor_keys=training_donor_keys,
        training_study_keys=training_study_keys,
        training_records=training_records,
    )


__all__ = [
    "MAD_SCALE",
    "MAX_GENES_PER_LABEL",
    "MAX_UNION_GENES",
    "MIN_DONOR_POSITIVE_FRACTION",
    "MIN_LABEL_MARGIN",
    "MIN_MEDIAN_DETECTION_FRACTION",
    "MIN_MEDIAN_LOG2_ENRICHMENT",
    "MIN_STUDY_POSITIVE_MEDIAN_FRACTION",
    "SELECTION_PSEUDOCOUNT",
    "LabelStableGeneSelection",
    "StableGeneEvidence",
    "StableGeneSelection",
    "select_fold_stable_genes",
    "stable_gene_passes_gates",
    "stable_gene_score",
]
