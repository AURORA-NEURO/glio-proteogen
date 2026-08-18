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
from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO

from .evidence import EvidenceBundle, EvidenceRecord, aggregate_evidence
from .fasta import digest_trypsin, read_fasta
from .mzml import parse_mzml
from .protein import ProteinGroup, infer_protein_groups
from .search import Psm, SearchParameters, search_spectrum, target_decoy_qvalues


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
    result_digest: str

    @property
    def limitations(self) -> tuple[str, ...]:
        return self.evidence.limitations

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "mzml_sha256": self.mzml_sha256,
            "fasta_sha256": self.fasta_sha256,
            "spectra_seen": self.spectra_seen,
            "ms2_spectra_seen": self.ms2_spectra_seen,
            "search_space_peptides": self.search_space_peptides,
            "psms": [_psm_dict(item) for item in self.psms],
            "accepted_psms": [_psm_dict(item) for item in self.accepted_psms],
            "peptide_spectral_counts": [list(item) for item in self.peptide_spectral_counts],
            "protein_groups": [_group_dict(item) for item in self.protein_groups],
            "evidence_digest": self.evidence.digest,
            "result_digest": self.result_digest,
        }


def _read_bytes(source: bytes | bytearray | str | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, bytearray):
        return bytes(source)
    if isinstance(source, str):
        return source.encode("utf-8")
    value = source.read()
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
    }


def _group_dict(value: ProteinGroup) -> dict[str, object]:
    return {
        "accessions": list(value.accessions),
        "shared_peptides": list(value.shared_peptides),
        "unique_peptides": list(value.unique_peptides),
    }


def _validate_request(request: ResearchRunRequest) -> None:
    if not request.sample_id.strip():
        raise ValueError("sample_id must be non-empty")
    if not math.isfinite(request.fragment_tolerance_da) or request.fragment_tolerance_da <= 0:
        raise ValueError("fragment_tolerance_da must be finite and positive")
    if request.min_matched_ions < 1:
        raise ValueError("min_matched_ions must be positive")
    if not 0 <= request.q_value_threshold <= 1 or not math.isfinite(request.q_value_threshold):
        raise ValueError("q_value_threshold must be finite and between zero and one")


def run_research_protein_inference(request: ResearchRunRequest) -> ResearchRunResult:
    """Execute transparent spectrum search, FDR, spectral counting, and grouping."""
    _validate_request(request)
    mzml_bytes = _read_bytes(request.mzml_source)
    fasta_bytes = _read_bytes(request.fasta_source)
    spectra = parse_mzml(mzml_bytes, max_spectra=request.max_spectra)
    entries = read_fasta(fasta_bytes)
    peptide_map = digest_trypsin(
        entries,
        missed_cleavages=request.missed_cleavages,
        min_length=request.min_peptide_length,
        max_length=request.max_peptide_length,
    )
    parameters = SearchParameters(
        fragment_tolerance_da=request.fragment_tolerance_da,
        min_matched_ions=request.min_matched_ions,
    )
    psms: list[Psm] = []
    ms2_count = 0
    for spectrum in spectra:
        if spectrum.ms_level != 2:
            continue
        ms2_count += 1
        psm = search_spectrum(
            spectrum.spectrum_id,
            0.0,
            peptide_map,
            spectrum.mz,
            spectrum.intensity,
            parameters=parameters,
        )
        if psm is not None:
            psms.append(psm)
    scored = target_decoy_qvalues(tuple(psms))
    accepted = tuple(
        item
        for item in scored
        if item.q_value is not None and item.q_value <= request.q_value_threshold
    )
    peptide_to_proteins: dict[str, set[str]] = {}
    for item in accepted:
        peptide_to_proteins.setdefault(item.peptide, set()).update(item.protein_accessions)
    groups = infer_protein_groups(
        {peptide: tuple(sorted(proteins)) for peptide, proteins in peptide_to_proteins.items()}
    )
    counts = tuple(sorted(Counter(item.peptide for item in accepted).items()))
    mzml_digest = sha256(mzml_bytes).hexdigest()
    fasta_digest = sha256(fasta_bytes).hexdigest()
    evidence = aggregate_evidence(
        (
            EvidenceRecord.create(
                "input:fasta",
                f"sha256:{fasta_digest}",
                "search_space",
                {"bytes": len(fasta_bytes), "peptides": len(peptide_map)},
            ),
            EvidenceRecord.create(
                "input:mzml",
                f"sha256:{mzml_digest}",
                "spectra",
                {"bytes": len(mzml_bytes), "spectra": len(spectra), "ms2": ms2_count},
            ),
            EvidenceRecord.create(
                "computed:protein-groups",
                "research:pipeline",
                "protein_groups",
                {"accepted_psms": len(accepted), "groups": len(groups)},
            ),
        )
    )
    result_payload = {
        "sample_id": request.sample_id,
        "mzml_sha256": mzml_digest,
        "fasta_sha256": fasta_digest,
        "psms": [_psm_dict(item) for item in scored],
        "accepted_psms": [_psm_dict(item) for item in accepted],
        "peptide_spectral_counts": [list(item) for item in counts],
        "protein_groups": [_group_dict(item) for item in groups],
        "evidence_digest": evidence.digest,
    }
    result_digest = sha256(
        json.dumps(result_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ResearchRunResult(
        sample_id=request.sample_id,
        mzml_sha256=mzml_digest,
        fasta_sha256=fasta_digest,
        spectra_seen=len(spectra),
        ms2_spectra_seen=ms2_count,
        search_space_peptides=len(peptide_map),
        psms=scored,
        accepted_psms=accepted,
        peptide_spectral_counts=counts,
        protein_groups=groups,
        evidence=evidence,
        result_digest=result_digest,
    )


def replay_research_protein_inference(
    request: ResearchRunRequest, expected: ResearchRunResult
) -> ResearchRunResult:
    """Re-run a research result and reject any changed or tampered projection."""
    observed = run_research_protein_inference(request)
    if observed.as_dict() != expected.as_dict():
        raise ValueError("research result replay or digest verification failed")
    return observed
