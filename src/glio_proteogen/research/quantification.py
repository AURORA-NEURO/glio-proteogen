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

    if not isinstance(sample_id, str) or not sample_id or len(sample_id) > 128:
        raise ValueError("sample_id must be a bounded non-empty string")
    totals: dict[str, float] = defaultdict(float)
    for peptide, intensity in observations:
        if not isinstance(peptide, str) or not peptide or len(peptide) > 256:
            raise ValueError("peptide must be a bounded non-empty string")
        if not isfinite(intensity) or intensity < 0:
            raise ValueError("matched-ion intensity must be finite and non-negative")
        totals[peptide] += intensity
    values = tuple(
        PeptideQuant(sample_id, peptide, intensity, missing=intensity <= 0)
        for peptide, intensity in sorted(totals.items())
    )
    return median_normalize(values)


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
