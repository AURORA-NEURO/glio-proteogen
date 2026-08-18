"""Deterministic label-free peptide quantification and median normalization."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True, slots=True)
class PeptideQuant:
    sample_id: str
    peptide: str
    intensity: float
    missing: bool = False


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
