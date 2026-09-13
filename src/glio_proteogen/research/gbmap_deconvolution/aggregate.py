"""Strict aggregate boundary for the unfitted GBmap composition candidate.

The fitting source is reduced to donor-by-lineage count aggregates before any
scientific estimator sees it.  Donor and study keys in these objects are
transient fitting identifiers: no fitted artifact may serialize them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

import numpy as np
import numpy.typing as npt

from .canonical import (
    aggregate_content_digest as _aggregate_content_digest,
)
from .canonical import feature_order_digest as _feature_order_digest

REFERENCE_EFFECTIVE_DEPTH: Final = 20_000
MIN_CELLS_PER_DONOR_LABEL: Final = 20
MIN_UMIS_PER_DONOR_LABEL: Final = 20_000
MIN_DONORS_PER_LINEAGE: Final = 8
MIN_STUDIES_PER_LINEAGE: Final = 3
MIN_STABLE_GENES_PER_LINEAGE: Final = 12

_DIGEST_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")

Int32Vector = npt.NDArray[np.int32]
Int64Vector = npt.NDArray[np.int64]


def _exact_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be an exact positive integer")
    return value


def _exact_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be an exact nonnegative integer")
    return value


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty text without surrounding whitespace")
    if len(value) > 256:
        raise ValueError(f"{name} exceeds the 256-character aggregate boundary")
    return value


def _digest(value: object, name: str) -> str:
    if type(value) is not str or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a namespaced SHA-256 digest")
    return value


def _count_vector(value: object, name: str) -> Int64Vector:
    """Validate and defensively freeze one exact signed-int64 count vector."""

    if type(value) is not np.ndarray:
        raise ValueError(f"{name} must be an exact NumPy ndarray")
    generic_array = cast("npt.NDArray[np.generic]", value)
    if generic_array.dtype != np.dtype(np.int64):
        raise ValueError(f"{name} must use exact int64 elements (boolean/float coercion forbidden)")
    array = cast("Int64Vector", generic_array)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a nonempty one-dimensional vector")
    if bool(np.any(array < 0)):
        raise ValueError(f"{name} cannot contain negative counts")
    frozen = np.array(array, dtype=np.int64, order="C", copy=True)
    frozen.flags.writeable = False
    return frozen


def _detection_vector(value: object, name: str) -> Int32Vector:
    """Validate and defensively freeze one exact signed-int32 detection vector."""

    if type(value) is not np.ndarray:
        raise ValueError(f"{name} must be an exact NumPy ndarray")
    generic_array = cast("npt.NDArray[np.generic]", value)
    if generic_array.dtype != np.dtype(np.int32):
        raise ValueError(f"{name} must use exact int32 elements (boolean/float coercion forbidden)")
    array = cast("Int32Vector", generic_array)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a nonempty one-dimensional vector")
    if bool(np.any(array < 0)):
        raise ValueError(f"{name} cannot contain negative counts")
    frozen = np.array(array, dtype=np.int32, order="C", copy=True)
    frozen.flags.writeable = False
    return frozen


def _python_sum(values: Int64Vector) -> int:
    """Sum through Python integers so an int64 accumulator cannot wrap."""

    return sum((int(value) for value in values), start=0)


@dataclass(frozen=True, slots=True)
class DonorLabelAggregate:
    """One transient donor-by-modeled-lineage raw-count aggregate."""

    donor_key: str
    study_key: str
    modeled_label: str
    source_labels: tuple[str, ...]
    cell_count: int
    gene_counts: Int64Vector
    detected_cell_counts: Int32Vector
    total_umis: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "donor_key", _identifier(self.donor_key, "donor_key"))
        object.__setattr__(self, "study_key", _identifier(self.study_key, "study_key"))
        object.__setattr__(
            self,
            "modeled_label",
            _identifier(self.modeled_label, "modeled_label"),
        )
        if type(self.source_labels) is not tuple or not self.source_labels:
            raise ValueError("source_labels must be a nonempty tuple")
        source_labels = tuple(
            sorted(_identifier(value, "source_labels item") for value in self.source_labels)
        )
        if len(source_labels) != len(set(source_labels)):
            raise ValueError("source_labels must be unique")
        object.__setattr__(self, "source_labels", source_labels)

        cell_count = _exact_positive_int(self.cell_count, "cell_count")
        total_umis = _exact_nonnegative_int(self.total_umis, "total_umis")
        counts = _count_vector(self.gene_counts, "gene_counts")
        detected = _detection_vector(self.detected_cell_counts, "detected_cell_counts")
        if counts.shape != detected.shape:
            raise ValueError("gene_counts and detected_cell_counts must have identical shapes")
        if bool(np.any(detected > cell_count)):
            raise ValueError("detected_cell_counts cannot exceed cell_count")
        if bool(np.any(detected > counts)):
            raise ValueError("each detected cell must contribute at least one gene count")
        if _python_sum(counts) != total_umis:
            raise ValueError("gene_counts do not reconcile to total_umis")

        object.__setattr__(self, "cell_count", cell_count)
        object.__setattr__(self, "total_umis", total_umis)
        object.__setattr__(self, "gene_counts", counts)
        object.__setattr__(self, "detected_cell_counts", detected)

    @property
    def eligible_for_reference(self) -> bool:
        return donor_label_is_eligible(self)


@dataclass(frozen=True, slots=True)
class AggregateReference:
    """Canonical, immutable aggregate input to the future offline fitter."""

    feature_ids: tuple[str, ...]
    gene_symbols: tuple[str | None, ...]
    records: tuple[DonorLabelAggregate, ...]
    source_file_sha256: str
    source_bytes: int
    taxonomy_digest: str
    extraction_recipe_digest: str
    _feature_order_digest_cache: str = field(init=False, repr=False, compare=False)
    _aggregate_content_digest_cache: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.feature_ids) is not tuple or not self.feature_ids:
            raise ValueError("feature_ids must be a nonempty tuple")
        feature_ids = tuple(_identifier(value, "feature_id") for value in self.feature_ids)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature_ids must be unique")
        if type(self.gene_symbols) is not tuple or len(self.gene_symbols) != len(feature_ids):
            raise ValueError("gene_symbols must be a tuple aligned with feature_ids")
        gene_symbols = [
            None if value is None else _identifier(value, "gene_symbol")
            for value in self.gene_symbols
        ]

        if type(self.records) is not tuple or not self.records:
            raise ValueError("records must be a nonempty tuple")
        for record in self.records:
            if type(record) is not DonorLabelAggregate:
                raise ValueError("records must contain exact DonorLabelAggregate instances")
            if record.gene_counts.shape != (len(feature_ids),):
                raise ValueError("every record count vector must align with feature_ids")

        records = tuple(
            sorted(
                self.records,
                key=lambda item: (
                    item.study_key,
                    item.donor_key,
                    item.modeled_label,
                    item.source_labels,
                ),
            )
        )
        donor_label_pairs: set[tuple[str, str]] = set()
        donor_studies: dict[str, str] = {}
        for record in records:
            pair = (record.donor_key, record.modeled_label)
            if pair in donor_label_pairs:
                raise ValueError("donor and modeled-label records must be unique")
            donor_label_pairs.add(pair)
            prior_study = donor_studies.setdefault(record.donor_key, record.study_key)
            if prior_study != record.study_key:
                raise ValueError("one donor cannot belong to more than one study")

        object.__setattr__(self, "feature_ids", feature_ids)
        object.__setattr__(self, "gene_symbols", tuple(gene_symbols))
        object.__setattr__(self, "records", records)
        object.__setattr__(
            self,
            "source_file_sha256",
            _digest(self.source_file_sha256, "source_file_sha256"),
        )
        object.__setattr__(
            self, "source_bytes", _exact_positive_int(self.source_bytes, "source_bytes")
        )
        object.__setattr__(
            self,
            "taxonomy_digest",
            _digest(self.taxonomy_digest, "taxonomy_digest"),
        )
        object.__setattr__(
            self,
            "extraction_recipe_digest",
            _digest(self.extraction_recipe_digest, "extraction_recipe_digest"),
        )
        object.__setattr__(
            self,
            "_feature_order_digest_cache",
            _feature_order_digest(feature_ids, tuple(gene_symbols)),
        )
        object.__setattr__(
            self,
            "_aggregate_content_digest_cache",
            _aggregate_content_digest(self),
        )

    @property
    def feature_order_digest(self) -> str:
        return self._feature_order_digest_cache

    @property
    def aggregate_content_digest(self) -> str:
        return self._aggregate_content_digest_cache

    @property
    def modeled_labels(self) -> tuple[str, ...]:
        return tuple(sorted({record.modeled_label for record in self.records}))

    @property
    def donor_count(self) -> int:
        return len({record.donor_key for record in self.records})

    @property
    def study_count(self) -> int:
        return len({record.study_key for record in self.records})


@dataclass(frozen=True, slots=True)
class LineageEligibility:
    modeled_label: str
    eligible: bool
    usable_donor_count: int
    usable_study_count: int
    stable_gene_count: int
    reasons: tuple[str, ...]


def donor_label_is_eligible(record: DonorLabelAggregate) -> bool:
    """Return whether one aggregate satisfies the fixed fitting floor."""

    return (
        record.cell_count >= MIN_CELLS_PER_DONOR_LABEL
        and record.total_umis >= MIN_UMIS_PER_DONOR_LABEL
    )


def lineage_eligibility(
    reference: AggregateReference,
    stable_gene_counts: Mapping[str, int],
) -> tuple[LineageEligibility, ...]:
    """Evaluate the fixed donor/study/stable-gene admission floor per lineage."""

    labels = reference.modeled_labels
    if set(stable_gene_counts) - set(labels):
        raise ValueError("stable_gene_counts contains an unknown modeled lineage")
    validated_stable: dict[str, int] = {}
    for label in labels:
        count = _exact_nonnegative_int(stable_gene_counts.get(label, 0), "stable gene count")
        if count > len(reference.feature_ids):
            raise ValueError("stable gene count cannot exceed the reference feature count")
        validated_stable[label] = count

    results: list[LineageEligibility] = []
    for label in labels:
        usable = tuple(
            record
            for record in reference.records
            if record.modeled_label == label and donor_label_is_eligible(record)
        )
        donors = {record.donor_key for record in usable}
        studies = {record.study_key for record in usable}
        stable = validated_stable[label]
        reasons: list[str] = []
        if len(donors) < MIN_DONORS_PER_LINEAGE:
            reasons.append("insufficient_usable_donors")
        if len(studies) < MIN_STUDIES_PER_LINEAGE:
            reasons.append("insufficient_usable_studies")
        if stable < MIN_STABLE_GENES_PER_LINEAGE:
            reasons.append("insufficient_stable_genes")
        results.append(
            LineageEligibility(
                modeled_label=label,
                eligible=not reasons,
                usable_donor_count=len(donors),
                usable_study_count=len(studies),
                stable_gene_count=stable,
                reasons=tuple(reasons),
            )
        )
    return tuple(results)


def largest_remainder_scale(
    counts: Int64Vector,
    feature_ids: Sequence[str],
    *,
    target_depth: int = REFERENCE_EFFECTIVE_DEPTH,
) -> Int64Vector:
    """Downscale integer counts exactly, resolving equal remainders by feature ID."""

    validated = _count_vector(counts, "counts")
    if len(feature_ids) != len(validated):
        raise ValueError("feature_ids must align with counts")
    identifiers = tuple(_identifier(value, "feature_id") for value in feature_ids)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("feature_ids must be unique")
    depth = _exact_positive_int(target_depth, "target_depth")
    total = _python_sum(validated)
    if total == 0:
        raise ValueError("zero-total counts cannot be scaled")
    if total < depth:
        raise ValueError("largest-remainder scaling never upsamples counts")

    return _largest_remainder_scale_prevalidated(
        validated,
        identifiers,
        total=total,
        target_depth=depth,
    )


def _largest_remainder_scale_prevalidated(
    counts: Int64Vector,
    feature_ids: tuple[str, ...],
    *,
    total: int,
    target_depth: int,
) -> Int64Vector:
    """Scale one reference-owned vector after aggregate-boundary validation."""

    quotients: list[int] = []
    remainders: list[int] = []
    for value in counts:
        quotient, remainder = divmod(int(value) * target_depth, total)
        quotients.append(quotient)
        remainders.append(remainder)
    remaining = target_depth - sum(quotients)
    order = sorted(
        range(len(feature_ids)), key=lambda index: (-remainders[index], feature_ids[index])
    )
    for index in order[:remaining]:
        quotients[index] += 1

    result = np.asarray(quotients, dtype=np.int64)
    if _python_sum(result) != target_depth or bool(np.any(result < 0)):
        raise RuntimeError("largest-remainder scaling failed integer closure")
    result.flags.writeable = False
    return result


__all__ = [
    "MIN_CELLS_PER_DONOR_LABEL",
    "MIN_DONORS_PER_LINEAGE",
    "MIN_STABLE_GENES_PER_LINEAGE",
    "MIN_STUDIES_PER_LINEAGE",
    "MIN_UMIS_PER_DONOR_LABEL",
    "REFERENCE_EFFECTIVE_DEPTH",
    "AggregateReference",
    "DonorLabelAggregate",
    "Int32Vector",
    "Int64Vector",
    "LineageEligibility",
    "donor_label_is_eligible",
    "largest_remainder_scale",
    "lineage_eligibility",
]
