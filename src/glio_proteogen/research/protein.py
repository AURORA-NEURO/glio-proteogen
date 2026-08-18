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
