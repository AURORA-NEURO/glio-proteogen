"""Deterministic research quantification with explicit scale and LOQ policy.

The values in this module are matched-fragment signal, not calibrated abundance.
The policy is deliberately closed and replayable: callers cannot silently change
units, normalization, or below-LOQ handling without changing the result digest.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from statistics import median

from .protein import ProteinGroup


@dataclass(frozen=True, slots=True)
class PeptideQuant:
    sample_id: str
    peptide: str
    intensity: float
    missing: bool = False
    status: str = "quantified"


@dataclass(frozen=True, slots=True)
class QuantificationPolicy:
    """Closed research policy for units, normalization, and below-LOQ handling."""

    measurement_unit: str = "matched_ion_intensity_arbitrary"
    normalization_method: str = "sample_median_scaled_v1"
    missingness_policy: str = "zero_or_below_loq_is_missing_no_imputation_v1"
    limit_of_quantification: float = 0.0
    max_input_observations: int = 100_000

    def __post_init__(self) -> None:
        if self.measurement_unit != "matched_ion_intensity_arbitrary":
            raise ValueError("only arbitrary matched-ion intensity is supported")
        if self.normalization_method not in {"none_v1", "sample_median_scaled_v1"}:
            raise ValueError("normalization_method is not supported")
        if self.missingness_policy != "zero_or_below_loq_is_missing_no_imputation_v1":
            raise ValueError("missingness_policy is not supported")
        if (
            type(self.limit_of_quantification) not in (int, float)
            or not isfinite(self.limit_of_quantification)
            or self.limit_of_quantification < 0
        ):
            raise ValueError("limit_of_quantification must be finite and non-negative")
        if (
            type(self.max_input_observations) is not int
            or not 1 <= self.max_input_observations <= 1_000_000
        ):
            raise ValueError("max_input_observations must be between one and one million")

    def as_dict(self) -> dict[str, object]:
        return {
            "limit_of_quantification": float(self.limit_of_quantification),
            "measurement_unit": self.measurement_unit,
            "missingness_policy": self.missingness_policy,
            "normalization_method": self.normalization_method,
            "max_input_observations": self.max_input_observations,
        }


@dataclass(frozen=True, slots=True)
class QuantificationReceipt:
    """Replay-bound measurement and normalization receipt for peptide signal.

    Intensities are matched-fragment-ion signal in arbitrary instrument units.
    The receipt makes the otherwise easy-to-misread median scaling and zero-signal
    handling explicit; it is evidence about this computation, not abundance or
    concentration calibration.
    """

    sample_id: str
    version: str
    measurement_unit: str
    normalization_method: str
    missingness_policy: str
    input_observations: int
    unique_peptides: int
    observed_peptides: int
    missing_peptides: int
    duplicate_observations: int
    raw_total_signal: float
    raw_positive_median: float | None
    normalization_target: float | None
    normalized_total_signal: float
    scale_factor: float | None
    raw_peptide_signals: tuple[tuple[str, float, bool], ...]
    normalized_peptide_signals: tuple[tuple[str, float, bool], ...]
    raw_positive_mad: float | None = None
    raw_positive_iqr: float | None = None
    raw_robust_cv: float | None = None
    observation_digest: str = ""
    max_input_observations: int = 100_000
    positive_signal_fraction: float = 0.0
    signal_quality: str = "no_positive_signal"
    limit_of_quantification: float = 0.0
    below_loq_peptides: int = 0
    quantifiable_peptides: int = 0
    raw_peptide_statuses: tuple[tuple[str, str], ...] = ()
    normalized_peptide_statuses: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "duplicate_observations": self.duplicate_observations,
            "input_observations": self.input_observations,
            "measurement_unit": self.measurement_unit,
            "missing_peptides": self.missing_peptides,
            "missingness_policy": self.missingness_policy,
            "normalization_method": self.normalization_method,
            "normalization_target": self.normalization_target,
            "normalized_peptide_signals": [list(item) for item in self.normalized_peptide_signals],
            "normalized_total_signal": self.normalized_total_signal,
            "observed_peptides": self.observed_peptides,
            "raw_peptide_signals": [list(item) for item in self.raw_peptide_signals],
            "raw_positive_median": self.raw_positive_median,
            "raw_positive_mad": self.raw_positive_mad,
            "raw_positive_iqr": self.raw_positive_iqr,
            "raw_robust_cv": self.raw_robust_cv,
            "raw_total_signal": self.raw_total_signal,
            "sample_id": self.sample_id,
            "scale_factor": self.scale_factor,
            "observation_digest": self.observation_digest,
            "max_input_observations": self.max_input_observations,
            "positive_signal_fraction": self.positive_signal_fraction,
            "signal_quality": self.signal_quality,
            "unique_peptides": self.unique_peptides,
            "version": self.version,
        }
        # Historical default receipts remain stable; a non-default LOQ is fully
        # self-describing and therefore part of the replay projection.
        if self.limit_of_quantification > 0 or self.below_loq_peptides:
            payload.update(
                {
                    "below_loq_peptides": self.below_loq_peptides,
                    "limit_of_quantification": self.limit_of_quantification,
                    "normalized_peptide_statuses": [
                        list(item) for item in self.normalized_peptide_statuses
                    ],
                    "quantifiable_peptides": self.quantifiable_peptides,
                    "raw_peptide_statuses": [list(item) for item in self.raw_peptide_statuses],
                }
            )
        if self.normalization_method != "sample_median_scaled":
            payload["normalization_policy"] = self.normalization_method
        return payload


@dataclass(frozen=True, slots=True)
class PeptideQuantification:
    """Normalized peptide values plus the receipt that explains their scale."""

    values: tuple[PeptideQuant, ...]
    receipt: QuantificationReceipt


@dataclass(frozen=True, slots=True)
class ProteinGroupQuant:
    """Ambiguity-aware group signal with shared peptides excluded from the primary estimate."""

    group_accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]
    unique_signal: float
    shared_signal: float
    total_signal: float
    primary_intensity: float | None
    status: str
    supporting_psms: int
    unique_positive_count: int = 0
    unique_signal_mad: float | None = None
    unique_signal_iqr: float | None = None
    unique_signal_quality: str = "no_unique_signal"
    # The digest binds the exact declared group partition and the evidence
    # mappings used for this group.  Empty defaults preserve compatibility for
    # manually constructed cohort projections, while pipeline-produced values
    # always carry the receipt.
    evidence_digest: str = ""
    evidence_version: str = ""
    input_intensity_peptides: int = 0
    input_psm_peptides: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "group_accessions": list(self.group_accessions),
            "primary_intensity": self.primary_intensity,
            "shared_peptides": list(self.shared_peptides),
            "shared_signal": self.shared_signal,
            "status": self.status,
            "supporting_psms": self.supporting_psms,
            "total_signal": self.total_signal,
            "unique_peptides": list(self.unique_peptides),
            "unique_signal": self.unique_signal,
            "unique_positive_count": self.unique_positive_count,
            "unique_signal_mad": self.unique_signal_mad,
            "unique_signal_iqr": self.unique_signal_iqr,
            "unique_signal_quality": self.unique_signal_quality,
            **(
                {
                    "evidence_digest": self.evidence_digest,
                    "evidence_version": self.evidence_version,
                    "input_intensity_peptides": self.input_intensity_peptides,
                    "input_psm_peptides": self.input_psm_peptides,
                }
                if self.evidence_digest
                else {}
            ),
        }


def _median_absolute_deviation(values: tuple[float, ...]) -> float | None:
    """Return descriptive median absolute deviation for at least two values."""

    if len(values) < 2:
        return None
    center = float(median(values))
    return float(median(tuple(abs(value - center) for value in values)))


def _interquartile_range(values: tuple[float, ...]) -> float | None:
    """Return a deterministic Tukey-hinge IQR for at least two values."""

    if len(values) < 2:
        return None
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    lower = ordered[:midpoint]
    upper = ordered[midpoint:] if len(ordered) % 2 == 0 else ordered[midpoint + 1 :]
    return float(median(upper) - median(lower))


def _signal_quality(positive_count: int, *, unique: bool = False) -> str:
    prefix = "unique_" if unique else ""
    if positive_count == 0:
        return f"{prefix}no_positive_signal"
    if positive_count == 1:
        return f"{prefix}single_positive_signal"
    return f"{prefix}descriptive_positive_signal"


def _observation_digest(observations: tuple[tuple[str, float], ...]) -> str:
    """Bind the order-independent observation multiset used for aggregation."""

    payload = [[peptide, intensity] for peptide, intensity in sorted(observations)]
    return sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _materialize_bounded[T](
    values: Iterable[T], *, limit: int, label: str
) -> tuple[T, ...]:
    """Materialize an iterable without allowing an unbounded producer to run."""

    materialized: list[T] = []
    for index, value in enumerate(values):
        if index >= limit:
            raise ValueError(f"{label} exceed {limit} items")
        materialized.append(value)
    return tuple(materialized)


def quantify_matched_ions(
    sample_id: str,
    observations: Iterable[tuple[str, float]],
    *,
    policy: QuantificationPolicy | None = None,
    peptide_universe: Iterable[str] | None = None,
) -> tuple[PeptideQuant, ...]:
    """Aggregate matched-fragment signal and return median-scaled peptide values.

    This is intentionally a transparent research unit: it quantifies the sum of
    finite, non-negative matched-ion intensities per peptide and normalizes them
    to the sample median.  It is not precursor-ion abundance, label-free
    absolute quantification, or a clinical protein concentration estimate.
    Zero signal is retained as explicit missingness; no missing value becomes a
    negative or an imputed positive measurement.
    """

    return quantify_matched_ions_with_receipt(
        sample_id,
        observations,
        policy=policy,
        peptide_universe=peptide_universe,
    ).values


def quantify_matched_ions_with_receipt(
    sample_id: str,
    observations: Iterable[tuple[str, float]],
    *,
    policy: QuantificationPolicy | None = None,
    peptide_universe: Iterable[str] | None = None,
) -> PeptideQuantification:
    """Quantify matched-ion signal and return a complete scale/missingness receipt."""

    selected_policy = policy if policy is not None else QuantificationPolicy()
    if not isinstance(selected_policy, QuantificationPolicy):
        raise TypeError("policy must be a QuantificationPolicy")

    if (
        not isinstance(sample_id, str)
        or not sample_id
        or len(sample_id) > 128
        or sample_id != sample_id.strip()
        or any(character.isspace() or ord(character) < 32 for character in sample_id)
    ):
        raise ValueError("sample_id must be a bounded non-empty string")
    observed = _materialize_bounded(
        observations,
        limit=selected_policy.max_input_observations,
        label="observations",
    )
    totals: dict[str, float] = defaultdict(float)
    universe = (
        _materialize_bounded(
            peptide_universe,
            limit=selected_policy.max_input_observations,
            label="peptide universe",
        )
        if peptide_universe is not None
        else ()
    )
    if len(set(universe)) != len(universe):
        raise ValueError("peptide universe values must be unique")
    for peptide in universe:
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide universe values must be bounded non-empty strings")
        totals.setdefault(peptide, 0.0)
    declared_universe = set(universe) if peptide_universe is not None else None
    normalized_observations: list[tuple[str, float]] = []
    observed_peptides: set[str] = set()
    for item in observed:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("observations must contain (peptide, intensity) tuples")
        peptide, intensity = item
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide must be a bounded non-empty string")
        if declared_universe is not None and peptide not in declared_universe:
            raise ValueError("observation is outside the declared peptide universe")
        if not isfinite(intensity) or intensity < 0:
            raise ValueError("matched-ion intensity must be finite and non-negative")
        normalized_observations.append((peptide, float(intensity)))
        observed_peptides.add(peptide)
        totals[peptide] += intensity
    values = tuple(
        PeptideQuant(
            sample_id,
            peptide,
            intensity,
            missing=(intensity <= selected_policy.limit_of_quantification),
            status=(
                "not_detected"
                if peptide not in observed_peptides
                else "zero_signal"
                if intensity <= 0
                else "below_loq"
                if intensity <= selected_policy.limit_of_quantification
                else "quantified"
            ),
        )
        for peptide, intensity in sorted(totals.items())
    )
    normalized = median_normalize(values, method=selected_policy.normalization_method)
    positive = tuple(item.intensity for item in values if not item.missing and item.intensity > 0)
    raw_median = median(positive) if positive else None
    positive_count = len(positive)
    positive_mad = _median_absolute_deviation(positive)
    positive_iqr = _interquartile_range(positive)
    receipt = QuantificationReceipt(
        sample_id=sample_id,
        version=(
            "matched-ion-median-4"
            if selected_policy == QuantificationPolicy()
            else "matched-ion-median-5"
        ),
        measurement_unit=(
            "median_scaled_matched_ion_intensity"
            if selected_policy.normalization_method == "sample_median_scaled_v1"
            else selected_policy.measurement_unit
        ),
        normalization_method=(
            "sample_median_scaled"
            if selected_policy.normalization_method == "sample_median_scaled_v1"
            else "none"
        ),
        missingness_policy=(
            "zero_signal_is_missing_no_imputation"
            if selected_policy.limit_of_quantification == 0
            else selected_policy.missingness_policy
        ),
        input_observations=len(observed),
        unique_peptides=len(values),
        observed_peptides=sum(not item.missing for item in values),
        missing_peptides=sum(item.missing for item in values),
        duplicate_observations=len(observed) - len(values),
        raw_total_signal=sum(item.intensity for item in values),
        raw_positive_median=raw_median,
        raw_positive_mad=positive_mad,
        raw_positive_iqr=positive_iqr,
        raw_robust_cv=(
            positive_mad / raw_median
            if positive_mad is not None and raw_median is not None and raw_median > 0
            else None
        ),
        positive_signal_fraction=(positive_count / len(values) if values else 0.0),
        signal_quality=_signal_quality(positive_count),
        normalization_target=raw_median,
        normalized_total_signal=sum(item.intensity for item in normalized),
        scale_factor=1.0 if positive else None,
        raw_peptide_signals=tuple((item.peptide, item.intensity, item.missing) for item in values),
        normalized_peptide_signals=tuple(
            (item.peptide, item.intensity, item.missing) for item in normalized
        ),
        limit_of_quantification=float(selected_policy.limit_of_quantification),
        below_loq_peptides=sum(item.status == "below_loq" for item in values),
        quantifiable_peptides=positive_count,
        raw_peptide_statuses=tuple((item.peptide, item.status) for item in values),
        normalized_peptide_statuses=tuple((item.peptide, item.status) for item in normalized),
        observation_digest=_observation_digest(tuple(normalized_observations)),
        max_input_observations=selected_policy.max_input_observations,
    )
    return PeptideQuantification(normalized, receipt)


def median_normalize(
    values: tuple[PeptideQuant, ...], *, method: str = "sample_median_scaled_v1"
) -> tuple[PeptideQuant, ...]:
    if method not in {"none_v1", "sample_median_scaled_v1"}:
        raise ValueError("normalization method is not supported")
    if method == "none_v1":
        return tuple(
            item
            if not item.missing or item.intensity <= 0
            else PeptideQuant(item.sample_id, item.peptide, 0.0, missing=True, status=item.status)
            for item in values
        )
    observed = [item.intensity for item in values if not item.missing and item.intensity > 0]
    if not observed:
        return tuple(
            item
            if not item.missing or item.intensity <= 0
            else PeptideQuant(item.sample_id, item.peptide, 0.0, missing=True, status=item.status)
            for item in values
        )
    center = median(observed)
    sample_medians: dict[str, float] = {}
    for sample_id in {item.sample_id for item in values}:
        sample = [
            item.intensity
            for item in values
            if item.sample_id == sample_id and not item.missing and item.intensity > 0
        ]
        if sample:
            sample_medians[sample_id] = median(sample)
    return tuple(
        PeptideQuant(item.sample_id, item.peptide, 0.0, missing=True, status=item.status)
        if item.missing and item.intensity > 0
        else item
        if item.missing or item.intensity <= 0 or item.sample_id not in sample_medians
        else PeptideQuant(
            item.sample_id,
            item.peptide,
            item.intensity * center / sample_medians[item.sample_id],
            missing=False,
            status=item.status,
        )
        for item in values
    )


def _validate_group_partition(groups: tuple[ProteinGroup, ...]) -> set[str]:
    declared_peptides: set[str] = set()
    declared_accessions: set[str] = set()
    for group in groups:
        if not isinstance(group, ProteinGroup):
            raise TypeError("groups must contain ProteinGroup values")
        if not group.accessions or any(
            not isinstance(accession, str) or not accession for accession in group.accessions
        ):
            raise ValueError("protein groups must have non-empty accession values")
        if len(set(group.accessions)) != len(group.accessions):
            raise ValueError("protein groups must not repeat accessions")
        if declared_accessions.intersection(group.accessions):
            raise ValueError("protein groups must have disjoint accession membership")
        declared_accessions.update(group.accessions)
        group_peptides = (*group.unique_peptides, *group.shared_peptides)
        if any(not isinstance(peptide, str) or not peptide for peptide in group_peptides):
            raise ValueError("protein groups must have non-empty peptide values")
        if len(set(group_peptides)) != len(group_peptides):
            raise ValueError("protein groups must not repeat peptides within a group")
        if declared_peptides.intersection(group_peptides):
            raise ValueError("protein groups must have disjoint peptide membership")
        declared_peptides.update(group_peptides)
    return declared_peptides


def _normalize_group_intensities(
    peptide_intensities: Mapping[str, float], declared_peptides: set[str]
) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for peptide, intensity in peptide_intensities.items():
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide intensity keys must be bounded non-empty strings")
        if not isinstance(intensity, (int, float)) or isinstance(intensity, bool):
            raise TypeError("peptide intensities must be numeric")
        if not isfinite(float(intensity)) or intensity < 0:
            raise ValueError("peptide intensities must be finite and non-negative")
        normalized[peptide] = float(intensity)
    if set(normalized).difference(declared_peptides):
        raise ValueError("peptide intensities contain unreferenced evidence")
    return normalized


def _normalize_group_psm_counts(
    peptide_psm_counts: Mapping[str, int], declared_peptides: set[str]
) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for peptide, count in peptide_psm_counts.items():
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide PSM keys must be bounded non-empty strings")
        if type(count) is not int or count < 0:
            raise ValueError("peptide PSM counts must be non-negative integers")
        normalized[peptide] = count
    if set(normalized).difference(declared_peptides):
        raise ValueError("peptide PSM counts contain unreferenced evidence")
    return normalized


def _group_evidence_digest(
    group: ProteinGroup,
    normalized_intensities: Mapping[str, float],
    normalized_counts: Mapping[str, int],
) -> str:
    group_peptides = (*group.unique_peptides, *group.shared_peptides)
    evidence_payload = {
        "group_accessions": list(group.accessions),
        "unique_peptides": list(group.unique_peptides),
        "shared_peptides": list(group.shared_peptides),
        "intensities": [
            [peptide, normalized_intensities.get(peptide)] for peptide in group_peptides
        ],
        "psm_counts": [[peptide, normalized_counts.get(peptide)] for peptide in group_peptides],
        "version": "protein-group-quantification-input-1",
    }
    return sha256(
        json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def quantify_protein_groups(
    groups: Iterable[ProteinGroup],
    peptide_intensities: Mapping[str, float],
    peptide_psm_counts: Mapping[str, int],
) -> tuple[ProteinGroupQuant, ...]:
    """Quantify groups without inventing values for shared-peptide ambiguity.

    The primary estimate is the median of positive unique-peptide intensities.
    Shared signal remains visible in ``shared_signal`` and ``total_signal`` but
    cannot create an apparently resolved protein value on its own.
    """

    materialized_groups = tuple(groups)
    if not materialized_groups:
        return ()
    declared_peptides = _validate_group_partition(materialized_groups)
    normalized_intensities = _normalize_group_intensities(peptide_intensities, declared_peptides)
    normalized_counts = _normalize_group_psm_counts(peptide_psm_counts, declared_peptides)
    output: list[ProteinGroupQuant] = []
    for group in sorted(materialized_groups, key=lambda item: item.accessions):
        group_peptides = (*group.unique_peptides, *group.shared_peptides)
        evidence_digest = _group_evidence_digest(group, normalized_intensities, normalized_counts)
        unique_signal_values = tuple(
            normalized_intensities.get(peptide, 0.0)
            for peptide in group.unique_peptides
            if normalized_intensities.get(peptide, 0.0) > 0
        )
        shared_signal_values = tuple(
            normalized_intensities.get(peptide, 0.0)
            for peptide in group.shared_peptides
            if normalized_intensities.get(peptide, 0.0) > 0
        )
        unique_signal = sum(unique_signal_values)
        shared_signal = sum(shared_signal_values)
        primary_intensity = median(unique_signal_values) if unique_signal_values else None
        status = (
            "quantified"
            if primary_intensity is not None
            else "non_quantifiable_shared_only"
            if shared_signal_values
            else "missing"
        )
        supporting_psms = sum(
            normalized_counts.get(peptide, 0)
            for peptide in (*group.unique_peptides, *group.shared_peptides)
        )
        output.append(
            ProteinGroupQuant(
                group_accessions=group.accessions,
                unique_peptides=group.unique_peptides,
                shared_peptides=group.shared_peptides,
                unique_signal=unique_signal,
                shared_signal=shared_signal,
                total_signal=unique_signal + shared_signal,
                primary_intensity=primary_intensity,
                status=status,
                supporting_psms=supporting_psms,
                unique_positive_count=len(unique_signal_values),
                unique_signal_mad=_median_absolute_deviation(unique_signal_values),
                unique_signal_iqr=_interquartile_range(unique_signal_values),
                unique_signal_quality=_signal_quality(len(unique_signal_values), unique=True),
                evidence_digest=evidence_digest,
                evidence_version="protein-group-quantification-input-1",
                input_intensity_peptides=sum(
                    peptide in normalized_intensities for peptide in group_peptides
                ),
                input_psm_peptides=sum(peptide in normalized_counts for peptide in group_peptides),
            )
        )
    return tuple(output)
