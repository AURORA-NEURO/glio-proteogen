"""Transparent peptide-spectrum matching with explicit target/decoy competition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from math import hypot


@dataclass(frozen=True, slots=True)
class SearchParameters:
    precursor_tolerance_ppm: int = 20
    fragment_tolerance_da: float = 0.02
    min_matched_ions: int = 2


@dataclass(frozen=True, slots=True)
class Psm:
    spectrum_id: str
    peptide: str
    protein_accessions: tuple[str, ...]
    score: float
    matched_ions: int
    decoy: bool
    q_value: float | None = None


_MASS = {
    "A": 71.037114,
    "R": 156.101111,
    "N": 114.042927,
    "D": 115.026943,
    "C": 103.009185,
    "E": 129.042593,
    "Q": 128.058578,
    "G": 57.021464,
    "H": 137.058912,
    "I": 113.084064,
    "L": 113.084064,
    "K": 128.094963,
    "M": 131.040485,
    "F": 147.068414,
    "P": 97.052764,
    "S": 87.032028,
    "T": 101.047679,
    "W": 186.079313,
    "Y": 163.063329,
    "V": 99.068414,
}
_PROTON = 1.007276466
_DEFAULT_PARAMETERS = SearchParameters()


def _fragments(peptide: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    running = 0.0
    b: list[float] = []
    for residue in peptide[:-1]:
        running += _MASS[residue]
        b.append(running + _PROTON)
    running = 18.010565
    y: list[float] = []
    for residue in reversed(peptide[1:]):
        running += _MASS[residue]
        y.append(running + _PROTON)
    return tuple(b), tuple(y)


def search_spectrum(
    spectrum_id: str,
    precursor_mz: float,
    peptide_map: dict[str, tuple[str, ...]],
    observed_mz: Iterable[float],
    observed_intensity: Iterable[float],
    *,
    parameters: SearchParameters = _DEFAULT_PARAMETERS,
) -> Psm | None:
    """Return the highest-scoring candidate; precursor indexing is caller-owned."""
    _ = precursor_mz
    mz = tuple(observed_mz)
    intensity = tuple(observed_intensity)
    if len(mz) != len(intensity):
        raise ValueError("observed m/z and intensity lengths differ")
    norm = hypot(*intensity) if intensity else 0.0
    best: Psm | None = None
    for peptide, accessions in peptide_map.items():
        if not peptide or any(residue not in _MASS for residue in peptide):
            continue
        theoretical = _fragments(peptide)[0] + _fragments(peptide)[1]
        matched = 0
        intensity_score = 0.0
        for value in theoretical:
            candidates = [
                (index, observed)
                for index, observed in enumerate(mz)
                if abs(observed - value) <= parameters.fragment_tolerance_da
            ]
            if candidates:
                index, observed = min(candidates, key=lambda item: abs(item[1] - value))
                matched += 1
                intensity_score += intensity[index] / (1.0 + abs(observed - value))
        if matched < parameters.min_matched_ions:
            continue
        candidate = Psm(
            spectrum_id=spectrum_id,
            peptide=peptide,
            protein_accessions=tuple(accessions),
            score=matched + (intensity_score / norm if norm else 0.0),
            matched_ions=matched,
            decoy=any(accession.startswith("DECOY_") for accession in accessions),
        )
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def target_decoy_qvalues(psms: Iterable[Psm]) -> tuple[Psm, ...]:
    ordered = sorted(psms, key=lambda value: (-value.score, value.spectrum_id, value.peptide))
    decoys = 0
    targets = 0
    raw: list[tuple[Psm, float]] = []
    for psm in ordered:
        decoys += int(psm.decoy)
        targets += int(not psm.decoy)
        raw.append((psm, decoys / max(targets, 1)))
    running = 1.0
    output: list[Psm] = []
    for psm, value in reversed(raw):
        running = min(running, value)
        output.append(replace(psm, q_value=running))
    return tuple(reversed(output))
