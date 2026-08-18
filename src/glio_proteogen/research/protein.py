"""Ambiguity-preserving protein-group inference from peptide evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .search import Psm


@dataclass(frozen=True, slots=True)
class ProteinGroup:
    accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProteinGroupCandidate:
    """A target/decoy-aware protein-group candidate.

    This is deliberately an auditable research candidate, not a calibrated
    protein probability.  Collision groups are retained with a null q-value
    and can never be promoted to a reportable group.
    """

    accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]
    score: float
    supporting_psms: int
    status: str
    q_value: float | None
    acceptance: str
    identifiability: str = "unique_peptide_supported"

    def as_dict(self) -> dict[str, object]:
        return {
            "acceptance": self.acceptance,
            "accessions": list(self.accessions),
            "identifiability": self.identifiability,
            "q_value": self.q_value,
            "score": self.score,
            "shared_peptides": list(self.shared_peptides),
            "status": self.status,
            "supporting_psms": self.supporting_psms,
            "unique_peptides": list(self.unique_peptides),
        }


@dataclass(frozen=True, slots=True)
class ProteinGroupFdrSummary:
    """Monotone target/decoy evidence at the protein-group level."""

    method: str
    candidates: int
    target_candidates: int
    decoy_candidates: int
    collision_candidates: int
    accepted_targets: int
    q_value_threshold: float
    max_accepted_q_value: float | None
    decoy_to_target_ratio: float
    input_psms: int = 0
    unique_spectra: int = 0
    duplicate_spectrum_psms: int = 0
    competition_digest: str = ""
    shared_peptide_candidates: int = 0
    shared_only_candidates: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_targets": self.accepted_targets,
            "candidates": self.candidates,
            "collision_candidates": self.collision_candidates,
            "decoy_candidates": self.decoy_candidates,
            "decoy_to_target_ratio": self.decoy_to_target_ratio,
            "duplicate_spectrum_psms": self.duplicate_spectrum_psms,
            "competition_digest": self.competition_digest,
            "input_psms": self.input_psms,
            "max_accepted_q_value": self.max_accepted_q_value,
            "method": self.method,
            "q_value_threshold": self.q_value_threshold,
            "target_candidates": self.target_candidates,
            "shared_only_candidates": self.shared_only_candidates,
            "shared_peptide_candidates": self.shared_peptide_candidates,
            "unique_spectra": self.unique_spectra,
        }


def infer_protein_groups(
    peptide_to_proteins: dict[str, tuple[str, ...]],
) -> tuple[ProteinGroup, ...]:
    """Return disjoint bipartite components while retaining shared-peptide ambiguity.

    A greedy protein parsimony pass can emit overlapping groups when a shared
    peptide is consumed by one representative and a unique peptide later
    selects another protein.  Components give every protein and peptide exactly
    one deterministic group; shared peptides remain explicitly marked instead
    of being silently assigned to one protein.
    """
    remaining = {
        peptide: {protein for protein in proteins if protein}
        for peptide, proteins in peptide_to_proteins.items()
        if proteins and any(protein for protein in proteins)
    }
    groups: list[ProteinGroup] = []
    while remaining:
        seed = min(remaining)
        component_peptides = {seed}
        component_proteins: set[str] = set()
        frontier = [seed]
        while frontier:
            peptide = frontier.pop()
            for protein in remaining[peptide]:
                if protein in component_proteins:
                    continue
                component_proteins.add(protein)
                linked = [
                    linked_peptide
                    for linked_peptide, proteins in remaining.items()
                    if protein in proteins and linked_peptide not in component_peptides
                ]
                component_peptides.update(linked)
                frontier.extend(linked)
        accessions = tuple(sorted(component_proteins))
        unique = tuple(
            sorted(peptide for peptide in component_peptides if len(remaining[peptide]) == 1)
        )
        shared = tuple(
            sorted(peptide for peptide in component_peptides if len(remaining[peptide]) > 1)
        )
        groups.append(ProteinGroup(accessions, unique, shared))
        for peptide in component_peptides:
            remaining.pop(peptide, None)
    return tuple(groups)


def infer_protein_group_candidates(
    psms: tuple[Psm, ...], *, q_value_threshold: float, decoy_prefix: str = "DECOY_"
) -> tuple[tuple[ProteinGroupCandidate, ...], ProteinGroupFdrSummary]:
    """Build deterministic group candidates from *all* scored PSMs.

    Group score is the maximum supporting PSM score.  Target/decoy groups are
    counted separately and receive monotone q-values; mixed target/decoy
    groups are collision evidence and are conservatively abstained.  No group
    is accepted merely because its best peptide passed peptide-level FDR.
    """

    if not isfinite(q_value_threshold) or not 0 <= q_value_threshold <= 1:
        raise ValueError("q_value_threshold must be finite and between zero and one")
    _validate_decoy_prefix(decoy_prefix)
    input_psms, psms, competition_digest = _prepare_group_psms(psms, decoy_prefix=decoy_prefix)
    peptide_to_proteins: dict[str, set[str]] = {}
    for psm in psms:
        if not isinstance(psm.peptide, str) or not psm.peptide:
            raise ValueError("PSM peptide must be a non-empty string")
        if not isfinite(psm.score) or psm.score < 0:
            raise ValueError("PSM scores must be finite and non-negative")
        peptide_to_proteins.setdefault(psm.peptide, set()).update(psm.protein_accessions)
    groups = infer_protein_groups(
        {peptide: tuple(sorted(accessions)) for peptide, accessions in peptide_to_proteins.items()}
    )
    candidates: list[ProteinGroupCandidate] = []
    for group in groups:
        supporting = tuple(
            psm for psm in psms if set(psm.protein_accessions).intersection(group.accessions)
        )
        if not supporting:
            continue
        has_decoy = any(accession.startswith(decoy_prefix) for accession in group.accessions)
        has_target = any(not accession.startswith(decoy_prefix) for accession in group.accessions)
        status = "collision" if has_decoy and has_target else "decoy" if has_decoy else "target"
        candidates.append(
            ProteinGroupCandidate(
                accessions=group.accessions,
                unique_peptides=group.unique_peptides,
                shared_peptides=group.shared_peptides,
                score=max(item.score for item in supporting),
                supporting_psms=len(supporting),
                status=status,
                q_value=None,
                acceptance="abstained" if status == "collision" else "pending",
                identifiability=(
                    "target_decoy_collision"
                    if status == "collision"
                    else "shared_only_ambiguous"
                    if not group.unique_peptides
                    else "unique_peptide_supported"
                ),
            )
        )
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item.score,
            {"target": 0, "decoy": 1, "collision": 2}[item.status],
            item.accessions,
        ),
    )
    decoys = 0
    targets = 0
    raw: list[tuple[ProteinGroupCandidate, float | None]] = []
    for candidate in ordered:
        if candidate.status == "collision":
            # A mixed target/decoy group is never reportable, but it is still
            # decoy evidence for conservative group-level FDR estimation.
            decoys += 1
            raw.append((candidate, None))
            continue
        decoys += int(candidate.status == "decoy")
        targets += int(candidate.status == "target")
        raw.append((candidate, decoys / max(targets, 1)))
    running = 1.0
    by_accessions: dict[tuple[str, ...], ProteinGroupCandidate] = {}
    for candidate, value in reversed(raw):
        if value is not None:
            running = min(running, value)
        q_value = None if candidate.status != "target" else running
        acceptance = (
            "accepted"
            if (
                candidate.status == "target"
                and candidate.identifiability == "unique_peptide_supported"
                and q_value is not None
                and q_value <= q_value_threshold
            )
            else "abstained"
            if candidate.identifiability == "shared_only_ambiguous"
            else "rejected"
            if candidate.status != "collision"
            else "abstained"
        )
        by_accessions[candidate.accessions] = ProteinGroupCandidate(
            accessions=candidate.accessions,
            unique_peptides=candidate.unique_peptides,
            shared_peptides=candidate.shared_peptides,
            score=candidate.score,
            supporting_psms=candidate.supporting_psms,
            status=candidate.status,
            q_value=q_value,
            acceptance=acceptance,
            identifiability=candidate.identifiability,
        )
    finalized = tuple(sorted(by_accessions.values(), key=lambda item: item.accessions))
    accepted_q = tuple(
        item.q_value
        for item in finalized
        if item.acceptance == "accepted" and item.q_value is not None
    )
    summary = ProteinGroupFdrSummary(
        method="max-psm-score-monotone-group-target-decoy-collision-abstain-3",
        candidates=len(finalized),
        target_candidates=sum(item.status == "target" for item in finalized),
        decoy_candidates=sum(item.status == "decoy" for item in finalized),
        collision_candidates=sum(item.status == "collision" for item in finalized),
        accepted_targets=len(accepted_q),
        q_value_threshold=q_value_threshold,
        max_accepted_q_value=max(accepted_q) if accepted_q else None,
        decoy_to_target_ratio=(
            sum(item.status in {"decoy", "collision"} for item in finalized)
            / sum(item.status == "target" for item in finalized)
            if any(item.status == "target" for item in finalized)
            else 0.0
        ),
        input_psms=len(input_psms),
        unique_spectra=len(psms),
        duplicate_spectrum_psms=len(input_psms) - len(psms),
        competition_digest=competition_digest,
        shared_peptide_candidates=sum(bool(item.shared_peptides) for item in finalized),
        shared_only_candidates=sum(
            item.identifiability == "shared_only_ambiguous" for item in finalized
        ),
    )
    return finalized, summary


def _group_competition_key(value: Psm) -> tuple[float, bool, bool, str, tuple[str, ...]]:
    """Order group contenders with target and non-collision evidence first on ties."""

    return (
        value.score,
        not value.target_decoy_collision,
        not value.decoy,
        value.peptide,
        value.protein_accessions,
    )


def _prepare_group_psms(
    psms: tuple[Psm, ...],
    *,
    decoy_prefix: str,
) -> tuple[tuple[Psm, ...], tuple[Psm, ...], str]:
    """Validate contenders, select one winner per spectrum, and digest all inputs."""

    input_psms = tuple(psms)
    winners_by_spectrum: dict[str, Psm] = {}
    contenders_by_spectrum: dict[str, list[Psm]] = {}
    for psm in input_psms:
        _validate_group_psm(psm, decoy_prefix=decoy_prefix)
        contenders_by_spectrum.setdefault(psm.spectrum_id, []).append(psm)
        current = winners_by_spectrum.get(psm.spectrum_id)
        if current is None or _group_competition_key(psm) > _group_competition_key(current):
            winners_by_spectrum[psm.spectrum_id] = psm
    winners = tuple(winners_by_spectrum[spectrum_id] for spectrum_id in sorted(winners_by_spectrum))
    digest_payload = [
        {
            "spectrum_id": spectrum_id,
            "candidates": [
                _psm_payload(item)
                for item in sorted(contenders, key=_group_competition_key, reverse=True)
            ],
        }
        for spectrum_id, contenders in sorted(contenders_by_spectrum.items())
    ]
    digest = sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return input_psms, winners, digest


def _validate_group_psm(psm: Psm, *, decoy_prefix: str) -> None:
    if not isinstance(psm.spectrum_id, str) or not psm.spectrum_id:
        raise ValueError("PSM spectrum_id must be a non-empty string")
    if not isinstance(psm.protein_accessions, tuple) or not psm.protein_accessions:
        raise ValueError("PSM must declare at least one protein accession")
    if any(not isinstance(accession, str) or not accession for accession in psm.protein_accessions):
        raise ValueError("PSM protein accessions must be non-empty strings")
    if not isfinite(psm.score) or psm.score < 0:
        raise ValueError("PSM scores must be finite and non-negative")
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


def _psm_payload(value: Psm) -> dict[str, object]:
    return {
        "decoy": value.decoy,
        "matched_intensity": value.matched_intensity,
        "matched_ions": value.matched_ions,
        "mean_fragment_error_da": value.mean_fragment_error_da,
        "peptide": value.peptide,
        "precursor_error_ppm": value.precursor_error_ppm,
        "protein_accessions": list(value.protein_accessions),
        "q_value": value.q_value,
        "score": value.score,
        "spectrum_id": value.spectrum_id,
        "target_decoy_collision": value.target_decoy_collision,
    }
