"""Ambiguity-preserving protein-group inference from peptide evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProteinGroup:
    accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]


def infer_protein_groups(
    peptide_to_proteins: dict[str, tuple[str, ...]],
) -> tuple[ProteinGroup, ...]:
    """Apply deterministic parsimony while retaining shared-peptide ambiguity."""
    remaining = {
        peptide: set(proteins) for peptide, proteins in peptide_to_proteins.items() if proteins
    }
    groups: list[ProteinGroup] = []
    while remaining:
        counts: dict[str, set[str]] = {}
        for peptide, proteins in remaining.items():
            for protein in proteins:
                counts.setdefault(protein, set()).add(peptide)
        best_count = max(len(peptides) for peptides in counts.values())
        chosen = min(protein for protein, peptides in counts.items() if len(peptides) == best_count)
        covered = {peptide for peptide, proteins in remaining.items() if chosen in proteins}
        accessions = tuple(
            sorted({protein for peptide in covered for protein in remaining[peptide]})
        )
        unique = tuple(sorted(peptide for peptide in covered if len(remaining[peptide]) == 1))
        shared = tuple(sorted(peptide for peptide in covered if len(remaining[peptide]) > 1))
        groups.append(ProteinGroup(accessions, unique, shared))
        for peptide in covered:
            remaining.pop(peptide, None)
    return tuple(groups)
