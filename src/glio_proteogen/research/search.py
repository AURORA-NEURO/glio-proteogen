"""Transparent peptide-spectrum matching with explicit target/decoy competition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from math import hypot, isfinite


@dataclass(frozen=True, slots=True)
class SearchParameters:
    precursor_tolerance_ppm: int = 20
    fragment_tolerance_da: float = 0.02
    min_matched_ions: int = 2
    precursor_charge: int = 1
    require_precursor_mz: bool = False

    def __post_init__(self) -> None:
        if self.precursor_tolerance_ppm < 0:
            raise ValueError("precursor_tolerance_ppm must be non-negative")
        if not isfinite(self.fragment_tolerance_da) or self.fragment_tolerance_da <= 0:
            raise ValueError("fragment_tolerance_da must be finite and positive")
        if self.min_matched_ions < 1:
            raise ValueError("min_matched_ions must be positive")
        if self.precursor_charge < 1:
            raise ValueError("precursor_charge must be positive")


@dataclass(frozen=True, slots=True)
class Psm:
    spectrum_id: str
    peptide: str
    protein_accessions: tuple[str, ...]
    score: float
    matched_ions: int
    decoy: bool
    q_value: float | None = None
    matched_intensity: float = 0.0


@dataclass(frozen=True, slots=True)
class FdrSummary:
    """Auditable target/decoy summary for one winner per spectrum.

    The summary is descriptive evidence, not a calibrated probability or a
    clinical confidence score.  Decoys are retained in the winner table and
    are never promoted to accepted targets by the pipeline.
    """

    method: str
    spectrum_winners: int
    target_winners: int
    decoy_winners: int
    accepted_targets: int
    q_value_threshold: float
    max_accepted_q_value: float | None
    decoy_to_target_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_targets": self.accepted_targets,
            "decoy_to_target_ratio": self.decoy_to_target_ratio,
            "decoy_winners": self.decoy_winners,
            "max_accepted_q_value": self.max_accepted_q_value,
            "method": self.method,
            "q_value_threshold": self.q_value_threshold,
            "spectrum_winners": self.spectrum_winners,
            "target_winners": self.target_winners,
        }


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
_WATER = 18.010565
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


def _precursor_mz(peptide: str, charge: int) -> float:
    neutral_mass = _WATER + sum(_MASS[residue] for residue in peptide)
    return (neutral_mass + (charge * _PROTON)) / charge


def search_spectrum(
    spectrum_id: str,
    precursor_mz: float,
    peptide_map: dict[str, tuple[str, ...]],
    observed_mz: Iterable[float],
    observed_intensity: Iterable[float],
    *,
    parameters: SearchParameters = _DEFAULT_PARAMETERS,
) -> Psm | None:
    """Return the best precursor-compatible candidate or abstain safely.

    A missing or non-finite precursor is not silently treated as a match.  This
    research primitive supports one precursor charge at a time; callers that
    cannot provide that metadata must abstain or run a separately declared
    open-search workflow.
    """
    if parameters.require_precursor_mz and (not isfinite(precursor_mz) or precursor_mz <= 0):
        return None
    mz = tuple(observed_mz)
    intensity = tuple(observed_intensity)
    if len(mz) != len(intensity):
        raise ValueError("observed m/z and intensity lengths differ")
    if any(not isfinite(value) or value < 0 for value in mz):
        return None
    if any(not isfinite(value) or value < 0 for value in intensity):
        return None
    norm = hypot(*intensity) if intensity else 0.0
    best: Psm | None = None
    for peptide, accessions in peptide_map.items():
        if not peptide or any(residue not in _MASS for residue in peptide):
            continue
        if parameters.require_precursor_mz:
            theoretical_precursor = _precursor_mz(peptide, parameters.precursor_charge)
            ppm_error = (
                abs(precursor_mz - theoretical_precursor) / theoretical_precursor * 1_000_000
            )
            if ppm_error > parameters.precursor_tolerance_ppm:
                continue
        theoretical = _fragments(peptide)[0] + _fragments(peptide)[1]
        matched = 0
        intensity_score = 0.0
        matched_intensity = 0.0
        used_indices: set[int] = set()
        for value in theoretical:
            candidates = [
                (index, observed)
                for index, observed in enumerate(mz)
                if index not in used_indices
                and abs(observed - value) <= parameters.fragment_tolerance_da
            ]
            if candidates:
                index, observed = min(candidates, key=lambda item: abs(item[1] - value))
                used_indices.add(index)
                matched += 1
                matched_intensity += intensity[index]
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
            matched_intensity=matched_intensity,
        )
        if best is None or (
            candidate.score,
            not candidate.decoy,
            candidate.peptide,
            candidate.protein_accessions,
        ) > (
            best.score,
            not best.decoy,
            best.peptide,
            best.protein_accessions,
        ):
            best = candidate
    return best


def target_decoy_qvalues(psms: Iterable[Psm]) -> tuple[Psm, ...]:
    winners: dict[str, Psm] = {}
    for psm in psms:
        if not isfinite(psm.score) or psm.score < 0:
            raise ValueError("PSM scores must be finite and non-negative")
        current = winners.get(psm.spectrum_id)
        if current is None or (
            psm.score,
            not psm.decoy,
            psm.peptide,
            psm.protein_accessions,
        ) > (
            current.score,
            not current.decoy,
            current.peptide,
            current.protein_accessions,
        ):
            winners[psm.spectrum_id] = psm
    ordered = sorted(
        winners.values(), key=lambda value: (-value.score, value.spectrum_id, value.peptide)
    )
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
        output.append(replace(psm, q_value=None if psm.decoy else running))
    return tuple(reversed(output))


def summarize_target_decoy(psms: Iterable[Psm], *, q_value_threshold: float) -> FdrSummary:
    """Return replayable winner-level FDR evidence for a declared threshold."""

    if not isfinite(q_value_threshold) or not 0 <= q_value_threshold <= 1:
        raise ValueError("q_value_threshold must be finite and between zero and one")
    scored = target_decoy_qvalues(psms)
    target_winners = sum(not item.decoy for item in scored)
    decoy_winners = sum(item.decoy for item in scored)
    accepted = tuple(
        item
        for item in scored
        if not item.decoy and item.q_value is not None and item.q_value <= q_value_threshold
    )
    accepted_q_values = tuple(item.q_value for item in accepted if item.q_value is not None)
    return FdrSummary(
        method="winner-per-spectrum-monotone-target-decoy-1",
        spectrum_winners=len(scored),
        target_winners=target_winners,
        decoy_winners=decoy_winners,
        accepted_targets=len(accepted),
        q_value_threshold=q_value_threshold,
        max_accepted_q_value=max(accepted_q_values) if accepted_q_values else None,
        decoy_to_target_ratio=decoy_winners / target_winners if target_winners else 0.0,
    )
