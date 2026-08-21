"""Bounded structural summaries for local proteomics exchange formats.

The summaries describe file structure only.  They deliberately do not decode
intensities, score peptide-spectrum matches, infer proteins, or make disease
claims.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from defusedxml import ElementTree as SafeET

from .provenance import sha256_digest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from xml.etree.ElementTree import Element

MAX_LOCAL_BYTES: Final = 8 * 1024 * 1024
MAX_XML_ELEMENTS: Final = 200_000
_FASTA_ALPHABET: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ*-")


class FormatError(ValueError):
    """Raised when a local research-format payload is unsafe or malformed."""


def _digest_ids(ids: Iterable[str]) -> str:
    return sha256_digest(tuple(sorted(set(ids))))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_root(data: bytes, expected_root: str) -> Element:
    if len(data) > MAX_LOCAL_BYTES:
        raise FormatError("XML payload exceeds the local byte cap")
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper or b"<![" in upper:
        raise FormatError("DTD and entity declarations are not admitted")
    try:
        root = SafeET.fromstring(data)
    except (SyntaxError, ValueError) as error:
        raise FormatError("XML payload is not well formed") from error
    if _local_name(root.tag) != expected_root:
        raise FormatError(f"XML root must be {expected_root}")
    element_count = sum(1 for _ in root.iter())
    if element_count > MAX_XML_ELEMENTS:
        raise FormatError("XML element count exceeds the structural cap")
    return root


@dataclass(frozen=True, slots=True)
class FastaStructure:
    """Structural FASTA features, without sequence identity or annotation claims."""

    record_count: int
    total_residues: int
    minimum_residues: int
    maximum_residues: int
    decoy_record_count: int
    header_digest: str
    byte_length: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "byte_length": self.byte_length,
            "decoy_record_count": self.decoy_record_count,
            "format": "fasta",
            "header_digest": self.header_digest,
            "maximum_residues": self.maximum_residues,
            "minimum_residues": self.minimum_residues,
            "record_count": self.record_count,
            "sha256": self.sha256,
            "total_residues": self.total_residues,
        }


@dataclass(frozen=True, slots=True)
class MzMlStructure:
    """Structural mzML features; binary arrays are counted but never decoded."""

    spectrum_count: int
    chromatogram_count: int
    precursor_count: int
    binary_array_count: int
    ms_level_counts: tuple[tuple[int, int], ...]
    id_digest: str
    byte_length: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "binary_array_count": self.binary_array_count,
            "byte_length": self.byte_length,
            "chromatogram_count": self.chromatogram_count,
            "format": "mzml",
            "id_digest": self.id_digest,
            "ms_level_counts": [[level, count] for level, count in self.ms_level_counts],
            "precursor_count": self.precursor_count,
            "spectrum_count": self.spectrum_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class MzIdentMlStructure:
    """Structural mzIdentML features; no PSM or protein inference is performed."""

    spectrum_identification_result_count: int
    spectrum_identification_item_count: int
    peptide_evidence_count: int
    protein_detection_hypothesis_count: int
    pass_threshold_item_count: int
    id_digest: str
    byte_length: int
    sha256: str
    spectrum_reference_count: int = 0
    spectrum_reference_match_count: int = 0
    protein_reference_count: int = 0
    protein_reference_match_count: int = 0
    peptide_reference_count: int = 0
    peptide_reference_match_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "byte_length": self.byte_length,
            "format": "mzidentml",
            "id_digest": self.id_digest,
            "pass_threshold_item_count": self.pass_threshold_item_count,
            "peptide_reference_count": self.peptide_reference_count,
            "peptide_reference_match_count": self.peptide_reference_match_count,
            "peptide_evidence_count": self.peptide_evidence_count,
            "protein_detection_hypothesis_count": self.protein_detection_hypothesis_count,
            "protein_reference_count": self.protein_reference_count,
            "protein_reference_match_count": self.protein_reference_match_count,
            "sha256": self.sha256,
            "spectrum_reference_count": self.spectrum_reference_count,
            "spectrum_reference_match_count": self.spectrum_reference_match_count,
            "spectrum_identification_item_count": self.spectrum_identification_item_count,
            "spectrum_identification_result_count": self.spectrum_identification_result_count,
        }


def _append_fasta_sequence(line: str, current_length: int | None) -> int:
    if current_length is None:
        raise FormatError("FASTA sequence appeared before its first header")
    sequence = line.upper()
    if any(character not in _FASTA_ALPHABET for character in sequence):
        raise FormatError("FASTA sequence contains unsupported characters")
    return current_length + len(sequence)


def _parse_fasta_lines(text: str) -> tuple[list[str], list[int]]:
    headers: list[str] = []
    lengths: list[int] = []
    current_length: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current_length is not None:
                lengths.append(current_length)
            header = line[1:].strip()
            if not header:
                raise FormatError("FASTA header cannot be empty")
            headers.append(header)
            current_length = 0
            continue
        current_length = _append_fasta_sequence(line, current_length)
    if current_length is not None:
        lengths.append(current_length)
    if not headers or any(length == 0 for length in lengths):
        raise FormatError("FASTA must contain non-empty records")
    if len(headers) != len(lengths):
        raise FormatError("FASTA record structure is inconsistent")
    return headers, lengths


def extract_fasta_structure(
    data: bytes, *, decoy_prefixes: tuple[str, ...] = ("DECOY_", "REV_")
) -> FastaStructure:
    """Extract bounded FASTA record and residue counts."""

    if len(data) > MAX_LOCAL_BYTES:
        raise FormatError("FASTA payload exceeds the local byte cap")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormatError("FASTA payload must be UTF-8") from error
    headers, lengths = _parse_fasta_lines(text)
    return FastaStructure(
        record_count=len(lengths),
        total_residues=sum(lengths),
        minimum_residues=min(lengths),
        maximum_residues=max(lengths),
        decoy_record_count=sum(header.startswith(decoy_prefixes) for header in headers),
        header_digest=_digest_ids(headers),
        byte_length=len(data),
        sha256=sha256_digest(data),
    )


def extract_mzml_structure(data: bytes) -> MzMlStructure:
    """Count mzML structural elements without reading binary measurements."""

    root = _xml_root(data, "mzML")
    ids: list[str] = []
    ms_levels: Counter[int] = Counter()
    spectrum_count = chromatogram_count = precursor_count = binary_array_count = 0
    for element in root.iter():
        local = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if element_id:
            ids.append(element_id)
        if local == "spectrum":
            spectrum_count += 1
        elif local == "chromatogram":
            chromatogram_count += 1
        elif local == "precursor":
            precursor_count += 1
        elif local == "binaryDataArray":
            binary_array_count += 1
        elif local == "cvParam" and element.attrib.get("name") == "ms level":
            raw_level = element.attrib.get("value")
            if raw_level is None or not raw_level.isdigit() or int(raw_level) < 1:
                raise FormatError("mzML ms level cvParam must be a positive integer")
            ms_levels[int(raw_level)] += 1
    return MzMlStructure(
        spectrum_count=spectrum_count,
        chromatogram_count=chromatogram_count,
        precursor_count=precursor_count,
        binary_array_count=binary_array_count,
        ms_level_counts=tuple(sorted(ms_levels.items())),
        id_digest=_digest_ids(ids),
        byte_length=len(data),
        sha256=sha256_digest(data),
    )


def extract_mzidentml_structure(data: bytes) -> MzIdentMlStructure:
    """Count mzIdentML identification structure without scoring identifications."""

    root = _xml_root(data, "MzIdentML")
    ids: list[str] = []
    result_count = item_count = evidence_count = hypothesis_count = pass_count = 0
    for element in root.iter():
        element_id = element.attrib.get("id")
        if element_id:
            ids.append(element_id)
        local = _local_name(element.tag)
        if local == "SpectrumIdentificationResult":
            result_count += 1
        elif local == "SpectrumIdentificationItem":
            item_count += 1
            if element.attrib.get("passThreshold", "").lower() == "true":
                pass_count += 1
        elif local == "PeptideEvidence":
            evidence_count += 1
        elif local == "ProteinDetectionHypothesis":
            hypothesis_count += 1
    return MzIdentMlStructure(
        spectrum_identification_result_count=result_count,
        spectrum_identification_item_count=item_count,
        peptide_evidence_count=evidence_count,
        protein_detection_hypothesis_count=hypothesis_count,
        pass_threshold_item_count=pass_count,
        id_digest=_digest_ids(ids),
        byte_length=len(data),
        sha256=sha256_digest(data),
    )


def bind_mzidentml_references(  # noqa: PLR0915
    data: bytes,
    structure: MzIdentMlStructure,
    *,
    spectrum_ids: Iterable[str],
    protein_accessions: Iterable[str],
) -> MzIdentMlStructure:
    """Bind mzIdentML references to the searched mzML spectra and FASTA.

    Structural counting alone cannot establish that an identification artifact
    belongs to the spectra and sequence catalogue being searched. This gate
    follows ``SpectrumIdentificationResult.spectrumID`` and
    ``SpectrumIdentificationItem.peptide_ref``,
    ``PeptideEvidence.peptide_ref``, and ``PeptideEvidence.dBSequence_ref``
    through the local mzIdentML object graph, rejecting missing or unresolved
    references before the artifact can be reported as run provenance. It still
    does not import mzIdentML scores or protein hypotheses into the local search
    or inference computation.
    """

    if not isinstance(structure, MzIdentMlStructure):
        raise TypeError("structure must be an MzIdentMlStructure")
    known_spectra = tuple(spectrum_ids)
    known_proteins = tuple(protein_accessions)
    if any(not isinstance(value, str) or not value for value in (*known_spectra, *known_proteins)):
        raise FormatError("reference catalogues must contain non-empty strings")
    spectrum_catalogue = set(known_spectra)
    protein_catalogue = set(known_proteins)
    root = _xml_root(data, "MzIdentML")

    db_sequences: dict[str, str] = {}
    peptides: set[str] = set()
    for element in root.iter():
        local = _local_name(element.tag)
        if local == "DBSequence":
            identifier = element.attrib.get("id")
            accession = element.attrib.get("accession")
            if not identifier or not accession:
                raise FormatError("mzIdentML DBSequence requires id and accession")
            if identifier in db_sequences:
                raise FormatError("mzIdentML DBSequence IDs must be unique")
            db_sequences[identifier] = accession
        elif local == "Peptide":
            identifier = element.attrib.get("id")
            if not identifier:
                raise FormatError("mzIdentML Peptide requires id")
            if identifier in peptides:
                raise FormatError("mzIdentML Peptide IDs must be unique")
            peptides.add(identifier)

    spectrum_references = tuple(
        element.attrib["spectrumID"]
        for element in root.iter()
        if _local_name(element.tag) == "SpectrumIdentificationResult"
        and element.attrib.get("spectrumID") is not None
    )
    unknown_spectra = tuple(
        value for value in spectrum_references if value not in spectrum_catalogue
    )
    if unknown_spectra:
        raise FormatError("mzIdentML spectrumID does not resolve to supplied mzML")
    if len(spectrum_references) != len(set(spectrum_references)):
        raise FormatError("mzIdentML spectrumID references must be unique")

    protein_references: list[str] = []
    peptide_references: list[str] = []
    for element in root.iter():
        local = _local_name(element.tag)
        if local == "SpectrumIdentificationItem":
            peptide_ref = element.attrib.get("peptide_ref")
            if peptide_ref is None:
                raise FormatError("mzIdentML SpectrumIdentificationItem requires peptide_ref")
            if peptide_ref not in peptides:
                raise FormatError(
                    "mzIdentML SpectrumIdentificationItem has an unresolved peptide_ref"
                )
            peptide_references.append(peptide_ref)
        elif local == "PeptideEvidence":
            peptide_ref = element.attrib.get("peptide_ref")
            if peptide_ref is None:
                raise FormatError("mzIdentML PeptideEvidence requires peptide_ref")
            if peptide_ref not in peptides:
                raise FormatError("mzIdentML PeptideEvidence has an unresolved peptide_ref")
            peptide_references.append(peptide_ref)
            db_sequence_ref = element.attrib.get("dBSequence_ref")
            if db_sequence_ref is None:
                raise FormatError("mzIdentML PeptideEvidence requires dBSequence_ref")
            accession = db_sequences.get(db_sequence_ref)
            if accession is None:
                raise FormatError("mzIdentML PeptideEvidence has an unresolved DBSequence_ref")
            protein_references.append(accession)
        elif local == "ProteinDetectionHypothesis":
            db_sequence_ref = element.attrib.get("dBSequence_ref")
            if db_sequence_ref is None:
                continue
            accession = db_sequences.get(db_sequence_ref)
            if accession is None:
                raise FormatError(
                    "mzIdentML ProteinDetectionHypothesis has an unresolved DBSequence_ref"
                )
            protein_references.append(accession)
    unknown_proteins = tuple(
        value for value in protein_references if value not in protein_catalogue
    )
    if unknown_proteins:
        raise FormatError("mzIdentML protein reference does not resolve to supplied FASTA")

    return replace(
        structure,
        spectrum_reference_count=len(spectrum_references),
        spectrum_reference_match_count=len(spectrum_references),
        protein_reference_count=len(protein_references),
        protein_reference_match_count=len(protein_references),
        peptide_reference_count=len(peptide_references),
        peptide_reference_match_count=len(peptide_references),
    )
