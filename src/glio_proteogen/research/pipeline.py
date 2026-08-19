"""Executable research-only mzML-to-protein-group computation pipeline.

The pipeline is intentionally separate from governed module contracts. It runs a
small, deterministic spectral-count workflow over caller-supplied bytes and
returns content-addressed evidence plus explicit research limitations. It does
not publish a production protein-inference result or clinical claim.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field, replace
from hashlib import md5, sha256
from typing import BinaryIO

from .evidence import EvidenceBundle, EvidenceRecord, aggregate_evidence, verify_evidence_bundle
from .fasta import build_search_space, read_fasta
from .modifications import expand_peptide_map, normalize_modification_rules
from .mzml import parse_mzml
from .pdc import PdcFile, PdcSourceReceipt, PdcStudySnapshot
from .protein import (
    ProteinGroup,
    ProteinGroupCandidate,
    ProteinGroupFdrSummary,
    infer_protein_group_candidates,
)
from .public_proteomics.formats import MzIdentMlStructure, extract_mzidentml_structure
from .public_proteomics.provenance import SourceReference
from .quantification import (
    ProteinGroupQuant,
    QuantificationPolicy,
    QuantificationReceipt,
    quantify_matched_ions_with_receipt,
    quantify_protein_groups,
)
from .search import (
    FdrSummary,
    Psm,
    PsmCompetition,
    SearchParameters,
    search_spectrum_candidates,
    summarize_target_decoy,
    target_decoy_qvalues,
)
from .search_space import (
    SearchSpaceReceipt,
    build_search_space_receipt,
    verify_search_space_receipt,
)

_PIPELINE_VERSION = "research-pipeline-1"
_MZML_PARSER_VERSION = "mzml-parser-1"
_SEARCH_VERSION = "fragment-search-4-candidate-audit-decoy-tie-abstention"
_DIGESTION_VERSION = "trypsin-digest-1"
_MODIFICATION_VERSION = "residue-local-unimod-1"


@dataclass(frozen=True, slots=True)
class ResearchRunRequest:
    """Caller-owned bytes and deterministic controls for one research run."""

    sample_id: str
    mzml_source: bytes | bytearray | BinaryIO
    fasta_source: bytes | str | BinaryIO
    fragment_tolerance_da: float = 0.02
    min_matched_ions: int = 2
    missed_cleavages: int = 0
    min_peptide_length: int = 7
    max_peptide_length: int = 40
    max_spectra: int = 100_000
    q_value_threshold: float = 0.01
    decoy_strategy: str = "caller_declared"
    decoy_prefix: str = "DECOY_"
    max_bytes: int = 256 * 1024 * 1024
    variable_modifications: tuple[str, ...] = ()
    max_variable_modifications: int = 0
    external_source_reference: SourceReference | None = None
    external_pdc_file: PdcFile | None = None
    external_pdc_response_sha256: str | None = None
    external_pdc_receipt: PdcSourceReceipt | None = None
    quantification_policy: QuantificationPolicy = field(default_factory=QuantificationPolicy)
    precursor_tolerance_ppm: int = 20
    mzidentml_source: bytes | bytearray | BinaryIO | None = None

    def __post_init__(self) -> None:
        # Snapshot streams at the boundary so a replay is byte-stable even when the
        # caller supplied a one-shot BinaryIO object.
        if type(self.max_bytes) is not int or not 0 < self.max_bytes <= 512 * 1024 * 1024:
            raise ValueError("max_bytes is outside the research limit")
        mzml_bytes = _read_bytes(self.mzml_source, self.max_bytes)
        fasta_bytes = _read_bytes(self.fasta_source, self.max_bytes)
        mzidentml_bytes = (
            _read_bytes(self.mzidentml_source, self.max_bytes)
            if self.mzidentml_source is not None
            else None
        )
        object.__setattr__(self, "mzml_source", mzml_bytes)
        object.__setattr__(self, "fasta_source", fasta_bytes)
        object.__setattr__(self, "mzidentml_source", mzidentml_bytes)
        object.__setattr__(
            self,
            "variable_modifications",
            normalize_modification_rules(self.variable_modifications),
        )
        if not isinstance(self.quantification_policy, QuantificationPolicy):
            raise TypeError("quantification_policy must be a QuantificationPolicy")
        if (
            type(self.max_variable_modifications) is not int
            or not 0 <= self.max_variable_modifications <= 3
        ):
            raise ValueError("max_variable_modifications must be between zero and three")
        if self.external_pdc_file is not None and not isinstance(self.external_pdc_file, PdcFile):
            raise TypeError("external_pdc_file must be a PdcFile")
        if self.external_pdc_file is not None:
            _validate_pdc_file_binding(
                self.external_pdc_file,
                self.external_source_reference,
                mzml_bytes,
            )
        if self.external_pdc_receipt is not None:
            if not isinstance(self.external_pdc_receipt, PdcSourceReceipt):
                raise TypeError("external_pdc_receipt must be a PdcSourceReceipt")
            if self.external_pdc_file != self.external_pdc_receipt.file:
                raise ValueError("external PDC file does not match its source receipt")
            if self.external_source_reference != self.external_pdc_receipt.source_reference:
                raise ValueError("external source reference does not match its PDC receipt")
            if self.external_pdc_response_sha256 not in {
                None,
                self.external_pdc_receipt.response_sha256,
            }:
                raise ValueError("external response hash does not match its PDC receipt")
        if self.external_pdc_response_sha256 is not None and (
            type(self.external_pdc_response_sha256) is not str
            or len(self.external_pdc_response_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.external_pdc_response_sha256.lower()
            )
        ):
            raise ValueError("external_pdc_response_sha256 must be a 64-character SHA-256")
        if self.external_pdc_file is None and self.external_pdc_response_sha256 is not None:
            raise ValueError("external PDC response hash requires an external PDC file")


def _validate_pdc_file_binding(
    pdc_file: PdcFile,
    source_reference: SourceReference | None,
    mzml_bytes: bytes,
) -> None:
    """Reject a PDC declaration that is not bound to the supplied mzML bytes."""

    if source_reference is None:
        raise ValueError("external PDC file requires a matching source reference")
    if pdc_file.file_format is None or pdc_file.file_format.lower() not in {"mzml", "mzml.gz"}:
        raise ValueError("external PDC file must declare mzML format")
    if source_reference.locator != pdc_file.location:
        raise ValueError("external PDC source locator does not match its file declaration")
    if pdc_file.file_size != len(mzml_bytes):
        raise ValueError("external PDC file size does not match supplied mzML bytes")
    if pdc_file.md5 is not None:
        if not isinstance(pdc_file.md5, str):
            raise TypeError("external PDC file MD5 must be text")
        if md5(mzml_bytes, usedforsecurity=False).hexdigest().lower() != pdc_file.md5.lower():
            raise ValueError("external PDC file MD5 does not match supplied mzML bytes")
    observed_sha = "sha256:" + sha256(mzml_bytes).hexdigest()
    if source_reference.byte_length != len(mzml_bytes) or source_reference.sha256 != observed_sha:
        raise ValueError("external PDC source reference does not match supplied mzML bytes")


def bind_pdc_mzml_source(
    request: ResearchRunRequest,
    pdc_file: PdcFile,
    source_reference: SourceReference,
    *,
    pdc_response_sha256: str | None = None,
    pdc_snapshot: PdcStudySnapshot | None = None,
) -> ResearchRunRequest:
    """Bind caller-downloaded PDC mzML bytes to immutable provenance metadata.

    The function never performs network I/O.  The caller must download bytes
    explicitly (for example with ``PdcClient.download_file``), then provide the
    PDC file declaration and a matching ``SourceReference``.  Any mismatch in
    format, declared size, MD5, locator, or SHA-256 aborts before parsing.
    """

    if not isinstance(pdc_file, PdcFile):
        raise TypeError("pdc_file must be a PdcFile declaration")
    if not isinstance(source_reference, SourceReference):
        raise TypeError("source_reference must be a SourceReference")
    if pdc_snapshot is not None and not isinstance(pdc_snapshot, PdcStudySnapshot):
        raise TypeError("pdc_snapshot must be a PdcStudySnapshot")
    if pdc_file.file_format is None or pdc_file.file_format.lower() not in {"mzml", "mzml.gz"}:
        raise ValueError("PDC source must declare mzML format")
    if source_reference.locator != pdc_file.location:
        raise ValueError("PDC source locator does not match the file declaration")
    snapshot = _read_bytes(request.mzml_source, request.max_bytes)
    observed_sha = "sha256:" + sha256(snapshot).hexdigest()
    if len(snapshot) != pdc_file.file_size:
        raise ValueError("downloaded PDC mzML size differs from its declaration")
    if (
        pdc_file.md5 is not None
        and md5(snapshot, usedforsecurity=False).hexdigest().lower() != pdc_file.md5.lower()
    ):
        raise ValueError("downloaded PDC mzML MD5 differs from its declaration")
    if source_reference.byte_length != len(snapshot) or source_reference.sha256 != observed_sha:
        raise ValueError("PDC source reference does not match downloaded bytes")
    receipt: PdcSourceReceipt | None = None
    if pdc_snapshot is not None:
        if pdc_response_sha256 not in {None, pdc_snapshot.response_sha256}:
            raise ValueError("PDC response hash does not match the captured snapshot")
        receipt = PdcSourceReceipt(
            snapshot=pdc_snapshot,
            file=pdc_file,
            source_reference=source_reference,
            observed_sha256=observed_sha,
            observed_md5=md5(snapshot, usedforsecurity=False).hexdigest(),
            observed_size=len(snapshot),
        )
        pdc_response_sha256 = pdc_snapshot.response_sha256
    return replace(
        request,
        mzml_source=snapshot,
        external_source_reference=source_reference,
        external_pdc_file=pdc_file,
        external_pdc_response_sha256=pdc_response_sha256,
        external_pdc_receipt=receipt,
    )


@dataclass(frozen=True, slots=True)
class ResearchRunResult:
    """Content-addressed output of the research pipeline."""

    sample_id: str
    mzml_sha256: str
    fasta_sha256: str
    spectra_seen: int
    ms2_spectra_seen: int
    search_space_peptides: int
    psms: tuple[Psm, ...]
    accepted_psms: tuple[Psm, ...]
    peptide_spectral_counts: tuple[tuple[str, int], ...]
    protein_groups: tuple[ProteinGroup, ...]
    evidence: EvidenceBundle
    configuration: tuple[tuple[str, object], ...]
    missing_precursor_ms2: int
    result_digest: str
    search_space_receipt: SearchSpaceReceipt | None = None
    peptide_intensities: tuple[tuple[str, float], ...] = ()
    fdr_summary: FdrSummary | None = None
    search_diagnostics: tuple[tuple[str, object], ...] = ()
    protein_group_quantifications: tuple[ProteinGroupQuant, ...] = ()
    protein_group_candidates: tuple[ProteinGroupCandidate, ...] = ()
    protein_group_fdr_summary: ProteinGroupFdrSummary | None = None
    quantification_receipt: QuantificationReceipt | None = None
    competition_audit: tuple[PsmCompetition, ...] = ()
    mzidentml_structure: MzIdentMlStructure | None = None

    @property
    def limitations(self) -> tuple[str, ...]:
        return self.evidence.limitations

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "sample_id": self.sample_id,
            "mzml_sha256": self.mzml_sha256,
            "fasta_sha256": self.fasta_sha256,
            "spectra_seen": self.spectra_seen,
            "ms2_spectra_seen": self.ms2_spectra_seen,
            "search_space_peptides": self.search_space_peptides,
            "search_space_receipt": (
                self.search_space_receipt.as_dict()
                if self.search_space_receipt is not None
                else None
            ),
            "missing_precursor_ms2": self.missing_precursor_ms2,
            "psms": [_psm_dict(item) for item in self.psms],
            "accepted_psms": [_psm_dict(item) for item in self.accepted_psms],
            "peptide_spectral_counts": [list(item) for item in self.peptide_spectral_counts],
            "peptide_intensities": [list(item) for item in self.peptide_intensities],
            "quantification_receipt": (
                self.quantification_receipt.as_dict()
                if self.quantification_receipt is not None
                else None
            ),
            "fdr_summary": self.fdr_summary.as_dict() if self.fdr_summary else None,
            "competition_audit": [item.as_dict() for item in self.competition_audit],
            "search_diagnostics": dict(self.search_diagnostics),
            "protein_group_quantifications": [
                item.as_dict() for item in self.protein_group_quantifications
            ],
            "protein_group_candidates": [item.as_dict() for item in self.protein_group_candidates],
            "protein_group_fdr_summary": (
                self.protein_group_fdr_summary.as_dict()
                if self.protein_group_fdr_summary is not None
                else None
            ),
            "protein_groups": [_group_dict(item) for item in self.protein_groups],
            "configuration": dict(self.configuration),
            "evidence_records": [
                {
                    "id": record.evidence_id,
                    "source": record.source,
                    "kind": record.kind,
                    "payload": record.payload_jsonable,
                    "quality": record.quality.as_dict() if record.quality is not None else None,
                    "digest": record.digest,
                }
                for record in self.evidence.records
            ],
            "evidence_bundle": self.evidence.as_dict(),
            "limitations": list(self.evidence.limitations),
            "evidence_digest": self.evidence.digest,
            "result_digest": self.result_digest,
        }
        if self.mzidentml_structure is not None:
            payload["mzidentml_sha256"] = self.mzidentml_structure.sha256
            payload["mzidentml_structure"] = self.mzidentml_structure.as_dict()
        return payload


def _read_bytes(source: bytes | bytearray | str | BinaryIO, max_bytes: int) -> bytes:
    if isinstance(source, bytes):
        if len(source) > max_bytes:
            raise ValueError("research input exceeds the byte limit")
        return source
    if isinstance(source, bytearray):
        if len(source) > max_bytes:
            raise ValueError("research input exceeds the byte limit")
        return bytes(source)
    if isinstance(source, str):
        value = source.encode("utf-8")
        if len(value) > max_bytes:
            raise ValueError("research input exceeds the byte limit")
        return value
    value = source.read(max_bytes + 1)
    if len(value) > max_bytes:
        raise ValueError("research input exceeds the byte limit")
    return bytes(value)


def _psm_dict(value: Psm) -> dict[str, object]:
    return {
        "decoy": value.decoy,
        "matched_ions": value.matched_ions,
        "peptide": value.peptide,
        "protein_accessions": list(value.protein_accessions),
        "q_value": value.q_value,
        "score": value.score,
        "spectrum_id": value.spectrum_id,
        "matched_intensity": value.matched_intensity,
        "mean_fragment_error_da": value.mean_fragment_error_da,
        "precursor_error_ppm": value.precursor_error_ppm,
        "target_decoy_collision": value.target_decoy_collision,
    }


def _group_dict(value: ProteinGroup) -> dict[str, object]:
    return {
        "accessions": list(value.accessions),
        "shared_peptides": list(value.shared_peptides),
        "unique_peptides": list(value.unique_peptides),
    }


def _pdc_file_dict(value: PdcFile) -> dict[str, object]:
    return {
        "data_category": value.data_category,
        "file_format": value.file_format,
        "file_name": value.file_name,
        "file_size": value.file_size,
        "file_type": value.file_type,
        "location": value.location,
        "md5": value.md5,
        "signed_url": value.signed_url,
        "study_id": value.study_id,
    }


def _result_digest(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_request(request: ResearchRunRequest) -> None:
    if (
        not isinstance(request.sample_id, str)
        or not request.sample_id
        or len(request.sample_id) > 128
        or request.sample_id != request.sample_id.strip()
        or any(character.isspace() or ord(character) < 32 for character in request.sample_id)
    ):
        raise ValueError("sample_id must be a bounded opaque identifier")
    if (
        type(request.fragment_tolerance_da) not in (int, float)
        or not math.isfinite(request.fragment_tolerance_da)
        or request.fragment_tolerance_da <= 0
    ):
        raise ValueError("fragment_tolerance_da must be finite and positive")
    if request.fragment_tolerance_da > 5:
        raise ValueError("fragment_tolerance_da exceeds the research limit")
    if (
        type(request.precursor_tolerance_ppm) is not int
        or not 0 <= request.precursor_tolerance_ppm <= 500
    ):
        raise ValueError("precursor_tolerance_ppm must be between zero and 500")
    if type(request.min_matched_ions) is not int or request.min_matched_ions < 1:
        raise ValueError("min_matched_ions must be positive")
    if request.min_matched_ions > 100:
        raise ValueError("min_matched_ions exceeds the research limit")
    if type(request.missed_cleavages) is not int or not 0 <= request.missed_cleavages <= 4:
        raise ValueError("missed_cleavages is outside the research limit")
    if (
        type(request.min_peptide_length) is not int
        or type(request.max_peptide_length) is not int
        or not 1 <= request.min_peptide_length <= request.max_peptide_length <= 100
    ):
        raise ValueError("peptide length bounds are invalid")
    if type(request.max_spectra) is not int or not 0 < request.max_spectra <= 1_000_000:
        raise ValueError("max_spectra is outside the research limit")
    if (
        type(request.max_variable_modifications) is not int
        or not 0 <= request.max_variable_modifications <= 3
    ):
        raise ValueError("max_variable_modifications must be between zero and three")
    if request.variable_modifications and request.max_variable_modifications == 0:
        raise ValueError("declared variable modifications require a positive site limit")
    if (
        type(request.q_value_threshold) not in (int, float)
        or not 0 <= request.q_value_threshold <= 1
        or not math.isfinite(request.q_value_threshold)
    ):
        raise ValueError("q_value_threshold must be finite and between zero and one")
    if request.decoy_strategy not in {"caller_declared", "reverse_protein"}:
        raise ValueError("unsupported decoy_strategy")
    if (
        not isinstance(request.decoy_prefix, str)
        or not 1 <= len(request.decoy_prefix) <= 32
        or any(character.isspace() or ord(character) < 33 for character in request.decoy_prefix)
    ):
        raise ValueError("decoy_prefix must be a bounded non-whitespace token")


def run_research_protein_inference(request: ResearchRunRequest) -> ResearchRunResult:  # noqa: PLR0915
    """Execute transparent spectrum search, FDR, spectral counting, and grouping."""
    _validate_request(request)
    mzml_bytes = _read_bytes(request.mzml_source, request.max_bytes)
    fasta_bytes = _read_bytes(request.fasta_source, request.max_bytes)
    mzidentml_bytes = (
        _read_bytes(request.mzidentml_source, request.max_bytes)
        if request.mzidentml_source is not None
        else None
    )
    mzidentml_structure = (
        extract_mzidentml_structure(mzidentml_bytes) if mzidentml_bytes is not None else None
    )
    external_reference = request.external_source_reference
    if external_reference is not None:
        observed_external_sha = "sha256:" + sha256(mzml_bytes).hexdigest()
        if (
            external_reference.byte_length != len(mzml_bytes)
            or external_reference.sha256 != observed_external_sha
        ):
            raise ValueError("external source reference does not match mzML input bytes")
    spectra = parse_mzml(mzml_bytes, max_bytes=request.max_bytes, max_spectra=request.max_spectra)
    entries = read_fasta(fasta_bytes)
    search_space = build_search_space(
        entries,
        decoy_strategy=request.decoy_strategy,
        decoy_prefix=request.decoy_prefix,
        missed_cleavages=request.missed_cleavages,
        min_length=request.min_peptide_length,
        max_length=request.max_peptide_length,
    )
    peptide_map = expand_peptide_map(
        search_space.as_map(),
        allowed_modifications=request.variable_modifications,
        max_variable_modifications=request.max_variable_modifications,
    )
    search_space_receipt = build_search_space_receipt(
        fasta_bytes,
        entries,
        decoy_strategy=request.decoy_strategy,
        decoy_prefix=request.decoy_prefix,
        missed_cleavages=request.missed_cleavages,
        min_peptide_length=request.min_peptide_length,
        max_peptide_length=request.max_peptide_length,
        modification_rules=request.variable_modifications,
        max_variable_modifications=request.max_variable_modifications,
    )
    parameters = SearchParameters(
        precursor_tolerance_ppm=request.precursor_tolerance_ppm,
        fragment_tolerance_da=request.fragment_tolerance_da,
        min_matched_ions=request.min_matched_ions,
        decoy_prefix=request.decoy_prefix,
        require_precursor_mz=True,
        allowed_modifications=request.variable_modifications,
        max_variable_modifications=request.max_variable_modifications,
    )
    candidate_psms: list[Psm] = []
    competition_audit: list[PsmCompetition] = []
    ms2_count = 0
    missing_precursor_count = 0
    for spectrum in spectra:
        if spectrum.ms_level != 2:
            continue
        ms2_count += 1
        if (
            spectrum.precursor_ambiguous
            or spectrum.precursor_mz is None
            or spectrum.precursor_charge is None
        ):
            missing_precursor_count += 1
            continue
        candidates = search_spectrum_candidates(
            spectrum.spectrum_id,
            spectrum.precursor_mz,
            peptide_map,
            spectrum.mz,
            spectrum.intensity,
            parameters=SearchParameters(
                precursor_tolerance_ppm=parameters.precursor_tolerance_ppm,
                fragment_tolerance_da=parameters.fragment_tolerance_da,
                min_matched_ions=parameters.min_matched_ions,
                precursor_charge=spectrum.precursor_charge,
                decoy_prefix=request.decoy_prefix,
                require_precursor_mz=True,
                allowed_modifications=request.variable_modifications,
                max_variable_modifications=request.max_variable_modifications,
            ),
        )
        if candidates:
            candidate_psms.extend(candidates)
            competition_audit.append(PsmCompetition.from_candidates(candidates))
    scored = target_decoy_qvalues(tuple(candidate_psms), decoy_prefix=request.decoy_prefix)
    fdr_summary = summarize_target_decoy(
        scored,
        q_value_threshold=request.q_value_threshold,
        decoy_prefix=request.decoy_prefix,
    )
    accepted = tuple(
        item
        for item in scored
        if (
            not item.decoy
            and not item.target_decoy_collision
            and item.q_value is not None
            and item.q_value <= request.q_value_threshold
        )
    )
    fragment_errors = tuple(item.mean_fragment_error_da for item in scored)
    precursor_errors = tuple(
        item.precursor_error_ppm for item in scored if item.precursor_error_ppm is not None
    )
    competition_digest = sha256(
        json.dumps(
            [item.as_dict() for item in competition_audit],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    search_diagnostics = tuple(
        sorted(
            {
                "candidate_competition_digest": competition_digest,
                "candidate_psms": len(candidate_psms),
                "competition_spectra": len(competition_audit),
                "contested_spectra": sum(item.candidate_count > 1 for item in competition_audit),
                "matched_psms": len(scored),
                "mean_fragment_error_da": (
                    sum(fragment_errors) / len(fragment_errors) if fragment_errors else None
                ),
                "max_fragment_error_da": max(fragment_errors) if fragment_errors else None,
                "max_precursor_error_ppm": max(precursor_errors) if precursor_errors else None,
                "precursor_tolerance_ppm": parameters.precursor_tolerance_ppm,
            }.items()
        )
    )
    group_candidates, protein_group_fdr_summary = infer_protein_group_candidates(
        scored,
        q_value_threshold=request.q_value_threshold,
        decoy_prefix=request.decoy_prefix,
    )
    accepted_group_candidates = tuple(
        item for item in group_candidates if item.acceptance == "accepted"
    )
    visible_group_candidates = tuple(
        item
        for item in group_candidates
        if item.acceptance == "accepted" or item.identifiability == "shared_only_ambiguous"
    )
    groups = tuple(
        ProteinGroup(item.accessions, item.unique_peptides, item.shared_peptides)
        for item in visible_group_candidates
    )
    reportable_accession_sets = tuple(
        frozenset(item.accessions) for item in accepted_group_candidates
    )
    quantifiable_accession_sets = tuple(
        frozenset(item.accessions) for item in visible_group_candidates
    )
    reportable_psms = tuple(
        item
        for item in accepted
        if any(
            frozenset(item.protein_accessions) <= accessions
            for accessions in reportable_accession_sets
        )
    )
    quantification_psms = tuple(
        item
        for item in accepted
        if any(
            frozenset(item.protein_accessions) <= accessions
            for accessions in quantifiable_accession_sets
        )
    )
    quantified = quantify_matched_ions_with_receipt(
        request.sample_id,
        ((item.peptide, item.matched_intensity) for item in quantification_psms),
        policy=request.quantification_policy,
    )
    peptide_intensities = tuple((item.peptide, item.intensity) for item in quantified.values)
    counts = tuple(sorted(Counter(item.peptide for item in quantification_psms).items()))
    protein_group_quantifications = quantify_protein_groups(
        groups,
        dict(peptide_intensities),
        dict(counts),
    )
    mzml_digest = sha256(mzml_bytes).hexdigest()
    fasta_digest = sha256(fasta_bytes).hexdigest()
    configuration_payload: dict[str, object] = {
        "pipeline_version": _PIPELINE_VERSION,
        "mzml_parser_version": _MZML_PARSER_VERSION,
        "search_version": _SEARCH_VERSION,
        "digestion_version": _DIGESTION_VERSION,
        "fragment_tolerance_da": request.fragment_tolerance_da,
        "precursor_tolerance_ppm": parameters.precursor_tolerance_ppm,
        "min_matched_ions": request.min_matched_ions,
        "missed_cleavages": request.missed_cleavages,
        "min_peptide_length": request.min_peptide_length,
        "max_peptide_length": request.max_peptide_length,
        "max_spectra": request.max_spectra,
        "q_value_threshold": request.q_value_threshold,
        "decoy_strategy": request.decoy_strategy,
        "decoy_prefix": request.decoy_prefix,
        "max_bytes": request.max_bytes,
        "quantification_version": "matched-ion-median-2",
        "quantification_quality_version": "matched-ion-descriptive-dispersion-1",
        "quantification_unit": "median_scaled_matched_ion_intensity",
        "quantification_receipt_version": quantified.receipt.version,
        "protein_group_quantification_version": "unique-peptide-median-v1",
        "protein_group_quantification_policy": "shared-signal-visible-excluded-from-primary",
        "require_precursor_mz": True,
        "precursor_charge_source": "mzml_selected_ion",
        "search_space_version": search_space_receipt.version,
        "search_space_digest": search_space_receipt.search_space_digest,
        "search_space_pairing_digest": search_space_receipt.pairing_digest,
        "search_space_target_proteins": search_space_receipt.target_proteins,
        "search_space_decoy_proteins": search_space_receipt.decoy_proteins,
        "search_space_unmatched_targets": search_space_receipt.unmatched_target_proteins,
        "search_space_unmatched_decoys": search_space_receipt.unmatched_decoy_proteins,
        "external_source_id": (
            external_reference.source_id if external_reference is not None else None
        ),
        "external_source_sha256": (
            external_reference.sha256 if external_reference is not None else None
        ),
        "external_pdc_file": (
            _pdc_file_dict(request.external_pdc_file)
            if request.external_pdc_file is not None
            else None
        ),
        "external_pdc_response_sha256": request.external_pdc_response_sha256,
        "external_pdc_receipt": (
            request.external_pdc_receipt.as_dict()
            if request.external_pdc_receipt is not None
            else None
        ),
    }
    if request.variable_modifications:
        configuration_payload.update(
            {
                "modification_version": _MODIFICATION_VERSION,
                "variable_modifications": list(request.variable_modifications),
                "max_variable_modifications": request.max_variable_modifications,
            }
        )
    if request.quantification_policy != QuantificationPolicy():
        configuration_payload["quantification_policy"] = request.quantification_policy.as_dict()
    if mzidentml_structure is not None:
        configuration_payload.update(
            {
                "mzidentml_sha256": mzidentml_structure.sha256,
                "mzidentml_structure": mzidentml_structure.as_dict(),
            }
        )
    configuration = tuple(sorted(configuration_payload.items()))
    evidence_records = [
        EvidenceRecord.create(
            "input:fasta",
            f"sha256:{fasta_digest}",
            "search_space",
            {
                "bytes": len(fasta_bytes),
                "peptides": len(peptide_map),
                "search_space_receipt": search_space_receipt.as_dict(),
            },
        ),
        EvidenceRecord.create(
            "search-space:receipt",
            "research:search-space",
            "search_space_receipt",
            search_space_receipt.as_dict(),
        ),
        EvidenceRecord.create(
            "input:mzml",
            f"sha256:{mzml_digest}",
            "spectra",
            {"bytes": len(mzml_bytes), "spectra": len(spectra), "ms2": ms2_count},
        ),
        EvidenceRecord.create(
            "run:configuration",
            "research:pipeline",
            "configuration",
            dict(configuration),
        ),
        EvidenceRecord.create(
            "computed:protein-groups",
            "research:pipeline",
            "protein_groups",
            {
                "accepted_psms": len(accepted),
                "decoy_psms": sum(item.decoy for item in scored),
                "target_decoy_collisions": sum(item.target_decoy_collision for item in scored),
                "groups": len(groups),
                "missing_precursor_ms2": missing_precursor_count,
                "quantified_peptides": len(peptide_intensities),
                "quantification_unit": "median_scaled_matched_ion_intensity",
                "fdr_summary": fdr_summary.as_dict(),
                "protein_group_fdr_summary": protein_group_fdr_summary.as_dict(),
                "protein_group_candidates": [item.as_dict() for item in group_candidates],
                "group_filtered_psms": len(reportable_psms),
                "search_diagnostics": dict(search_diagnostics),
                "protein_group_quantifications": [
                    item.as_dict() for item in protein_group_quantifications
                ],
                "quantification_receipt": quantified.receipt.as_dict(),
                "competition_audit": [item.as_dict() for item in competition_audit],
            },
        ),
    ]
    if external_reference is not None:
        evidence_records.append(
            EvidenceRecord.create(
                "input:external-mzml",
                external_reference.source_id,
                "external_proteomics_mzml",
                external_reference.as_dict(),
            )
        )
    if request.external_pdc_file is not None:
        evidence_records.append(
            EvidenceRecord.create(
                "input:external-pdc-file",
                request.external_pdc_file.location,
                "external_pdc_file_declaration",
                {
                    **_pdc_file_dict(request.external_pdc_file),
                    "response_sha256": request.external_pdc_response_sha256,
                    "receipt": (
                        request.external_pdc_receipt.as_dict()
                        if request.external_pdc_receipt is not None
                        else None
                    ),
                },
            )
        )
    if mzidentml_structure is not None:
        evidence_records.append(
            EvidenceRecord.create(
                "input:mzidentml",
                mzidentml_structure.sha256,
                "identification_evidence_structure",
                mzidentml_structure.as_dict(),
            )
        )
    evidence = aggregate_evidence(tuple(evidence_records))
    result_payload: dict[str, object] = {
        "sample_id": request.sample_id,
        "mzml_sha256": mzml_digest,
        "fasta_sha256": fasta_digest,
        "spectra_seen": len(spectra),
        "ms2_spectra_seen": ms2_count,
        "search_space_peptides": len(peptide_map),
        "search_space_receipt": search_space_receipt.as_dict(),
        "missing_precursor_ms2": missing_precursor_count,
        "psms": [_psm_dict(item) for item in scored],
        "accepted_psms": [_psm_dict(item) for item in accepted],
        "peptide_spectral_counts": [list(item) for item in counts],
        "peptide_intensities": [list(item) for item in peptide_intensities],
        "quantification_receipt": quantified.receipt.as_dict(),
        "fdr_summary": fdr_summary.as_dict(),
        "protein_group_fdr_summary": protein_group_fdr_summary.as_dict(),
        "protein_group_candidates": [item.as_dict() for item in group_candidates],
        "competition_audit": [item.as_dict() for item in competition_audit],
        "search_diagnostics": dict(search_diagnostics),
        "protein_group_quantifications": [item.as_dict() for item in protein_group_quantifications],
        "protein_groups": [_group_dict(item) for item in groups],
        "configuration": dict(configuration),
        "evidence_records": [
            {
                "id": record.evidence_id,
                "source": record.source,
                "kind": record.kind,
                "payload": record.payload_jsonable,
                "quality": record.quality.as_dict() if record.quality is not None else None,
                "digest": record.digest,
            }
            for record in evidence.records
        ],
        "evidence_bundle": evidence.as_dict(),
        "limitations": list(evidence.limitations),
        "evidence_digest": evidence.digest,
    }
    if mzidentml_structure is not None:
        result_payload["mzidentml_sha256"] = mzidentml_structure.sha256
        result_payload["mzidentml_structure"] = mzidentml_structure.as_dict()
    result_digest = _result_digest(result_payload)
    return ResearchRunResult(
        sample_id=request.sample_id,
        mzml_sha256=mzml_digest,
        fasta_sha256=fasta_digest,
        spectra_seen=len(spectra),
        ms2_spectra_seen=ms2_count,
        search_space_peptides=len(peptide_map),
        search_space_receipt=search_space_receipt,
        psms=scored,
        accepted_psms=accepted,
        peptide_spectral_counts=counts,
        protein_groups=groups,
        evidence=evidence,
        configuration=configuration,
        missing_precursor_ms2=missing_precursor_count,
        result_digest=result_digest,
        peptide_intensities=peptide_intensities,
        fdr_summary=fdr_summary,
        search_diagnostics=search_diagnostics,
        protein_group_quantifications=protein_group_quantifications,
        protein_group_candidates=group_candidates,
        protein_group_fdr_summary=protein_group_fdr_summary,
        quantification_receipt=quantified.receipt,
        competition_audit=tuple(competition_audit),
        mzidentml_structure=mzidentml_structure,
    )


def replay_research_protein_inference(
    request: ResearchRunRequest, expected: ResearchRunResult
) -> ResearchRunResult:
    """Re-run a research result and reject any changed or tampered projection."""
    expected_projection = expected.as_dict()
    expected_digest = expected_projection.pop("result_digest")
    if (
        expected_digest != expected.result_digest
        or _result_digest(expected_projection) != expected_digest
    ):
        raise ValueError("expected research result digest is invalid")
    verify_evidence_bundle(expected.evidence)
    if expected.search_space_receipt is not None:
        verify_search_space_receipt(expected.search_space_receipt)
    observed = run_research_protein_inference(request)
    if observed.as_dict() != {**expected_projection, "result_digest": expected_digest}:
        raise ValueError("research result replay or digest verification failed")
    return observed
