"""Transparent peptide-spectrum matching with explicit target/decoy competition."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha256
from math import hypot, isfinite

from .modifications import normalize_modification_rules, parse_modified_peptide


@dataclass(frozen=True, slots=True)
class SearchParameters:
    precursor_tolerance_ppm: int = 20
    fragment_tolerance_da: float = 0.02
    min_matched_ions: int = 2
    precursor_charge: int = 1
    decoy_prefix: str = "DECOY_"
    require_precursor_mz: bool = False
    allowed_modifications: tuple[str, ...] = ()
    max_variable_modifications: int = 0

    def __post_init__(self) -> None:
        if type(self.precursor_tolerance_ppm) is not int or self.precursor_tolerance_ppm < 0:
            raise ValueError("precursor_tolerance_ppm must be non-negative")
        if not isfinite(self.fragment_tolerance_da) or self.fragment_tolerance_da <= 0:
            raise ValueError("fragment_tolerance_da must be finite and positive")
        if self.min_matched_ions < 1:
            raise ValueError("min_matched_ions must be positive")
        if type(self.precursor_charge) is not int or not 1 <= self.precursor_charge <= 20:
            raise ValueError("precursor_charge must be positive")
        if (
            not isinstance(self.decoy_prefix, str)
            or not 1 <= len(self.decoy_prefix) <= 32
            or any(character.isspace() or ord(character) < 33 for character in self.decoy_prefix)
        ):
            raise ValueError("decoy_prefix must be a bounded non-whitespace token")
        if type(self.require_precursor_mz) is not bool:
            raise ValueError("require_precursor_mz must be boolean")
        normalized = normalize_modification_rules(self.allowed_modifications)
        if normalized != self.allowed_modifications:
            object.__setattr__(self, "allowed_modifications", normalized)
        if (
            type(self.max_variable_modifications) is not int
            or not 0 <= self.max_variable_modifications <= 3
        ):
            raise ValueError("max_variable_modifications must be between zero and three")


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
    mean_fragment_error_da: float = 0.0
    precursor_error_ppm: float | None = None
    target_decoy_collision: bool = False


@dataclass(frozen=True, slots=True)
class PsmCompetition:
    """Immutable audit receipt for every candidate considered for one spectrum.

    The selected winner is not sufficient evidence for a target/decoy search:
    a changed lower-scoring contender can indicate a different search space even
    when the final PSM is unchanged.  This receipt binds candidate cardinality,
    class counts, score margin, and a canonical candidate digest without making
    the research result claim a calibrated posterior probability.
    """

    spectrum_id: str
    candidate_count: int
    target_candidates: int
    decoy_candidates: int
    collision_candidates: int
    winner_score: float
    runner_up_score: float | None
    score_margin: float | None
    candidate_digest: str

    @classmethod
    def from_candidates(cls, candidates: Iterable[Psm]) -> PsmCompetition:
        ordered = tuple(sorted(candidates, key=_competition_sort_key, reverse=True))
        if not ordered:
            raise ValueError("competition receipt requires at least one candidate")
        spectrum_id = ordered[0].spectrum_id
        if any(item.spectrum_id != spectrum_id for item in ordered):
            raise ValueError("competition candidates must share a spectrum_id")
        payload = [_candidate_payload(item) for item in ordered]
        digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        runner_up = ordered[1].score if len(ordered) > 1 else None
        return cls(
            spectrum_id=spectrum_id,
            candidate_count=len(ordered),
            target_candidates=sum(
                not item.decoy and not item.target_decoy_collision for item in ordered
            ),
            decoy_candidates=sum(item.decoy for item in ordered),
            collision_candidates=sum(item.target_decoy_collision for item in ordered),
            winner_score=ordered[0].score,
            runner_up_score=runner_up,
            score_margin=ordered[0].score - runner_up if runner_up is not None else None,
            candidate_digest=digest,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "candidate_digest": self.candidate_digest,
            "collision_candidates": self.collision_candidates,
            "decoy_candidates": self.decoy_candidates,
            "runner_up_score": self.runner_up_score,
            "score_margin": self.score_margin,
            "spectrum_id": self.spectrum_id,
            "target_candidates": self.target_candidates,
            "winner_score": self.winner_score,
        }


@dataclass(frozen=True, slots=True)
class FdrSummary:
    """Auditable target/decoy summary for one winner per spectrum.

    The summary is descriptive evidence, not a calibrated probability or a
    clinical confidence score.  Decoys are retained in the winner table and
    are never promoted to accepted targets by the pipeline.  A target-only
    winner table has no empirical error evidence, so its target q-values are
    intentionally absent rather than reported as zero.
    """

    method: str
    spectrum_winners: int
    target_winners: int
    decoy_winners: int
    collision_winners: int
    accepted_targets: int
    q_value_threshold: float
    max_accepted_q_value: float | None
    decoy_to_target_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_targets": self.accepted_targets,
            "decoy_to_target_ratio": self.decoy_to_target_ratio,
            "decoy_winners": self.decoy_winners,
            "collision_winners": self.collision_winners,
            "max_accepted_q_value": self.max_accepted_q_value,
            "method": self.method,
            "q_value_threshold": self.q_value_threshold,
            "spectrum_winners": self.spectrum_winners,
            "target_winners": self.target_winners,
        }


def _validate_target_decoy_psm(psm: Psm, *, decoy_prefix: str = "DECOY_") -> None:
    """Validate the target/decoy class against the declared accessions.

    The search primitive is public and can be called without the pipeline's
    later protein-group validation.  Accepting a forged ``decoy=False`` flag
    here would let a decoy accession contribute to target-level FDR, so class
    membership is derived and checked at the first FDR boundary.
    """

    if (
        type(psm.spectrum_id) is not str
        or not psm.spectrum_id
        or len(psm.spectrum_id) > 256
        or psm.spectrum_id != psm.spectrum_id.strip()
        or any(character.isspace() or ord(character) < 32 for character in psm.spectrum_id)
    ):
        raise ValueError("PSM spectrum_id must be a bounded opaque string")
    if (
        type(psm.peptide) is not str
        or not psm.peptide
        or len(psm.peptide) > 256
        or any(character.isspace() or ord(character) < 32 for character in psm.peptide)
    ):
        raise ValueError("PSM peptide must be a bounded non-whitespace string")
    if type(psm.protein_accessions) is not tuple or not psm.protein_accessions:
        raise ValueError("PSM must declare at least one protein accession")
    if any(
        type(accession) is not str
        or not accession
        or len(accession) > 256
        or accession != accession.strip()
        or any(character.isspace() or ord(character) < 32 for character in accession)
        for accession in psm.protein_accessions
    ):
        raise ValueError("PSM protein accessions must be bounded opaque strings")
    if len(set(psm.protein_accessions)) != len(psm.protein_accessions):
        raise ValueError("PSM protein accessions must be unique")
    if type(psm.decoy) is not bool or type(psm.target_decoy_collision) is not bool:
        raise ValueError("PSM target/decoy flags must be boolean")
    if type(psm.matched_ions) is not int or psm.matched_ions < 1:
        raise ValueError("PSM matched_ions must be a positive integer")
    for value, label in (
        (psm.score, "score"),
        (psm.matched_intensity, "matched_intensity"),
        (psm.mean_fragment_error_da, "mean_fragment_error_da"),
    ):
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            raise ValueError(f"PSM {label} must be finite and non-negative")
    if psm.precursor_error_ppm is not None and (
        type(psm.precursor_error_ppm) not in (int, float)
        or not isfinite(psm.precursor_error_ppm)
        or psm.precursor_error_ppm < 0
    ):
        raise ValueError("PSM precursor_error_ppm must be finite and non-negative")
    if psm.q_value is not None and (
        type(psm.q_value) not in (int, float)
        or not isfinite(psm.q_value)
        or not 0 <= psm.q_value <= 1
    ):
        raise ValueError("PSM q_value must be finite and between zero and one")
    derived_decoy = all(accession.startswith(decoy_prefix) for accession in psm.protein_accessions)
    derived_collision = (
        any(accession.startswith(decoy_prefix) for accession in psm.protein_accessions)
        and not derived_decoy
    )
    if psm.decoy != derived_decoy or psm.target_decoy_collision != derived_collision:
        raise ValueError("PSM target/decoy flags do not match protein accessions")


def _validate_decoy_prefix(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 32
        or any(character.isspace() or ord(character) < 33 for character in value)
    ):
        raise ValueError("decoy_prefix must be a bounded non-whitespace token")


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


def _fragments(
    peptide: str, *, allowed_modifications: tuple[str, ...] = ()
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    parsed = parse_modified_peptide(peptide, allowed_modifications=allowed_modifications)
    masses = parsed.residue_masses
    running = 0.0
    b: list[float] = []
    for residue_mass in masses[:-1]:
        running += residue_mass
        b.append(running + _PROTON)
    running = 18.010565
    y: list[float] = []
    for residue_mass in reversed(masses[1:]):
        running += residue_mass
        y.append(running + _PROTON)
    return tuple(b), tuple(y)


def _precursor_mz(
    peptide: str, charge: int, *, allowed_modifications: tuple[str, ...] = ()
) -> float:
    parsed = parse_modified_peptide(peptide, allowed_modifications=allowed_modifications)
    neutral_mass = _WATER + sum(parsed.residue_masses)
    return (neutral_mass + (charge * _PROTON)) / charge


def _competition_sort_key(value: Psm) -> tuple[float, bool, bool, str, tuple[str, ...]]:
    """Order candidates conservatively when scores are exactly tied.

    Equal target/decoy evidence cannot support a target preference. Collision
    candidates sort first as explicit abstention evidence, then pure decoys
    sort ahead of targets. This ordering is shared by candidate receipts and
    winner selection so replay cannot silently change tie policy.
    """

    return (
        value.score,
        value.target_decoy_collision,
        value.decoy,
        value.peptide,
        value.protein_accessions,
    )


def _candidate_payload(value: Psm) -> dict[str, object]:
    return {
        "decoy": value.decoy,
        "matched_intensity": value.matched_intensity,
        "matched_ions": value.matched_ions,
        "mean_fragment_error_da": value.mean_fragment_error_da,
        "peptide": value.peptide,
        "precursor_error_ppm": value.precursor_error_ppm,
        "protein_accessions": list(value.protein_accessions),
        "score": value.score,
        "spectrum_id": value.spectrum_id,
        "target_decoy_collision": value.target_decoy_collision,
    }


def _assign_fragment_peaks(
    theoretical: tuple[float, ...],
    observed_mz: tuple[float, ...],
    tolerance_da: float,
) -> tuple[tuple[int, int], ...]:
    """Select a deterministic maximum-cardinality peak assignment.

    Fragment-ion windows can overlap.  A nearest-peak greedy pass can consume
    the only peak available to a later ion and undercount a valid spectrum.  On
    the one-dimensional m/z axis, an optimal assignment can be chosen without
    crossing edges after sorting both sides, so a bounded suffix dynamic
    program is sufficient.  The objective is maximum matched-ion count first,
    then minimum total absolute error; stable index ordering resolves exact
    ties.  The returned indices refer to the caller's original sequences.
    """

    ordered_theoretical = tuple(sorted(enumerate(theoretical), key=lambda item: (item[1], item[0])))
    ordered_observed = tuple(sorted(enumerate(observed_mz), key=lambda item: (item[1], item[0])))
    theoretical_count = len(ordered_theoretical)
    observed_count = len(ordered_observed)
    counts = [[0] * (observed_count + 1) for _ in range(theoretical_count + 1)]
    errors = [[0.0] * (observed_count + 1) for _ in range(theoretical_count + 1)]
    actions = [["" for _ in range(observed_count + 1)] for _ in range(theoretical_count + 1)]

    def better(  # noqa: PLR0917 - comparator keeps all DP tie-break state explicit.
        candidate_count: int,
        candidate_error: float,
        candidate_action: str,
        current_count: int,
        current_error: float,
        current_action: str,
    ) -> bool:
        if candidate_count != current_count:
            return candidate_count > current_count
        if candidate_error != current_error:
            return candidate_error < current_error
        # Prefer a match, then skipping an observed peak, then skipping an ion.
        # This only resolves equivalent optima and keeps replay stable.
        return {"m": 0, "o": 1, "t": 2}[candidate_action] < {
            "m": 0,
            "o": 1,
            "t": 2,
        }[current_action]

    for theoretical_index in range(theoretical_count - 1, -1, -1):
        for observed_index in range(observed_count - 1, -1, -1):
            best_count = counts[theoretical_index + 1][observed_index]
            best_error = errors[theoretical_index + 1][observed_index]
            best_action = "t"
            skip_observed_count = counts[theoretical_index][observed_index + 1]
            skip_observed_error = errors[theoretical_index][observed_index + 1]
            if better(
                skip_observed_count,
                skip_observed_error,
                "o",
                best_count,
                best_error,
                best_action,
            ):
                best_count, best_error, best_action = (
                    skip_observed_count,
                    skip_observed_error,
                    "o",
                )
            theoretical_value = ordered_theoretical[theoretical_index][1]
            observed_value = ordered_observed[observed_index][1]
            error = abs(observed_value - theoretical_value)
            if error <= tolerance_da:
                match_count = 1 + counts[theoretical_index + 1][observed_index + 1]
                match_error = error + errors[theoretical_index + 1][observed_index + 1]
                if better(
                    match_count,
                    match_error,
                    "m",
                    best_count,
                    best_error,
                    best_action,
                ):
                    best_count, best_error, best_action = match_count, match_error, "m"
            counts[theoretical_index][observed_index] = best_count
            errors[theoretical_index][observed_index] = best_error
            actions[theoretical_index][observed_index] = best_action

    assignments: list[tuple[int, int]] = []
    theoretical_index = 0
    observed_index = 0
    while theoretical_index < theoretical_count and observed_index < observed_count:
        action = actions[theoretical_index][observed_index]
        if action == "m":
            assignments.append(
                (
                    ordered_theoretical[theoretical_index][0],
                    ordered_observed[observed_index][0],
                )
            )
            theoretical_index += 1
            observed_index += 1
        elif action == "o":
            observed_index += 1
        else:
            theoretical_index += 1
    return tuple(assignments)


def search_spectrum_candidates(
    spectrum_id: str,
    precursor_mz: float,
    peptide_map: dict[str, tuple[str, ...]],
    observed_mz: Iterable[float],
    observed_intensity: Iterable[float],
    *,
    parameters: SearchParameters = _DEFAULT_PARAMETERS,
) -> tuple[Psm, ...]:
    """Return all deterministic precursor-compatible candidates.

    A missing or non-finite precursor is not silently treated as a match.  This
    research primitive supports one precursor charge at a time; callers that
    cannot provide that metadata must abstain or run a separately declared
    open-search workflow.  Candidates are returned in the same total order used
    by target/decoy competition so the caller can retain an auditable receipt.
    """
    if parameters.require_precursor_mz and (not isfinite(precursor_mz) or precursor_mz <= 0):
        return ()
    mz = tuple(observed_mz)
    intensity = tuple(observed_intensity)
    if len(mz) != len(intensity):
        raise ValueError("observed m/z and intensity lengths differ")
    if any(not isfinite(value) or value < 0 for value in mz):
        return ()
    if any(not isfinite(value) or value < 0 for value in intensity):
        return ()
    norm = hypot(*intensity) if intensity else 0.0
    all_candidates: list[Psm] = []
    for peptide, accessions in peptide_map.items():
        if not peptide:
            continue
        try:
            parsed = parse_modified_peptide(
                peptide, allowed_modifications=parameters.allowed_modifications
            )
        except ValueError:
            continue
        if len(parsed.modifications) > parameters.max_variable_modifications:
            continue
        if parameters.require_precursor_mz:
            theoretical_precursor = _precursor_mz(
                peptide,
                parameters.precursor_charge,
                allowed_modifications=parameters.allowed_modifications,
            )
            ppm_error = (
                abs(precursor_mz - theoretical_precursor) / theoretical_precursor * 1_000_000
            )
            if ppm_error > parameters.precursor_tolerance_ppm:
                continue
        fragments = _fragments(peptide, allowed_modifications=parameters.allowed_modifications)
        theoretical = fragments[0] + fragments[1]
        assignments = _assign_fragment_peaks(theoretical, mz, parameters.fragment_tolerance_da)
        matched = len(assignments)
        intensity_score = 0.0
        matched_intensity = 0.0
        fragment_errors: list[float] = []
        for theoretical_index, observed_index in assignments:
            theoretical_value = theoretical[theoretical_index]
            observed = mz[observed_index]
            matched_intensity += intensity[observed_index]
            error = abs(observed - theoretical_value)
            fragment_errors.append(error)
            intensity_score += intensity[observed_index] / (1.0 + error)
        if matched < parameters.min_matched_ions:
            continue
        candidate = Psm(
            spectrum_id=spectrum_id,
            peptide=peptide,
            protein_accessions=tuple(accessions),
            score=matched + (intensity_score / norm if norm else 0.0),
            matched_ions=matched,
            decoy=all(accession.startswith(parameters.decoy_prefix) for accession in accessions),
            matched_intensity=matched_intensity,
            mean_fragment_error_da=sum(fragment_errors) / len(fragment_errors),
            precursor_error_ppm=(
                abs(precursor_mz - theoretical_precursor) / theoretical_precursor * 1_000_000
                if parameters.require_precursor_mz
                else None
            ),
            target_decoy_collision=(
                any(accession.startswith(parameters.decoy_prefix) for accession in accessions)
                and not all(
                    accession.startswith(parameters.decoy_prefix) for accession in accessions
                )
            ),
        )
        all_candidates.append(candidate)
    return tuple(sorted(all_candidates, key=_competition_sort_key, reverse=True))


def search_spectrum(
    spectrum_id: str,
    precursor_mz: float,
    peptide_map: dict[str, tuple[str, ...]],
    observed_mz: Iterable[float],
    observed_intensity: Iterable[float],
    *,
    parameters: SearchParameters = _DEFAULT_PARAMETERS,
) -> Psm | None:
    """Return the best candidate while preserving the legacy single-PSM API."""

    candidates = search_spectrum_candidates(
        spectrum_id,
        precursor_mz,
        peptide_map,
        observed_mz,
        observed_intensity,
        parameters=parameters,
    )
    return candidates[0] if candidates else None


def target_decoy_qvalues(psms: Iterable[Psm], *, decoy_prefix: str = "DECOY_") -> tuple[Psm, ...]:
    _validate_decoy_prefix(decoy_prefix)
    winners: dict[str, Psm] = {}
    for psm in psms:
        _validate_target_decoy_psm(psm, decoy_prefix=decoy_prefix)
        if not isfinite(psm.score) or psm.score < 0:
            raise ValueError("PSM scores must be finite and non-negative")
        current = winners.get(psm.spectrum_id)
        if current is None or _competition_sort_key(psm) > _competition_sort_key(current):
            winners[psm.spectrum_id] = psm
    # Equal-score winners from different spectra are still indistinguishable
    # target/decoy evidence.  Process collision and pure-decoy winners before
    # targets so a lexical spectrum ID cannot manufacture a zero q-value.
    ordered = sorted(
        winners.values(),
        key=lambda value: (
            -value.score,
            -int(value.target_decoy_collision),
            -int(value.decoy),
            value.spectrum_id,
            value.peptide,
            value.protein_accessions,
        ),
    )
    has_decoy_evidence = any(psm.decoy or psm.target_decoy_collision for psm in ordered)
    decoys = 0
    targets = 0
    raw: list[tuple[Psm, float]] = []
    for psm in ordered:
        decoys += int(psm.decoy or psm.target_decoy_collision)
        targets += int(not psm.decoy and not psm.target_decoy_collision)
        raw.append((psm, decoys / max(targets, 1)))
    running = 1.0
    output: list[Psm] = []
    for psm, value in reversed(raw):
        running = min(running, value)
        output.append(
            replace(
                psm,
                q_value=(
                    None
                    if psm.decoy or psm.target_decoy_collision or not has_decoy_evidence
                    else running
                ),
            )
        )
    return tuple(reversed(output))


def summarize_target_decoy(
    psms: Iterable[Psm], *, q_value_threshold: float, decoy_prefix: str = "DECOY_"
) -> FdrSummary:
    """Return replayable winner-level FDR evidence for a declared threshold."""

    if not isfinite(q_value_threshold) or not 0 <= q_value_threshold <= 1:
        raise ValueError("q_value_threshold must be finite and between zero and one")
    scored = target_decoy_qvalues(psms, decoy_prefix=decoy_prefix)
    target_winners = sum(not item.decoy and not item.target_decoy_collision for item in scored)
    decoy_winners = sum(item.decoy for item in scored)
    collision_winners = sum(item.target_decoy_collision for item in scored)
    accepted = tuple(
        item
        for item in scored
        if (
            not item.decoy
            and not item.target_decoy_collision
            and item.q_value is not None
            and item.q_value <= q_value_threshold
        )
    )
    accepted_q_values = tuple(item.q_value for item in accepted if item.q_value is not None)
    return FdrSummary(
        method="winner-per-spectrum-target-decoy-collision-abstain-ties-4",
        spectrum_winners=len(scored),
        target_winners=target_winners,
        decoy_winners=decoy_winners,
        collision_winners=collision_winners,
        accepted_targets=len(accepted),
        q_value_threshold=q_value_threshold,
        max_accepted_q_value=max(accepted_q_values) if accepted_q_values else None,
        decoy_to_target_ratio=(
            (decoy_winners + collision_winners) / target_winners if target_winners else 0.0
        ),
    )
