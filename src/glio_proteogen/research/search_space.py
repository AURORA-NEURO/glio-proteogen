"""Replay-bound provenance for a target/decoy proteomics search space."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from .fasta import FastaEntry, digest_entry_trypsin

_DECOY_PREFIX = "DECOY_"
_VERSION = "search-space-receipt-1"


@dataclass(frozen=True, slots=True)
class DecoyPair:
    """Per-protein target/decoy pairing and cleavage-aware digest evidence."""

    target_accession: str
    decoy_accession: str
    target_peptides: int
    decoy_peptides: int
    target_residue_count: int
    decoy_residue_count: int
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "decoy_accession": self.decoy_accession,
            "decoy_peptides": self.decoy_peptides,
            "decoy_residue_count": self.decoy_residue_count,
            "status": self.status,
            "target_accession": self.target_accession,
            "target_peptides": self.target_peptides,
            "target_residue_count": self.target_residue_count,
        }


@dataclass(frozen=True, slots=True)
class SearchSpaceReceipt:
    """Immutable receipt for the exact digested target/decoy search space."""

    version: str
    source_sha256: str
    digestion_enzyme: str
    missed_cleavages: int
    min_peptide_length: int
    max_peptide_length: int
    decoy_prefix: str
    target_proteins: int
    decoy_proteins: int
    target_peptides: int
    decoy_peptides: int
    target_decoy_overlap_peptides: int
    paired_proteins: int
    cleavage_compatible_pairs: int
    unmatched_target_proteins: int
    unmatched_decoy_proteins: int
    pairs: tuple[DecoyPair, ...]
    pairing_digest: str
    search_space_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "cleavage_compatible_pairs": self.cleavage_compatible_pairs,
            "decoy_peptides": self.decoy_peptides,
            "decoy_prefix": self.decoy_prefix,
            "decoy_proteins": self.decoy_proteins,
            "digestion_enzyme": self.digestion_enzyme,
            "max_peptide_length": self.max_peptide_length,
            "min_peptide_length": self.min_peptide_length,
            "missed_cleavages": self.missed_cleavages,
            "paired_proteins": self.paired_proteins,
            "pairing_digest": self.pairing_digest,
            "pairs": [item.as_dict() for item in self.pairs],
            "search_space_digest": self.search_space_digest,
            "source_sha256": self.source_sha256,
            "target_decoy_overlap_peptides": self.target_decoy_overlap_peptides,
            "target_peptides": self.target_peptides,
            "target_proteins": self.target_proteins,
            "unmatched_decoy_proteins": self.unmatched_decoy_proteins,
            "unmatched_target_proteins": self.unmatched_target_proteins,
            "version": self.version,
        }


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_entries(entries: tuple[FastaEntry, ...]) -> None:
    accessions = [entry.accession for entry in entries]
    if len(accessions) != len(set(accessions)):
        raise ValueError("FASTA accessions must be unique for a search-space receipt")
    if any(not entry.accession.strip() for entry in entries):
        raise ValueError("FASTA accessions must be non-empty")


def build_search_space_receipt(
    source_bytes: bytes,
    entries: Iterable[FastaEntry],
    *,
    missed_cleavages: int = 0,
    min_peptide_length: int = 7,
    max_peptide_length: int = 40,
    decoy_prefix: str = _DECOY_PREFIX,
) -> SearchSpaceReceipt:
    """Digest entries and bind target/decoy pairing to the source bytes.

    Pairing is accession-based (``DECOY_<target>``) and cleavage-aware: both
    entries are independently digested with the declared trypsin controls, and
    a pair is marked ``cleavage_compatible`` only when both sides produce the
    same number of digestion products. An unmatched or incompatible side is
    retained as explicit evidence rather than silently used for calibration.
    """

    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be immutable bytes")
    if not source_bytes:
        raise ValueError("search-space source cannot be empty")
    if len(decoy_prefix) < 2 or any(char.isspace() for char in decoy_prefix):
        raise ValueError("decoy_prefix must be a bounded non-whitespace token")
    entries_tuple = tuple(entries)
    if not entries_tuple:
        raise ValueError("search-space receipt requires at least one FASTA entry")
    _validate_entries(entries_tuple)
    digests = {
        entry.accession: digest_entry_trypsin(
            entry,
            missed_cleavages=missed_cleavages,
            min_length=min_peptide_length,
            max_length=max_peptide_length,
        )
        for entry in entries_tuple
    }
    by_accession = {entry.accession: entry for entry in entries_tuple}
    targets = tuple(
        sorted(accession for accession in by_accession if not accession.startswith(decoy_prefix))
    )
    decoys = tuple(
        sorted(accession for accession in by_accession if accession.startswith(decoy_prefix))
    )
    target_peptide_set = {peptide for accession in targets for peptide in digests[accession]}
    decoy_peptide_set = {peptide for accession in decoys for peptide in digests[accession]}
    pairs: list[DecoyPair] = []
    unmatched_targets = 0
    unmatched_decoys = 0
    compatible_pairs = 0
    for target in targets:
        decoy = f"{decoy_prefix}{target}"
        if decoy not in by_accession:
            unmatched_targets += 1
            continue
        target_count = len(digests[target])
        decoy_count = len(digests[decoy])
        status = (
            "cleavage_compatible"
            if target_count == decoy_count and target_count > 0
            else "cleavage_mismatch"
        )
        if status == "cleavage_compatible":
            compatible_pairs += 1
        pairs.append(
            DecoyPair(
                target_accession=target,
                decoy_accession=decoy,
                target_peptides=target_count,
                decoy_peptides=decoy_count,
                target_residue_count=len(by_accession[target].sequence),
                decoy_residue_count=len(by_accession[decoy].sequence),
                status=status,
            )
        )
    for decoy in decoys:
        if decoy[len(decoy_prefix) :] not in by_accession:
            unmatched_decoys += 1
    pair_payload = [pair.as_dict() for pair in pairs]
    pairing_digest = _digest(pair_payload)
    payload: dict[str, object] = {
        "cleavage_compatible_pairs": compatible_pairs,
        "decoy_peptides": len(decoy_peptide_set),
        "decoy_prefix": decoy_prefix,
        "decoy_proteins": len(decoys),
        "digestion_enzyme": "trypsin",
        "max_peptide_length": max_peptide_length,
        "min_peptide_length": min_peptide_length,
        "missed_cleavages": missed_cleavages,
        "paired_proteins": len(pairs),
        "pairing_digest": pairing_digest,
        "pairs": pair_payload,
        "source_sha256": sha256(source_bytes).hexdigest(),
        "target_decoy_overlap_peptides": len(target_peptide_set & decoy_peptide_set),
        "target_peptides": len(target_peptide_set),
        "target_proteins": len(targets),
        "unmatched_decoy_proteins": unmatched_decoys,
        "unmatched_target_proteins": unmatched_targets,
        "version": _VERSION,
    }
    return SearchSpaceReceipt(
        version=_VERSION,
        source_sha256=sha256(source_bytes).hexdigest(),
        digestion_enzyme="trypsin",
        missed_cleavages=missed_cleavages,
        min_peptide_length=min_peptide_length,
        max_peptide_length=max_peptide_length,
        decoy_prefix=decoy_prefix,
        target_proteins=len(targets),
        decoy_proteins=len(decoys),
        target_peptides=len(target_peptide_set),
        decoy_peptides=len(decoy_peptide_set),
        target_decoy_overlap_peptides=len(target_peptide_set & decoy_peptide_set),
        paired_proteins=len(pairs),
        cleavage_compatible_pairs=compatible_pairs,
        unmatched_target_proteins=unmatched_targets,
        unmatched_decoy_proteins=unmatched_decoys,
        pairs=tuple(
            DecoyPair(
                target_accession=pair.target_accession,
                decoy_accession=pair.decoy_accession,
                target_peptides=pair.target_peptides,
                decoy_peptides=pair.decoy_peptides,
                target_residue_count=pair.target_residue_count,
                decoy_residue_count=pair.decoy_residue_count,
                status=pair.status,
            )
            for pair in pairs
        ),
        pairing_digest=pairing_digest,
        search_space_digest=_digest(payload),
    )


def verify_search_space_receipt(receipt: SearchSpaceReceipt) -> SearchSpaceReceipt:
    """Reject forged or internally inconsistent search-space receipts."""

    if not isinstance(receipt, SearchSpaceReceipt):
        raise TypeError("receipt must be a SearchSpaceReceipt")
    payload = receipt.as_dict()
    if _digest(payload["pairs"]) != receipt.pairing_digest:
        raise ValueError("search-space pairing digest is invalid")
    expected = dict(payload)
    expected.pop("search_space_digest")
    if _digest(expected) != receipt.search_space_digest:
        raise ValueError("search-space digest is invalid")
    if receipt.paired_proteins != len(receipt.pairs):
        raise ValueError("search-space pair count is inconsistent")
    if receipt.cleavage_compatible_pairs > receipt.paired_proteins:
        raise ValueError("search-space compatibility count is inconsistent")
    return receipt
