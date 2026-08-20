"""Streaming FASTA reading and deterministic tryptic digestion."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO

DEFAULT_FASTA_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_FASTA_MAX_ENTRIES = 1_000_000
DEFAULT_FASTA_MAX_RESIDUES = 100_000_000
_MAX_FASTA_BYTES = 512 * 1024 * 1024
_MAX_FASTA_ENTRIES = 2_000_000
_MAX_FASTA_RESIDUES = 500_000_000
_FASTA_ALPHABET = frozenset("ABCDEFGHIKLMNOPQRSTUVWYXZ*")


@dataclass(frozen=True, slots=True)
class FastaEntry:
    accession: str
    sequence: str


@dataclass(frozen=True, slots=True)
class SearchSpaceReceipt:
    """Content-addressed record of the exact research search space.

    A peptide-level FDR estimate is only interpretable relative to the target and
    decoy sequences that were actually searched.  This receipt makes that search
    space explicit without promoting the research result to a calibrated protein
    probability or changing any governed module ABI.
    """

    version: str
    decoy_strategy: str
    decoy_prefix: str
    target_entries: int
    declared_decoy_entries: int
    generated_decoy_entries: int
    target_peptides: int
    decoy_peptides: int
    collision_peptides: int
    peptide_count: int
    digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "collision_peptides": self.collision_peptides,
            "decoy_prefix": self.decoy_prefix,
            "decoy_strategy": self.decoy_strategy,
            "declared_decoy_entries": self.declared_decoy_entries,
            "decoy_peptides": self.decoy_peptides,
            "digest": self.digest,
            "generated_decoy_entries": self.generated_decoy_entries,
            "peptide_count": self.peptide_count,
            "target_entries": self.target_entries,
            "target_peptides": self.target_peptides,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class SearchSpace:
    """Immutable peptide map plus the receipt that describes its construction."""

    peptide_map: tuple[tuple[str, tuple[str, ...]], ...]
    receipt: SearchSpaceReceipt

    def as_map(self) -> dict[str, tuple[str, ...]]:
        return dict(self.peptide_map)


def _read_fasta_source(source: bytes | str | BinaryIO, max_bytes: int) -> str:
    if type(max_bytes) is not int or not 0 < max_bytes <= _MAX_FASTA_BYTES:
        raise ValueError("FASTA byte limit is outside the bounded range")
    if isinstance(source, bytes):
        payload = source
    elif isinstance(source, str):
        payload = source.encode("utf-8")
    else:
        # ``BinaryIO.read(n)`` may legally return fewer than ``n`` bytes
        # before EOF (for example, a throttled or non-seekable source).  A
        # single bounded read would turn a valid FASTA prefix into a
        # self-consistent but incomplete search space.
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = max_bytes - total
            value = source.read(min(65_536, remaining + 1))
            if value == b"":
                break
            if not isinstance(value, bytes):
                raise TypeError("FASTA binary stream must return bytes")
            total += len(value)
            if total > max_bytes:
                raise ValueError("FASTA source exceeds the research byte limit")
            chunks.append(value)
        payload = b"".join(chunks)
    if len(payload) > max_bytes:
        raise ValueError("FASTA source exceeds the research byte limit")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("FASTA source is not valid UTF-8") from error


def read_fasta(
    source: bytes | str | BinaryIO,
    *,
    max_bytes: int = DEFAULT_FASTA_MAX_BYTES,
    max_entries: int = DEFAULT_FASTA_MAX_ENTRIES,
    max_residues: int = DEFAULT_FASTA_MAX_RESIDUES,
) -> tuple[FastaEntry, ...]:
    """Read bounded FASTA text with explicit entry and residue ceilings."""

    if type(max_entries) is not int or not 0 < max_entries <= _MAX_FASTA_ENTRIES:
        raise ValueError("FASTA entry limit is outside the bounded range")
    if type(max_residues) is not int or not 0 < max_residues <= _MAX_FASTA_RESIDUES:
        raise ValueError("FASTA residue limit is outside the bounded range")
    text = _read_fasta_source(source, max_bytes)
    entries: list[FastaEntry] = []
    seen_accessions: set[str] = set()
    accession: str | None = None
    residues: list[str] = []
    residue_count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if accession is not None:
                if not residues:
                    raise ValueError("FASTA entry has no residues")
                if accession in seen_accessions:
                    raise ValueError("FASTA contains duplicate accessions")
                seen_accessions.add(accession)
                entries.append(FastaEntry(accession, "".join(residues)))
                if len(entries) > max_entries:
                    raise ValueError("FASTA entry count exceeds the research limit")
            header = line[1:].split(None, 1)
            if not header or not header[0]:
                raise ValueError("FASTA header has no accession")
            accession = header[0]
            residues = []
        elif accession is None or any(char not in _FASTA_ALPHABET for char in line):
            raise ValueError("invalid FASTA sequence")
        else:
            residues.append(line.upper())
            residue_count += len(line)
            if residue_count > max_residues:
                raise ValueError("FASTA residue count exceeds the research limit")
    if accession is not None:
        if not residues:
            raise ValueError("FASTA entry has no residues")
        if accession in seen_accessions:
            raise ValueError("FASTA contains duplicate accessions")
        seen_accessions.add(accession)
        entries.append(FastaEntry(accession, "".join(residues)))
        if len(entries) > max_entries:
            raise ValueError("FASTA entry count exceeds the research limit")
    if not entries:
        raise ValueError("FASTA contains no entries")
    return tuple(entries)


def build_search_space(
    entries: Iterable[FastaEntry],
    *,
    decoy_strategy: str = "caller_declared",
    decoy_prefix: str = "DECOY_",
    missed_cleavages: int = 0,
    min_length: int = 7,
    max_length: int = 40,
) -> SearchSpace:
    """Build a deterministic target/decoy peptide map and immutable receipt.

    ``caller_declared`` searches only the supplied FASTA entries and requires
    decoy accessions to carry ``decoy_prefix``.  ``reverse_protein`` adds one
    reversed sequence per target entry, using a namespaced accession.  Reversed
    sequences are intentionally simple and fully declared: this is a research
    target/decoy construction primitive, not a claim that the generated decoy
    distribution is universally appropriate for every instrument or search tool.
    """

    if decoy_strategy not in {"caller_declared", "reverse_protein"}:
        raise ValueError("unsupported decoy_strategy")
    if (
        not isinstance(decoy_prefix, str)
        or not 1 <= len(decoy_prefix) <= 32
        or any(character.isspace() or ord(character) < 33 for character in decoy_prefix)
    ):
        raise ValueError("decoy_prefix must be a bounded non-whitespace token")
    materialized = tuple(entries)
    if not materialized:
        raise ValueError("search space requires at least one FASTA entry")
    accessions = [entry.accession for entry in materialized]
    if any(not accession for accession in accessions):
        raise ValueError("FASTA accessions must be non-empty")
    if len(set(accessions)) != len(accessions):
        raise ValueError("search space accessions must be unique")
    declared_decoys = tuple(
        entry for entry in materialized if entry.accession.startswith(decoy_prefix)
    )
    targets = tuple(entry for entry in materialized if not entry.accession.startswith(decoy_prefix))
    generated: tuple[FastaEntry, ...] = ()
    if decoy_strategy == "reverse_protein":
        generated = tuple(
            FastaEntry(f"{decoy_prefix}{entry.accession}", entry.sequence[::-1])
            for entry in targets
        )
        existing = {entry.accession for entry in materialized}
        if any(entry.accession in existing for entry in generated):
            raise ValueError("generated decoy accession collides with supplied FASTA")
    all_entries = materialized + generated
    peptide_map = digest_trypsin(
        all_entries,
        missed_cleavages=missed_cleavages,
        min_length=min_length,
        max_length=max_length,
    )
    target_map = (
        digest_trypsin(
            targets,
            missed_cleavages=missed_cleavages,
            min_length=min_length,
            max_length=max_length,
        )
        if targets
        else {}
    )
    decoy_entries = declared_decoys + generated
    decoy_map = (
        digest_trypsin(
            decoy_entries,
            missed_cleavages=missed_cleavages,
            min_length=min_length,
            max_length=max_length,
        )
        if decoy_entries
        else {}
    )
    target_peptides = set(target_map)
    decoy_peptides = set(decoy_map)
    digest_payload = {
        "decoy_entries": [
            {
                "accession": entry.accession,
                "sequence_sha256": sha256(entry.sequence.encode("ascii")).hexdigest(),
            }
            for entry in sorted(decoy_entries, key=lambda item: item.accession)
        ],
        "decoy_prefix": decoy_prefix,
        "decoy_strategy": decoy_strategy,
        "missed_cleavages": missed_cleavages,
        "peptide_map": [list(item) for item in sorted(peptide_map.items())],
        "target_entries": [
            {
                "accession": entry.accession,
                "sequence_sha256": sha256(entry.sequence.encode("ascii")).hexdigest(),
            }
            for entry in sorted(targets, key=lambda item: item.accession)
        ],
        "min_length": min_length,
        "max_length": max_length,
    }
    digest = sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt = SearchSpaceReceipt(
        version="search-space-reverse-decoy-1",
        decoy_strategy=decoy_strategy,
        decoy_prefix=decoy_prefix,
        target_entries=len(targets),
        declared_decoy_entries=len(declared_decoys),
        generated_decoy_entries=len(generated),
        target_peptides=len(target_peptides),
        decoy_peptides=len(decoy_peptides),
        collision_peptides=len(target_peptides.intersection(decoy_peptides)),
        peptide_count=len(peptide_map),
        digest=digest,
    )
    return SearchSpace(tuple(peptide_map.items()), receipt)


def digest_trypsin(
    entries: Iterable[FastaEntry],
    *,
    missed_cleavages: int = 0,
    min_length: int = 7,
    max_length: int = 40,
) -> dict[str, tuple[str, ...]]:
    if (
        type(missed_cleavages) is not int
        or type(min_length) is not int
        or type(max_length) is not int
        or not 0 <= missed_cleavages <= 3
        or not 1 <= min_length <= max_length <= 200
    ):
        raise ValueError("invalid digestion limits")
    peptide_map: dict[str, set[str]] = {}
    for entry in entries:
        for peptide in digest_entry_trypsin(
            entry,
            missed_cleavages=missed_cleavages,
            min_length=min_length,
            max_length=max_length,
        ):
            peptide_map.setdefault(peptide, set()).add(entry.accession)
    return {
        peptide: tuple(sorted(accessions)) for peptide, accessions in sorted(peptide_map.items())
    }


def digest_entry_trypsin(
    entry: FastaEntry,
    *,
    missed_cleavages: int = 0,
    min_length: int = 7,
    max_length: int = 40,
) -> tuple[str, ...]:
    """Digest one entry while preserving the entry boundary.

    Keeping the per-accession digest is important for a decoy receipt: a global
    peptide map loses whether a peptide came from the target, its decoy partner,
    or both.  The implementation uses the same tryptic rules as ``digest_trypsin``
    so search-space provenance cannot silently diverge from the actual search.
    """

    if (
        type(missed_cleavages) is not int
        or type(min_length) is not int
        or type(max_length) is not int
        or not 0 <= missed_cleavages <= 3
        or not 1 <= min_length <= max_length <= 200
    ):
        raise ValueError("invalid digestion limits")
    if (
        type(entry.sequence) is not str
        or not entry.sequence
        or any(character not in _FASTA_ALPHABET for character in entry.sequence)
    ):
        raise ValueError("FASTA sequence contains unsupported characters")
    cuts = [0]
    for index, residue in enumerate(entry.sequence[:-1], start=1):
        if residue in "KR" and entry.sequence[index] != "P":
            cuts.append(index)
    cuts.append(len(entry.sequence))
    peptides: set[str] = set()
    for start_index, start in enumerate(cuts[:-1]):
        for end_index in range(start_index + 1, min(len(cuts), start_index + missed_cleavages + 2)):
            peptide = entry.sequence[start : cuts[end_index]]
            if min_length <= len(peptide) <= max_length and "*" not in peptide:
                peptides.add(peptide)
    return tuple(sorted(peptides))
