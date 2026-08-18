"""Ambiguity-preserving protein-group inference from peptide evidence."""

from __future__ import annotations

from dataclasses import dataclass
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

    def as_dict(self) -> dict[str, object]:
        return {
            "acceptance": self.acceptance,
            "accessions": list(self.accessions),
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

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_targets": self.accepted_targets,
            "candidates": self.candidates,
            "collision_candidates": self.collision_candidates,
            "decoy_candidates": self.decoy_candidates,
            "decoy_to_target_ratio": self.decoy_to_target_ratio,
            "max_accepted_q_value": self.max_accepted_q_value,
            "method": self.method,
            "q_value_threshold": self.q_value_threshold,
            "target_candidates": self.target_candidates,
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
    psms: tuple[Psm, ...], *, q_value_threshold: float
) -> tuple[tuple[ProteinGroupCandidate, ...], ProteinGroupFdrSummary]:
    """Build deterministic group candidates from *all* scored PSMs.

    Group score is the maximum supporting PSM score.  Target/decoy groups are
    counted separately and receive monotone q-values; mixed target/decoy
    groups are collision evidence and are conservatively abstained.  No group
    is accepted merely because its best peptide passed peptide-level FDR.
    """

    if not isfinite(q_value_threshold) or not 0 <= q_value_threshold <= 1:
        raise ValueError("q_value_threshold must be finite and between zero and one")
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
        has_decoy = any(accession.startswith("DECOY_") for accession in group.accessions)
        has_target = any(not accession.startswith("DECOY_") for accession in group.accessions)
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
            if candidate.status == "target" and q_value is not None and q_value <= q_value_threshold
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
        )
    finalized = tuple(sorted(by_accessions.values(), key=lambda item: item.accessions))
    accepted_q = tuple(
        item.q_value
        for item in finalized
        if item.acceptance == "accepted" and item.q_value is not None
    )
    summary = ProteinGroupFdrSummary(
        method="max-psm-score-monotone-group-target-decoy-collision-abstain-1",
        candidates=len(finalized),
        target_candidates=sum(item.status == "target" for item in finalized),
        decoy_candidates=sum(item.status == "decoy" for item in finalized),
        collision_candidates=sum(item.status == "collision" for item in finalized),
        accepted_targets=len(accepted_q),
        q_value_threshold=q_value_threshold,
        max_accepted_q_value=max(accepted_q) if accepted_q else None,
        decoy_to_target_ratio=(
            sum(item.status == "decoy" for item in finalized)
            / sum(item.status == "target" for item in finalized)
            if any(item.status == "target" for item in finalized)
            else 0.0
        ),
    )
    return finalized, summary
