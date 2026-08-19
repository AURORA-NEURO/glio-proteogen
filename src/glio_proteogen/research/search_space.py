"""Replay-bound provenance for a target/decoy proteomics search space."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from .fasta import (
    FastaEntry,
    _validate_decoy_prefix,
    _validate_digestion_limits,
    _validate_fasta_entry,
    digest_entry_trypsin,
    read_fasta,
)
from .modifications import (
    MODIFICATION_CATALOGUE_VERSION,
    expand_peptide,
    modification_catalogue_digest,
    normalize_modification_rules,
)

_DECOY_PREFIX = "DECOY_"
_BASE_VERSION = "search-space-receipt-1"
_MODIFICATION_VERSION = "search-space-receipt-4-modification-catalogue"
_LEGACY_MODIFICATION_VERSION = "search-space-receipt-3-modification-overlap"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PAIR_STATUSES = frozenset({"cleavage_compatible", "cleavage_mismatch"})


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
    digest: str = ""
    decoy_strategy: str = "caller_declared"
    declared_decoy_entries: int = 0
    generated_decoy_entries: int = 0
    peptide_count: int = 0
    modification_rules: tuple[str, ...] = ()
    max_variable_modifications: int = 0
    modified_target_peptides: int = 0
    modified_decoy_peptides: int = 0
    modified_target_decoy_overlap_peptides: int = 0
    modified_peptide_count: int = 0
    modification_catalogue_version: str = ""
    modification_catalogue_sha256: str = ""

    @property
    def target_entries(self) -> int:
        """Return the number of non-decoy FASTA entries in the receipt."""

        return self.target_proteins

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "cleavage_compatible_pairs": self.cleavage_compatible_pairs,
            "decoy_peptides": self.decoy_peptides,
            "decoy_prefix": self.decoy_prefix,
            "decoy_strategy": self.decoy_strategy,
            "declared_decoy_entries": self.declared_decoy_entries,
            "decoy_proteins": self.decoy_proteins,
            "digestion_enzyme": self.digestion_enzyme,
            "max_peptide_length": self.max_peptide_length,
            "min_peptide_length": self.min_peptide_length,
            "missed_cleavages": self.missed_cleavages,
            "paired_proteins": self.paired_proteins,
            "pairing_digest": self.pairing_digest,
            "generated_decoy_entries": self.generated_decoy_entries,
            "pairs": [item.as_dict() for item in self.pairs],
            "peptide_count": self.peptide_count,
            "search_space_digest": self.search_space_digest,
            "source_sha256": self.source_sha256,
            "target_entries": self.target_entries,
            "target_decoy_overlap_peptides": self.target_decoy_overlap_peptides,
            "collision_peptides": self.target_decoy_overlap_peptides,
            "target_peptides": self.target_peptides,
            "target_proteins": self.target_proteins,
            "unmatched_decoy_proteins": self.unmatched_decoy_proteins,
            "unmatched_target_proteins": self.unmatched_target_proteins,
            "version": self.version,
        }
        if self.modification_rules:
            payload.update(
                {
                    "max_variable_modifications": self.max_variable_modifications,
                    "modification_rules": list(self.modification_rules),
                    "modified_decoy_peptides": self.modified_decoy_peptides,
                    "modified_target_decoy_overlap_peptides": (
                        self.modified_target_decoy_overlap_peptides
                    ),
                    "modified_peptide_count": self.modified_peptide_count,
                    "modified_target_peptides": self.modified_target_peptides,
                    "modification_catalogue_sha256": self.modification_catalogue_sha256,
                    "modification_catalogue_version": self.modification_catalogue_version,
                }
            )
        return payload


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_entries(entries: tuple[FastaEntry, ...]) -> None:
    accessions = [entry.accession for entry in entries]
    if len(accessions) != len(set(accessions)):
        raise ValueError("FASTA accessions must be unique for a search-space receipt")
    if any(not entry.accession.strip() for entry in entries):
        raise ValueError("FASTA accessions must be non-empty")


def build_search_space_receipt(  # noqa: PLR0915 - receipt construction binds every control
    source_bytes: bytes,
    entries: Iterable[FastaEntry],
    *,
    missed_cleavages: int = 0,
    min_peptide_length: int = 7,
    max_peptide_length: int = 40,
    decoy_prefix: str = _DECOY_PREFIX,
    decoy_strategy: str = "caller_declared",
    modification_rules: tuple[str, ...] = (),
    max_variable_modifications: int = 0,
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
    if decoy_strategy not in {"caller_declared", "reverse_protein"}:
        raise ValueError("unsupported decoy_strategy")
    _validate_decoy_prefix(decoy_prefix)
    _validate_digestion_limits(missed_cleavages, min_peptide_length, max_peptide_length)
    modification_rules = normalize_modification_rules(modification_rules)
    receipt_version = _MODIFICATION_VERSION if modification_rules else _BASE_VERSION
    if type(max_variable_modifications) is not int or not 0 <= max_variable_modifications <= 3:
        raise ValueError("max_variable_modifications must be between zero and three")
    if modification_rules and max_variable_modifications == 0:
        raise ValueError("declared modification rules require a positive site limit")
    entries_tuple = tuple(entries)
    if not entries_tuple:
        raise ValueError("search-space receipt requires at least one FASTA entry")
    for entry in entries_tuple:
        _validate_fasta_entry(entry)
    _validate_entries(entries_tuple)
    declared_decoys = tuple(
        entry for entry in entries_tuple if entry.accession.startswith(decoy_prefix)
    )
    targets_entries = tuple(
        entry for entry in entries_tuple if not entry.accession.startswith(decoy_prefix)
    )
    generated_decoys = (
        tuple(
            FastaEntry(f"{decoy_prefix}{entry.accession}", entry.sequence[::-1])
            for entry in targets_entries
        )
        if decoy_strategy == "reverse_protein"
        else ()
    )
    supplied_accessions = {entry.accession for entry in entries_tuple}
    if any(entry.accession in supplied_accessions for entry in generated_decoys):
        raise ValueError("generated decoy accession collides with supplied FASTA")
    search_entries = entries_tuple + generated_decoys
    digests = {
        entry.accession: digest_entry_trypsin(
            entry,
            missed_cleavages=missed_cleavages,
            min_length=min_peptide_length,
            max_length=max_peptide_length,
        )
        for entry in search_entries
    }
    by_accession = {entry.accession: entry for entry in search_entries}
    targets = tuple(
        sorted(accession for accession in by_accession if not accession.startswith(decoy_prefix))
    )
    decoys = tuple(
        sorted(accession for accession in by_accession if accession.startswith(decoy_prefix))
    )
    target_peptide_set = {peptide for accession in targets for peptide in digests[accession]}
    decoy_peptide_set = {peptide for accession in decoys for peptide in digests[accession]}
    modified_digests = {
        accession: tuple(
            variant
            for peptide in digests[accession]
            for variant in expand_peptide(
                peptide,
                allowed_modifications=modification_rules,
                max_variable_modifications=max_variable_modifications,
            )
        )
        for accession in by_accession
    }
    modified_target_peptide_set = {
        peptide for accession in targets for peptide in modified_digests[accession]
    }
    modified_decoy_peptide_set = {
        peptide for accession in decoys for peptide in modified_digests[accession]
    }
    modified_target_decoy_overlap = len(modified_target_peptide_set & modified_decoy_peptide_set)
    modified_peptide_count = len(modified_target_peptide_set | modified_decoy_peptide_set)
    pairs: list[DecoyPair] = []
    unmatched_targets = 0
    unmatched_decoys = 0
    compatible_pairs = 0
    for target in targets:
        decoy = f"{decoy_prefix}{target}"
        if decoy not in by_accession:
            unmatched_targets += 1
            continue
        target_count = len(modified_digests[target])
        decoy_count = len(modified_digests[decoy])
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
        "decoy_strategy": decoy_strategy,
        "declared_decoy_entries": len(declared_decoys),
        "decoy_proteins": len(decoys),
        "digestion_enzyme": "trypsin",
        "max_peptide_length": max_peptide_length,
        "min_peptide_length": min_peptide_length,
        "missed_cleavages": missed_cleavages,
        "paired_proteins": len(pairs),
        "pairing_digest": pairing_digest,
        "generated_decoy_entries": len(generated_decoys),
        "pairs": pair_payload,
        "peptide_count": len(target_peptide_set | decoy_peptide_set),
        "source_sha256": sha256(source_bytes).hexdigest(),
        "target_entries": len(targets),
        "target_decoy_overlap_peptides": len(target_peptide_set & decoy_peptide_set),
        "collision_peptides": len(target_peptide_set & decoy_peptide_set),
        "target_peptides": len(target_peptide_set),
        "target_proteins": len(targets),
        "unmatched_decoy_proteins": unmatched_decoys,
        "unmatched_target_proteins": unmatched_targets,
        "version": receipt_version,
    }
    if modification_rules:
        payload.update(
            {
                "max_variable_modifications": max_variable_modifications,
                "modification_rules": list(modification_rules),
                "modified_decoy_peptides": len(modified_decoy_peptide_set),
                "modified_target_decoy_overlap_peptides": modified_target_decoy_overlap,
                "modified_peptide_count": modified_peptide_count,
                "modified_target_peptides": len(modified_target_peptide_set),
                "modification_catalogue_sha256": modification_catalogue_digest(),
                "modification_catalogue_version": MODIFICATION_CATALOGUE_VERSION,
            }
        )
    return SearchSpaceReceipt(
        version=receipt_version,
        source_sha256=sha256(source_bytes).hexdigest(),
        digestion_enzyme="trypsin",
        missed_cleavages=missed_cleavages,
        min_peptide_length=min_peptide_length,
        max_peptide_length=max_peptide_length,
        decoy_prefix=decoy_prefix,
        decoy_strategy=decoy_strategy,
        declared_decoy_entries=len(declared_decoys),
        generated_decoy_entries=len(generated_decoys),
        peptide_count=len(target_peptide_set | decoy_peptide_set),
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
        digest=_digest(payload),
        modification_rules=modification_rules,
        max_variable_modifications=max_variable_modifications,
        modified_target_peptides=len(modified_target_peptide_set),
        modified_decoy_peptides=len(modified_decoy_peptide_set),
        modified_target_decoy_overlap_peptides=(
            modified_target_decoy_overlap if modification_rules else 0
        ),
        modified_peptide_count=modified_peptide_count if modification_rules else 0,
        modification_catalogue_version=(
            MODIFICATION_CATALOGUE_VERSION if modification_rules else ""
        ),
        modification_catalogue_sha256=(
            modification_catalogue_digest() if modification_rules else ""
        ),
    )


def _validate_nonnegative_int(value: object, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"search-space {field} is invalid")


def _validate_receipt_structure(receipt: SearchSpaceReceipt) -> None:  # noqa: PLR0915
    if receipt.version not in {
        _BASE_VERSION,
        _MODIFICATION_VERSION,
        _LEGACY_MODIFICATION_VERSION,
    }:
        raise ValueError("search-space receipt version is unsupported")
    for value, field in (
        (receipt.source_sha256, "source SHA-256"),
        (receipt.pairing_digest, "pairing digest"),
        (receipt.search_space_digest, "search-space digest"),
    ):
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise ValueError(f"search-space {field} is not a lowercase SHA-256")
    if receipt.digestion_enzyme != "trypsin":
        raise ValueError("search-space digestion enzyme is unsupported")
    if receipt.decoy_strategy not in {"caller_declared", "reverse_protein"}:
        raise ValueError("search-space decoy strategy is unsupported")
    try:
        _validate_decoy_prefix(receipt.decoy_prefix)
        _validate_digestion_limits(
            receipt.missed_cleavages,
            receipt.min_peptide_length,
            receipt.max_peptide_length,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("search-space digestion controls are invalid") from error
    if type(receipt.pairs) is not tuple:
        raise ValueError("search-space pairs must be a tuple")
    if any(not isinstance(item, DecoyPair) for item in receipt.pairs):
        raise TypeError("search-space pairs must contain DecoyPair values")
    if tuple(item.target_accession for item in receipt.pairs) != tuple(
        sorted(item.target_accession for item in receipt.pairs)
    ):
        raise ValueError("search-space pairs are not canonically ordered")
    targets: set[str] = set()
    decoys: set[str] = set()
    compatible_count = 0
    for pair in receipt.pairs:
        if not isinstance(pair, DecoyPair):
            raise TypeError("search-space pairs must contain DecoyPair values")
        if (
            type(pair.target_accession) is not str
            or not pair.target_accession
            or pair.target_accession.startswith(receipt.decoy_prefix)
            or pair.decoy_accession != f"{receipt.decoy_prefix}{pair.target_accession}"
            or pair.target_accession in targets
            or pair.decoy_accession in decoys
        ):
            raise ValueError("search-space pair target/decoy identity is invalid")
        _validate_nonnegative_int(pair.target_peptides, "target peptide count")
        _validate_nonnegative_int(pair.decoy_peptides, "decoy peptide count")
        _validate_nonnegative_int(pair.target_residue_count, "target residue count")
        _validate_nonnegative_int(pair.decoy_residue_count, "decoy residue count")
        if pair.status not in _PAIR_STATUSES:
            raise ValueError("search-space pair status is unsupported")
        compatible = pair.target_peptides == pair.decoy_peptides and pair.target_peptides > 0
        if (pair.status == "cleavage_compatible") != compatible:
            raise ValueError("search-space pair status is inconsistent")
        compatible_count += pair.status == "cleavage_compatible"
        targets.add(pair.target_accession)
        decoys.add(pair.decoy_accession)
    if receipt.paired_proteins != len(receipt.pairs):
        raise ValueError("search-space pair count is inconsistent")
    if receipt.cleavage_compatible_pairs != compatible_count:
        raise ValueError("search-space compatibility count is inconsistent")
    _validate_nonnegative_int(receipt.target_proteins, "target protein count")
    _validate_nonnegative_int(receipt.decoy_proteins, "decoy protein count")
    _validate_nonnegative_int(receipt.unmatched_target_proteins, "unmatched target count")
    _validate_nonnegative_int(receipt.unmatched_decoy_proteins, "unmatched decoy count")
    _validate_nonnegative_int(receipt.target_peptides, "target peptide count")
    _validate_nonnegative_int(receipt.decoy_peptides, "decoy peptide count")
    _validate_nonnegative_int(receipt.target_decoy_overlap_peptides, "target/decoy overlap count")
    _validate_nonnegative_int(receipt.paired_proteins, "paired protein count")
    _validate_nonnegative_int(receipt.cleavage_compatible_pairs, "compatible pair count")
    _validate_nonnegative_int(receipt.modified_target_peptides, "modified target peptide count")
    _validate_nonnegative_int(receipt.modified_decoy_peptides, "modified decoy peptide count")
    _validate_nonnegative_int(
        receipt.modified_target_decoy_overlap_peptides,
        "modified target/decoy overlap count",
    )
    _validate_nonnegative_int(receipt.modified_peptide_count, "modified search-space peptide count")
    _validate_nonnegative_int(receipt.declared_decoy_entries, "declared decoy entry count")
    _validate_nonnegative_int(receipt.generated_decoy_entries, "generated decoy entry count")
    _validate_nonnegative_int(receipt.peptide_count, "search-space peptide count")
    if (
        receipt.target_proteins != receipt.paired_proteins + receipt.unmatched_target_proteins
        or receipt.decoy_proteins != receipt.paired_proteins + receipt.unmatched_decoy_proteins
    ):
        raise ValueError("search-space unmatched protein counts are inconsistent")
    if receipt.declared_decoy_entries + receipt.generated_decoy_entries != receipt.decoy_proteins:
        raise ValueError("search-space decoy entry counts are inconsistent")
    if receipt.decoy_strategy == "caller_declared" and receipt.generated_decoy_entries:
        raise ValueError("caller-declared search space cannot contain generated decoys")
    if (
        receipt.decoy_strategy == "reverse_protein"
        and receipt.generated_decoy_entries != receipt.target_proteins
    ):
        raise ValueError("reverse search space must generate one decoy per target")
    if receipt.target_decoy_overlap_peptides > min(receipt.target_peptides, receipt.decoy_peptides):
        raise ValueError("search-space overlap count is inconsistent")
    if receipt.peptide_count != (
        receipt.target_peptides + receipt.decoy_peptides - receipt.target_decoy_overlap_peptides
    ):
        raise ValueError("search-space peptide count is inconsistent")
    if receipt.modification_rules:
        try:
            normalized_rules = normalize_modification_rules(receipt.modification_rules)
        except (TypeError, ValueError) as error:
            raise ValueError("search-space modification rules are invalid") from error
        if normalized_rules != receipt.modification_rules:
            raise ValueError("search-space modification rules are not canonical")
        if receipt.version != _MODIFICATION_VERSION or (
            type(receipt.max_variable_modifications) is not int
            or not 1 <= receipt.max_variable_modifications <= 3
        ):
            raise ValueError("search-space modification controls are inconsistent")
        if receipt.modified_target_decoy_overlap_peptides > min(
            receipt.modified_target_peptides,
            receipt.modified_decoy_peptides,
        ):
            raise ValueError("search-space modified overlap count is inconsistent")
        if receipt.modified_peptide_count != (
            receipt.modified_target_peptides
            + receipt.modified_decoy_peptides
            - receipt.modified_target_decoy_overlap_peptides
        ):
            raise ValueError("search-space modified peptide count is inconsistent")
        if receipt.modification_catalogue_version != MODIFICATION_CATALOGUE_VERSION:
            raise ValueError("search-space modification catalogue version is inconsistent")
        if (
            type(receipt.modification_catalogue_sha256) is not str
            or _SHA256.fullmatch(receipt.modification_catalogue_sha256) is None
            or receipt.modification_catalogue_sha256 != modification_catalogue_digest()
        ):
            raise ValueError("search-space modification catalogue digest is invalid")
    elif (
        receipt.version != _BASE_VERSION
        or receipt.max_variable_modifications != 0
        or receipt.modified_target_decoy_overlap_peptides != 0
        or receipt.modified_peptide_count != 0
        or receipt.modification_catalogue_version != ""
        or receipt.modification_catalogue_sha256 != ""
    ):
        raise ValueError("search-space modification controls are inconsistent")
    if receipt.digest and receipt.digest != receipt.search_space_digest:
        raise ValueError("search-space digest alias is invalid")


def verify_search_space_receipt(
    receipt: SearchSpaceReceipt,
    *,
    source_bytes: bytes | None = None,
    entries: Iterable[FastaEntry] | None = None,
) -> SearchSpaceReceipt:
    """Reject forged or internally inconsistent search-space receipts.

    When ``source_bytes`` is supplied, its content hash is checked against the
    receipt.  Supplying ``entries`` as well performs a full rebuild using every
    recorded digestion, decoy, and modification control.  This optional
    source-bound path closes the standalone replay gap while preserving the
    inexpensive structural verifier used by callers that only have a receipt.
    """

    if not isinstance(receipt, SearchSpaceReceipt):
        raise TypeError("receipt must be a SearchSpaceReceipt")
    _validate_receipt_structure(receipt)
    payload = receipt.as_dict()
    if _digest(payload["pairs"]) != receipt.pairing_digest:
        raise ValueError("search-space pairing digest is invalid")
    expected = dict(payload)
    expected.pop("search_space_digest")
    if _digest(expected) != receipt.search_space_digest:
        raise ValueError("search-space digest is invalid")
    if source_bytes is not None:
        if type(source_bytes) is not bytes:
            raise TypeError("source_bytes must be immutable bytes")
        if sha256(source_bytes).hexdigest() != receipt.source_sha256:
            raise ValueError("search-space source bytes do not match receipt")
    if entries is not None:
        if source_bytes is None:
            raise ValueError("entries require source_bytes for source-bound verification")
        provided_entries = tuple(entries)
        if read_fasta(source_bytes) != provided_entries:
            raise ValueError("search-space source entries do not match supplied entries")
        rebuilt = build_search_space_receipt(
            source_bytes,
            provided_entries,
            missed_cleavages=receipt.missed_cleavages,
            min_peptide_length=receipt.min_peptide_length,
            max_peptide_length=receipt.max_peptide_length,
            decoy_prefix=receipt.decoy_prefix,
            decoy_strategy=receipt.decoy_strategy,
            modification_rules=receipt.modification_rules,
            max_variable_modifications=receipt.max_variable_modifications,
        )
        if rebuilt.as_dict() != receipt.as_dict():
            raise ValueError("search-space receipt does not match source entries")
    return receipt
