"""Bounded, explicit peptide modification semantics for research search.

This module intentionally implements a small declared catalogue rather than an
open-ended modification parser.  A modified peptide is only searchable when its
ProForma-like residue annotation names a supported UNIMOD entry and the caller
declares that entry in the search controls.  That makes mass shifts visible in
the precursor/fragment calculation and replay configuration instead of silently
turning unknown annotations into arbitrary mass deltas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from math import isfinite


@dataclass(frozen=True, slots=True)
class ModificationSpec:
    """One supported residue-local mass modification."""

    identifier: str
    name: str
    delta_mass: float
    residues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PeptideModification:
    """A modification attached to one zero-based residue position."""

    position: int
    identifier: str
    delta_mass: float


@dataclass(frozen=True, slots=True)
class ParsedPeptide:
    """Mass-ready representation of a strictly parsed peptide annotation."""

    sequence: str
    residue_masses: tuple[float, ...]
    modifications: tuple[PeptideModification, ...]


_CATALOGUE: dict[str, ModificationSpec] = {
    "UNIMOD:4": ModificationSpec("UNIMOD:4", "Carbamidomethyl", 57.021464, ("C",)),
    "UNIMOD:21": ModificationSpec("UNIMOD:21", "Phospho", 79.966331, ("S", "T", "Y")),
    "UNIMOD:35": ModificationSpec("UNIMOD:35", "Oxidation", 15.994915, ("M",)),
}
_TOKEN = re.compile(r"UNIMOD:[0-9]+\Z")


def supported_modifications() -> tuple[ModificationSpec, ...]:
    """Return the immutable, deterministic catalogue exposed by this lane."""

    return tuple(_CATALOGUE[key] for key in sorted(_CATALOGUE))


def normalize_modification_rules(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Validate and canonicalize caller-declared variable modification rules."""

    if values is None:
        return ()
    if not isinstance(values, (tuple, list)):
        raise TypeError("modification rules must be a tuple or list")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not _TOKEN.fullmatch(value.upper()):
            raise ValueError("modification rules must use UNIMOD:<integer> identifiers")
        identifier = value.upper()
        if identifier not in _CATALOGUE:
            raise ValueError(f"unsupported research modification: {identifier}")
        if identifier in normalized:
            raise ValueError("modification rules must be unique")
        normalized.append(identifier)
    return tuple(sorted(normalized))


def parse_modified_peptide(
    peptide: str,
    *,
    allowed_modifications: tuple[str, ...] = (),
) -> ParsedPeptide:
    """Parse residue-local ``M[UNIMOD:35]PEPTIDE`` annotations.

    N-/C-terminal and arbitrary numeric mass annotations are intentionally
    rejected.  The explicit catalogue and residue compatibility check prevent a
    caller from claiming a mass shift whose chemical placement is unknown.
    """

    if not isinstance(peptide, str) or not peptide:
        raise ValueError("peptide must be non-empty text")
    allowed = set(normalize_modification_rules(allowed_modifications))
    sequence: list[str] = []
    masses: list[float] = []
    modifications: list[PeptideModification] = []
    index = 0
    while index < len(peptide):
        residue = peptide[index]
        if residue not in _RESIDUE_MASS:
            raise ValueError("peptide contains an unsupported residue or modification syntax")
        position = len(sequence)
        sequence.append(residue)
        masses.append(_RESIDUE_MASS[residue])
        index += 1
        while index < len(peptide) and peptide[index] == "[":
            end = peptide.find("]", index + 1)
            if end < 0:
                raise ValueError("peptide modification annotation is not closed")
            identifier = peptide[index + 1 : end].upper()
            spec = _CATALOGUE.get(identifier)
            if spec is None or not _TOKEN.fullmatch(identifier):
                raise ValueError("peptide modification is outside the supported catalogue")
            if identifier not in allowed:
                raise ValueError(f"peptide modification {identifier} was not declared")
            if residue not in spec.residues:
                raise ValueError(
                    f"modification {identifier} is incompatible with residue {residue}"
                )
            if any(item.position == position for item in modifications):
                raise ValueError("multiple modifications on one residue are not supported")
            masses[position] += spec.delta_mass
            modifications.append(PeptideModification(position, identifier, spec.delta_mass))
            index = end + 1
    if any(not isfinite(value) or value <= 0 for value in masses):
        raise ValueError("peptide residue masses must be finite and positive")
    return ParsedPeptide(peptide, tuple(masses), tuple(modifications))


def expand_peptide(
    peptide: str,
    *,
    allowed_modifications: tuple[str, ...] = (),
    max_variable_modifications: int = 0,
    max_variants: int = 10_000,
) -> tuple[str, ...]:
    """Enumerate bounded residue-local variable-modification variants.

    The unmodified peptide is always first.  Variant generation is deterministic
    and fails closed when a declared search space would exceed ``max_variants``.
    """

    rules = normalize_modification_rules(allowed_modifications)
    if type(max_variable_modifications) is not int or not 0 <= max_variable_modifications <= 3:
        raise ValueError("max_variable_modifications must be between zero and three")
    if type(max_variants) is not int or not 1 <= max_variants <= 100_000:
        raise ValueError("max_variants is outside the supported research limit")
    base = parse_modified_peptide(peptide, allowed_modifications=rules)
    if base.modifications:
        return (peptide,)
    if not rules or max_variable_modifications == 0:
        return (peptide,)
    choices: list[tuple[str | None, ...]] = []
    for residue in peptide:
        eligible = tuple(
            identifier for identifier in rules if residue in _CATALOGUE[identifier].residues
        )
        choices.append((None, *eligible))
    variant_count = 0
    output: list[str] = []
    for assignment in product(*choices):
        count = sum(item is not None for item in assignment)
        if count > max_variable_modifications:
            continue
        variant_count += 1
        if variant_count > max_variants:
            raise ValueError("variable modification search space exceeds the research limit")
        output.append(
            "".join(
                residue if identifier is None else f"{residue}[{identifier}]"
                for residue, identifier in zip(peptide, assignment, strict=True)
            )
        )
    return tuple(output)


def expand_peptide_map(
    peptide_map: dict[str, tuple[str, ...]],
    *,
    allowed_modifications: tuple[str, ...] = (),
    max_variable_modifications: int = 0,
) -> dict[str, tuple[str, ...]]:
    """Expand a digested peptide map while retaining accession ambiguity."""

    output: dict[str, set[str]] = {}
    for peptide, accessions in peptide_map.items():
        for variant in expand_peptide(
            peptide,
            allowed_modifications=allowed_modifications,
            max_variable_modifications=max_variable_modifications,
        ):
            output.setdefault(variant, set()).update(accessions)
    return {peptide: tuple(sorted(output[peptide])) for peptide in sorted(output)}


_RESIDUE_MASS = {
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
