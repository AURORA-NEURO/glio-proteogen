"""End-to-end tests for the research-only proteomics computation pipeline."""

from __future__ import annotations

import base64
import io
import struct
from dataclasses import replace
from hashlib import md5, sha256

import pytest

from glio_proteogen.research import (
    EvidenceRecord,
    PdcFile,
    PdcStudySnapshot,
    ResearchRunRequest,
    SourceReference,
    aggregate_evidence,
    bind_pdc_mzml_source,
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
    assert dict(result.search_diagnostics)["candidate_psms"] == 1
    assert dict(result.search_diagnostics)["contested_spectra"] == 0
    assert len(result.competition_audit) == 1
    assert result.competition_audit[0].target_candidates == 1
    assert result.competition_audit[0].decoy_candidates == 0
    assert result.as_dict()["competition_audit"]
    assert dict(result.search_diagnostics)["max_fragment_error_da"] == pytest.approx(0.000525466)
    assert result.fdr_summary is not None
    assert result.fdr_summary.target_winners == 1
    assert result.fdr_summary.decoy_winners == 0
    assert result.fdr_summary.accepted_targets == 1
    assert result.protein_group_fdr_summary is not None
    assert result.protein_group_fdr_summary.accepted_targets == 1
    assert result.protein_group_candidates[0].acceptance == "accepted"
    assert result.protein_group_candidates[0].q_value == 0.0
    fdr_summary = result.as_dict()["fdr_summary"]
    assert isinstance(fdr_summary, dict)
    assert fdr_summary["method"] == "winner-per-spectrum-target-decoy-collision-abstain-1"
    assert fdr_summary["collision_winners"] == 0
    assert result.peptide_spectral_counts == (("MPEPTIDER", 1),)
    assert result.peptide_intensities == (("MPEPTIDER", 20.0),)
    assert result.protein_groups[0].accessions == ("P1",)
    assert result.protein_group_quantifications[0].status == "quantified"
    assert result.protein_group_quantifications[0].primary_intensity == 20.0
    assert result.quantification_receipt is not None
    assert result.quantification_receipt.raw_positive_median == 20.0
    assert result.quantification_receipt.measurement_unit == ("median_scaled_matched_ion_intensity")
    assert len(result.result_digest) == 64
    assert result.result_digest == run_research_protein_inference(request).result_digest
    assert replay_research_protein_inference(request, result).result_digest == result.result_digest
    assert result.as_dict()["evidence_digest"] == result.evidence.digest


def test_pipeline_replay_rejects_tampered_quantification_receipt() -> None:
    request = ResearchRunRequest(
        "receipt-tamper",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(request)
    assert result.quantification_receipt is not None
    tampered = replace(
        result,
        quantification_receipt=replace(result.quantification_receipt, raw_total_signal=999.0),
    )
    with pytest.raises(ValueError, match="digest"):
        replay_research_protein_inference(request, tampered)


def test_pipeline_replay_rejects_tampered_competition_receipt() -> None:
    request = ResearchRunRequest(
        "competition-tamper",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    result = run_research_protein_inference(request)
    tampered_receipt = replace(result.competition_audit[0], candidate_digest="0" * 64)
    tampered = replace(result, competition_audit=(tampered_receipt,))
    with pytest.raises(ValueError, match="digest"):
        replay_research_protein_inference(request, tampered)


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
    assert result.protein_group_candidates[0].status == "decoy"
    assert result.protein_group_candidates[0].acceptance == "rejected"
    assert result.protein_group_fdr_summary is not None
    assert result.protein_group_fdr_summary.decoy_candidates == 1
    ms1 = ResearchRunRequest(
        sample_id="ms1",
        mzml_source=_mzml(ms_level=1),
        fasta_source=b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    assert run_research_protein_inference(ms1).psms == ()


def test_pipeline_abstains_on_target_decoy_sequence_collision() -> None:
    result = run_research_protein_inference(
        ResearchRunRequest(
            "collision",
            _mzml(),
            b">P1\nMPEPTIDER\n>DECOY_P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
        )
    )
    assert len(result.psms) == 1
    assert result.psms[0].target_decoy_collision is True
    assert result.psms[0].q_value is None
    assert result.accepted_psms == ()
    assert result.fdr_summary is not None
    assert result.fdr_summary.collision_winners == 1
    assert result.protein_group_candidates[0].acceptance == "abstained"
    assert result.protein_group_fdr_summary is not None
    assert result.protein_group_fdr_summary.collision_candidates == 1
    assert result.protein_group_quantifications == ()


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


def test_pipeline_binds_caller_downloaded_pdc_mzml_provenance() -> None:
    payload = _mzml()
    pdc_file = PdcFile(
        study_id="PDC000204",
        file_name="fixture.mzML",
        file_type="Mass Spectrometry",
        data_category="Raw Mass Spectra",
        file_format="mzML",
        file_size=len(payload),
        md5=md5(payload, usedforsecurity=False).hexdigest(),
        location="memory://PDC000204/fixture.mzML",
    )
    source_reference = SourceReference(
        source_id="pdc:PDC000204:fixture.mzML",
        locator=pdc_file.location,
        media_type="application/mzml",
        sha256="sha256:" + sha256(payload).hexdigest(),
        byte_length=len(payload),
        retrieved_at="2026-08-17T00:00:00Z",
        license_or_terms="caller-provided public fixture; research-only",
    )
    request = ResearchRunRequest(
        "pdc-bound",
        payload,
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    bound = bind_pdc_mzml_source(request, pdc_file, source_reference)
    result = run_research_protein_inference(bound)
    assert dict(result.configuration)["external_source_id"] == source_reference.source_id
    assert any(record.kind == "external_proteomics_mzml" for record in result.evidence.records)
    assert any(record.kind == "external_pdc_file_declaration" for record in result.evidence.records)
    with pytest.raises(ValueError, match="locator"):
        replace(
            bound,
            external_pdc_file=replace(pdc_file, location="memory://PDC000204/renamed.mzML"),
        )
    with pytest.raises(ValueError, match="MD5"):
        replace(bound, external_pdc_file=replace(pdc_file, md5="0" * 32))
    response_bound = replace(bound, external_pdc_response_sha256="a" * 64)
    assert run_research_protein_inference(response_bound).result_digest != result.result_digest
    with pytest.raises(ValueError, match="size"):
        bind_pdc_mzml_source(
            request,
            replace(pdc_file, file_size=pdc_file.file_size + 1),
            source_reference,
        )
    with pytest.raises(ValueError, match="MD5"):
        bind_pdc_mzml_source(
            request,
            replace(pdc_file, md5="0" * 32),
            source_reference,
        )


def test_pipeline_rejects_unbound_pdc_declarations() -> None:
    payload = _mzml()
    pdc_file = PdcFile(
        study_id="PDC000204",
        file_name="fixture.mzML",
        file_type="Mass Spectrometry",
        data_category="Raw Mass Spectra",
        file_format="mzML",
        file_size=len(payload),
        md5=md5(payload, usedforsecurity=False).hexdigest(),
        location="memory://PDC000204/fixture.mzML",
    )
    with pytest.raises(ValueError, match="source reference"):
        ResearchRunRequest(
            "unbound-pdc",
            payload,
            b">P1\nMPEPTIDER\n",
            external_pdc_file=pdc_file,
        )
    with pytest.raises(ValueError, match="response hash"):
        ResearchRunRequest(
            "response-without-file",
            payload,
            b">P1\nMPEPTIDER\n",
            external_pdc_response_sha256="a" * 64,
        )


def test_pipeline_binds_catalog_attested_pdc_receipt_and_rejects_substitution() -> None:
    payload = _mzml()
    pdc_file = PdcFile(
        study_id="PDC000204",
        file_name="catalog.mzML",
        file_type="processed_mzML",
        data_category="Proteome",
        file_format="mzML",
        file_size=len(payload),
        md5=md5(payload, usedforsecurity=False).hexdigest(),
        location="https://pdc.cancer.gov/files/catalog.mzML",
    )
    source = SourceReference(
        source_id="pdc:catalog",
        locator=pdc_file.location,
        media_type="application/mzml",
        sha256="sha256:" + sha256(payload).hexdigest(),
        byte_length=len(payload),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="public metadata-bound research fixture",
    )
    snapshot = PdcStudySnapshot(
        study_id="PDC000204",
        counts=(("Proteome", "processed_mzML", 1),),
        files=(pdc_file,),
        source_url="https://pdc.cancer.gov/pdc/study/PDC000204",
        response_sha256="b" * 64,
    )
    request = ResearchRunRequest(
        "catalog-bound",
        payload,
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    bound = bind_pdc_mzml_source(request, pdc_file, source, pdc_snapshot=snapshot)
    assert bound.external_pdc_receipt is not None
    receipt = bound.external_pdc_receipt
    assert receipt.response_sha256 == "b" * 64
    assert receipt.digest == bound.external_pdc_receipt.digest
    result = run_research_protein_inference(bound)
    configuration = dict(result.configuration)
    assert configuration["external_pdc_receipt"] == receipt.as_dict()
    with pytest.raises(ValueError, match="absent"):
        bind_pdc_mzml_source(
            request,
            replace(pdc_file, file_name="not-in-catalog.mzML"),
            source,
            pdc_snapshot=snapshot,
        )
    with pytest.raises(ValueError, match="response hash"):
        bind_pdc_mzml_source(
            request,
            pdc_file,
            source,
            pdc_snapshot=replace(snapshot, response_sha256="c" * 64),
            pdc_response_sha256="d" * 64,
        )


def test_pipeline_rejects_receipt_field_replacement_and_malformed_response_hash() -> None:
    payload = _mzml()
    pdc_file = PdcFile(
        "PDC000204",
        "catalog.mzML",
        "processed",
        "Proteome",
        "mzML",
        len(payload),
        md5(payload, usedforsecurity=False).hexdigest(),
        "https://pdc.cancer.gov/files/catalog.mzML",
    )
    source = SourceReference(
        "pdc:catalog",
        pdc_file.location,
        "application/mzml",
        "sha256:" + sha256(payload).hexdigest(),
        len(payload),
        "2026-08-18T00:00:00Z",
        "research fixture",
    )
    snapshot = PdcStudySnapshot(
        "PDC000204",
        (("Proteome", "processed", 1),),
        (pdc_file,),
        "https://pdc.cancer.gov/pdc/study/PDC000204",
        "b" * 64,
    )
    base = ResearchRunRequest("receipt-fields", payload, b">P1\nMPEPTIDER\n")
    bound = bind_pdc_mzml_source(base, pdc_file, source, pdc_snapshot=snapshot)
    with pytest.raises(ValueError, match="does not match"):
        replace(bound, external_pdc_file=replace(pdc_file, file_name="other.mzML"))
    with pytest.raises(ValueError, match="reference"):
        replace(bound, external_source_reference=replace(source, source_id="pdc:other"))
    with pytest.raises(ValueError, match="response"):
        replace(bound, external_pdc_response_sha256="c" * 64)
    with pytest.raises(TypeError, match="PdcSourceReceipt"):
        replace(bound, external_pdc_receipt=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="64-character"):
        ResearchRunRequest(
            "bad-response",
            payload,
            b">P1\nMPEPTIDER\n",
            external_pdc_response_sha256="z" * 64,
        )


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
