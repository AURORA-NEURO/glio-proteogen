"""Deterministic label-free peptide quantification and median normalization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True, slots=True)
class PeptideQuant:
    sample_id: str
    peptide: str
    intensity: float
    missing: bool = False


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
