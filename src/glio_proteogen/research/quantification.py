"""Deterministic label-free peptide quantification and median normalization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protein import ProteinGroup


@dataclass(frozen=True, slots=True)
class PeptideQuant:
    sample_id: str
    peptide: str
    intensity: float
    missing: bool = False


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

    def as_dict(self) -> dict[str, object]:
        return {
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
            "raw_total_signal": self.raw_total_signal,
            "sample_id": self.sample_id,
            "scale_factor": self.scale_factor,
            "unique_peptides": self.unique_peptides,
            "version": self.version,
        }


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
        }


def quantify_matched_ions(
    sample_id: str, observations: Iterable[tuple[str, float]]
) -> tuple[PeptideQuant, ...]:
    """Aggregate matched-fragment signal and return median-scaled peptide values.

    This is intentionally a transparent research unit: it quantifies the sum of
    finite, non-negative matched-ion intensities per peptide and normalizes them
    to the sample median.  It is not precursor-ion abundance, label-free
    absolute quantification, or a clinical protein concentration estimate.
    Zero signal is retained as explicit missingness; no missing value becomes a
    negative or an imputed positive measurement.
    """

    return quantify_matched_ions_with_receipt(sample_id, observations).values


def quantify_matched_ions_with_receipt(
    sample_id: str, observations: Iterable[tuple[str, float]]
) -> PeptideQuantification:
    """Quantify matched-ion signal and return a complete scale/missingness receipt."""

    if (
        not isinstance(sample_id, str)
        or not sample_id
        or len(sample_id) > 128
        or sample_id != sample_id.strip()
        or any(character.isspace() or ord(character) < 32 for character in sample_id)
    ):
        raise ValueError("sample_id must be a bounded non-empty string")
    observed = tuple(observations)
    totals: dict[str, float] = defaultdict(float)
    for peptide, intensity in observed:
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide must be a bounded non-empty string")
        if not isfinite(intensity) or intensity < 0:
            raise ValueError("matched-ion intensity must be finite and non-negative")
        totals[peptide] += intensity
    values = tuple(
        PeptideQuant(sample_id, peptide, intensity, missing=intensity <= 0)
        for peptide, intensity in sorted(totals.items())
    )
    normalized = median_normalize(values)
    positive = tuple(item.intensity for item in values if not item.missing and item.intensity > 0)
    raw_median = median(positive) if positive else None
    receipt = QuantificationReceipt(
        sample_id=sample_id,
        version="matched-ion-median-2",
        measurement_unit="median_scaled_matched_ion_intensity",
        normalization_method="sample_median_scaled",
        missingness_policy="zero_signal_is_missing_no_imputation",
        input_observations=len(observed),
        unique_peptides=len(values),
        observed_peptides=sum(not item.missing for item in values),
        missing_peptides=sum(item.missing for item in values),
        duplicate_observations=len(observed) - len(values),
        raw_total_signal=sum(item.intensity for item in values),
        raw_positive_median=raw_median,
        normalization_target=raw_median,
        normalized_total_signal=sum(item.intensity for item in normalized),
        scale_factor=1.0 if positive else None,
        raw_peptide_signals=tuple((item.peptide, item.intensity, item.missing) for item in values),
        normalized_peptide_signals=tuple(
            (item.peptide, item.intensity, item.missing) for item in normalized
        ),
    )
    return PeptideQuantification(normalized, receipt)


def median_normalize(values: tuple[PeptideQuant, ...]) -> tuple[PeptideQuant, ...]:
    observed = [item.intensity for item in values if not item.missing and item.intensity > 0]
    if not observed:
        return values
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
        item
        if item.missing or item.intensity <= 0 or item.sample_id not in sample_medians
        else PeptideQuant(
            item.sample_id, item.peptide, item.intensity * center / sample_medians[item.sample_id]
        )
        for item in values
    )


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

    normalized_intensities: dict[str, float] = {}
    for peptide, intensity in peptide_intensities.items():
        if not isinstance(peptide, str) or not peptide:
            raise ValueError("peptide intensity keys must be non-empty strings")
        if not isinstance(intensity, (int, float)) or isinstance(intensity, bool):
            raise TypeError("peptide intensities must be numeric")
        if not isfinite(float(intensity)) or intensity < 0:
            raise ValueError("peptide intensities must be finite and non-negative")
        normalized_intensities[peptide] = float(intensity)
    normalized_counts: dict[str, int] = {}
    for peptide, count in peptide_psm_counts.items():
        if not isinstance(peptide, str) or not peptide:
            raise ValueError("peptide PSM keys must be non-empty strings")
        if type(count) is not int or count < 0:
            raise ValueError("peptide PSM counts must be non-negative integers")
        normalized_counts[peptide] = count
    output: list[ProteinGroupQuant] = []
    for group in sorted(groups, key=lambda item: item.accessions):
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
            )
        )
    return tuple(output)
