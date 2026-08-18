"""End-to-end tests for the research-only proteomics computation pipeline."""

from __future__ import annotations

import base64
import io
import struct
from dataclasses import replace

import pytest

from glio_proteogen.research import (
    EvidenceRecord,
    ResearchRunRequest,
    aggregate_evidence,
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


def _mzml(*, ms_level: int = 2, matched: bool = True, precursor: bool = True) -> bytes:
    mz = (132.0, 229.1, 358.1) if matched else (1.0,)
    intensity = (10.0, 20.0, 30.0) if matched else (1.0,)
    precursor_xml = (
        "<precursorList><precursor><selectedIonList><selectedIon>"
        '<cvParam accession="MS:1000744" value="1087.508837466"/>'
        '<cvParam accession="MS:1000041" value="1"/>'
        "</selectedIon></selectedIonList></precursor></precursorList>"
        if precursor
        else ""
    )
    return (
        '<mzML><run><spectrumList><spectrum id="scan=1">'
        f'<cvParam accession="MS:1000511" value="{ms_level}"/>'
        + precursor_xml
        + "<binaryDataArrayList>"
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
    assert result.psms[0].matched_intensity == 20.0
    assert result.psms[0].mean_fragment_error_da == pytest.approx(0.000525466)
    assert result.psms[0].precursor_error_ppm == pytest.approx(0.0)
    assert dict(result.search_diagnostics)["matched_psms"] == 1
    assert dict(result.search_diagnostics)["max_fragment_error_da"] == pytest.approx(0.000525466)
    assert result.fdr_summary is not None
    assert result.fdr_summary.target_winners == 1
    assert result.fdr_summary.decoy_winners == 0
    assert result.fdr_summary.accepted_targets == 1
    fdr_summary = result.as_dict()["fdr_summary"]
    assert isinstance(fdr_summary, dict)
    assert fdr_summary["method"] == ("winner-per-spectrum-monotone-target-decoy-1")
    assert result.peptide_spectral_counts == (("MPEPTIDER", 1),)
    assert result.peptide_intensities == (("MPEPTIDER", 20.0),)
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
        configuration=result.configuration,
        missing_precursor_ms2=result.missing_precursor_ms2,
        result_digest=result.result_digest,
    )
    with pytest.raises(ValueError):
        replay_research_protein_inference(request, tampered)


def test_pipeline_snapshots_streams_binds_configuration_and_freezes_evidence() -> None:
    stream = io.BytesIO(_mzml())
    request = ResearchRunRequest(
        "stream-snapshot",
        stream,
        io.BytesIO(b">P1\nMPEPTIDER\n"),
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    first = run_research_protein_inference(request)
    stream.read()
    assert replay_research_protein_inference(request, first).result_digest == first.result_digest
    with pytest.raises(TypeError):
        first.evidence.records[0].payload["tamper"] = True  # type: ignore[index]
    changed = run_research_protein_inference(
        ResearchRunRequest(
            "stream-snapshot",
            _mzml(),
            b">P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
            q_value_threshold=0.5,
        )
    )
    assert changed.result_digest != first.result_digest


def test_pipeline_abstains_when_precursor_metadata_is_missing() -> None:
    result = run_research_protein_inference(
        ResearchRunRequest(
            "missing-precursor",
            _mzml(precursor=False),
            b">P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
        )
    )
    assert result.psms == ()
    assert result.missing_precursor_ms2 == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_matched_ions", 1.5),
        ("missed_cleavages", True),
        ("min_peptide_length", 0),
        ("max_peptide_length", 101),
        ("max_spectra", 1.5),
        ("q_value_threshold", True),
    ],
)
def test_pipeline_rejects_non_strict_controls(field: str, value: object) -> None:
    request = ResearchRunRequest("controls", _mzml(), b">P1\nMPEPTIDER\n")
    object.__setattr__(request, field, value)
    with pytest.raises(ValueError):
        run_research_protein_inference(request)


def test_pipeline_replay_rejects_forged_digest() -> None:
    request = ResearchRunRequest(
        "forged",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(request)
    with pytest.raises(ValueError):
        replay_research_protein_inference(request, replace(result, result_digest="0" * 64))


def test_evidence_payload_is_immutable_and_digest_bound() -> None:
    record = EvidenceRecord.create("immutable", "source", "kind", {"nested": [1, 2]})
    assert record.payload_jsonable == {"nested": [1, 2]}
    with pytest.raises(TypeError):
        record.payload["nested"] = (3,)  # type: ignore[index]
    with pytest.raises(ValueError):
        aggregate_evidence((replace(record, digest="0" * 64),))
    with pytest.raises(TypeError):
        EvidenceRecord.create("bad", "source", "kind", {"unsupported": object()})
