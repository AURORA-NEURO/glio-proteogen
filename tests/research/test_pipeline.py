"""End-to-end tests for the research-only proteomics computation pipeline."""

from __future__ import annotations

import base64
import io
import struct

import pytest

from glio_proteogen.research import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _mzml(*, ms_level: int = 2, matched: bool = True) -> bytes:
    mz = (132.0, 229.1, 358.1) if matched else (1.0,)
    intensity = (10.0, 20.0, 30.0) if matched else (1.0,)
    return (
        '<mzML><run><spectrumList><spectrum id="scan=1">'
        f'<cvParam accession="MS:1000511" value="{ms_level}"/>'
        "<binaryDataArrayList>"
        + _array(mz, "MS:1000514")
        + _array(intensity, "MS:1000515")
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()


def test_pipeline_executes_search_fdr_spectral_counts_and_groups() -> None:
    request = ResearchRunRequest(
        sample_id="PDC000204:research-fixture",
        mzml_source=_mzml(),
        fasta_source=b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(request)
    assert result.spectra_seen == 1
    assert result.ms2_spectra_seen == 1
    assert result.search_space_peptides == 1
    assert len(result.psms) == 1
    assert len(result.accepted_psms) == 1
    assert result.peptide_spectral_counts == (("MPEPTIDER", 1),)
    assert result.protein_groups[0].accessions == ("P1",)
    assert len(result.result_digest) == 64
    assert result.result_digest == run_research_protein_inference(request).result_digest
    assert replay_research_protein_inference(request, result).result_digest == result.result_digest
    assert result.as_dict()["evidence_digest"] == result.evidence.digest


def test_pipeline_preserves_decoy_rejection_and_ms2_boundary() -> None:
    decoy = ResearchRunRequest(
        sample_id="decoy",
        mzml_source=io.BytesIO(_mzml()),
        fasta_source=io.BytesIO(b">DECOY_P1\nMPEPTIDER\n"),
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(decoy)
    assert len(result.psms) == 1
    assert result.psms[0].decoy
    assert result.accepted_psms == ()
    ms1 = ResearchRunRequest(
        sample_id="ms1",
        mzml_source=_mzml(ms_level=1),
        fasta_source=b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    assert run_research_protein_inference(ms1).psms == ()


def test_pipeline_rejects_invalid_controls_and_no_match_is_safe() -> None:
    with pytest.raises(ValueError):
        run_research_protein_inference(
            ResearchRunRequest("", _mzml(), b">P1\nMPEPTIDER\n", min_matched_ions=1)
        )
    with pytest.raises(ValueError):
        run_research_protein_inference(
            ResearchRunRequest("x", _mzml(), b">P1\nMPEPTIDER\n", q_value_threshold=2.0)
        )
    result = run_research_protein_inference(
        ResearchRunRequest(
            "no-match",
            _mzml(matched=False),
            b">P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
        )
    )
    assert result.psms == ()
    assert result.protein_groups == ()
    assert result.evidence.records


def test_pipeline_replay_rejects_tampered_projection() -> None:
    request = ResearchRunRequest(
        "tamper",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(request)
    tampered = result.__class__(
        sample_id="other",
        mzml_sha256=result.mzml_sha256,
        fasta_sha256=result.fasta_sha256,
        spectra_seen=result.spectra_seen,
        ms2_spectra_seen=result.ms2_spectra_seen,
        search_space_peptides=result.search_space_peptides,
        psms=result.psms,
        accepted_psms=result.accepted_psms,
        peptide_spectral_counts=result.peptide_spectral_counts,
        protein_groups=result.protein_groups,
        evidence=result.evidence,
        result_digest=result.result_digest,
    )
    with pytest.raises(ValueError):
        replay_research_protein_inference(request, tampered)
