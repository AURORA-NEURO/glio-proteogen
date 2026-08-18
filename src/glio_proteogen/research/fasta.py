"""Streaming FASTA reading and deterministic tryptic digestion."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class FastaEntry:
    accession: str
    sequence: str


def read_fasta(source: bytes | str | BinaryIO) -> tuple[FastaEntry, ...]:
    if isinstance(source, bytes):
        text = source.decode("utf-8")
    elif isinstance(source, str):
        text = source
    else:
        value = source.read()
        text = value.decode("utf-8") if isinstance(value, bytes) else value
    entries: list[FastaEntry] = []
    accession: str | None = None
    residues: list[str] = []
    alphabet = set("ABCDEFGHIKLMNOPQRSTUVWYXZ*")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if accession is not None:
                if not residues:
                    raise ValueError("FASTA entry has no residues")
                entries.append(FastaEntry(accession, "".join(residues)))
            accession = line[1:].split(None, 1)[0]
            if not accession:
                raise ValueError("FASTA header has no accession")
            residues = []
        elif accession is None or any(char not in alphabet for char in line):
            raise ValueError("invalid FASTA sequence")
        else:
            residues.append(line.upper())
    if accession is not None:
        if not residues:
            raise ValueError("FASTA entry has no residues")
        entries.append(FastaEntry(accession, "".join(residues)))
    if not entries:
        raise ValueError("FASTA contains no entries")
    return tuple(entries)


def digest_trypsin(
    entries: Iterable[FastaEntry],
    *,
    missed_cleavages: int = 0,
    min_length: int = 7,
    max_length: int = 40,
) -> dict[str, tuple[str, ...]]:
    if not 0 <= missed_cleavages <= 3 or not 1 <= min_length <= max_length <= 200:
        raise ValueError("invalid digestion limits")
    peptide_map: dict[str, set[str]] = {}
    for entry in entries:
        cuts = [0]
        for index, residue in enumerate(entry.sequence[:-1], start=1):
            if residue in "KR" and entry.sequence[index] != "P":
                cuts.append(index)
        cuts.append(len(entry.sequence))
        for start_index, start in enumerate(cuts[:-1]):
            for end_index in range(
                start_index + 1, min(len(cuts), start_index + missed_cleavages + 2)
            ):
                peptide = entry.sequence[start : cuts[end_index]]
                if min_length <= len(peptide) <= max_length and "*" not in peptide:
                    peptide_map.setdefault(peptide, set()).add(entry.accession)
    return {
        peptide: tuple(sorted(accessions)) for peptide, accessions in sorted(peptide_map.items())
    }
