from __future__ import annotations

import pytest

from glio_proteogen.research.public_proteomics import (
    FormatError,
    bind_mzidentml_references,
    extract_fasta_structure,
    extract_mzidentml_structure,
    extract_mzml_structure,
)

EXPECTED_RECORDS = 2
EXPECTED_RESIDUES = 12
EXPECTED_MINIMUM = 4
EXPECTED_MAXIMUM = 8
EXPECTED_BINARY_ARRAYS = 2
EXPECTED_MS_LEVEL = 2


def test_fasta_features_are_structural_and_decoy_aware() -> None:
    data = b">sp|P1|alpha\nMPEPTIDE\n>DECOY_P1\nMPEP\n"
    summary = extract_fasta_structure(data)
    assert summary.record_count == EXPECTED_RECORDS
    assert summary.total_residues == EXPECTED_RESIDUES
    assert summary.minimum_residues == EXPECTED_MINIMUM
    assert summary.maximum_residues == EXPECTED_MAXIMUM
    assert summary.decoy_record_count == 1


def test_fasta_rejects_sequence_before_header_and_invalid_symbols() -> None:
    with pytest.raises(FormatError, match="before"):
        extract_fasta_structure(b"MPEPTIDE\n")
    with pytest.raises(FormatError, match="unsupported"):
        extract_fasta_structure(b">protein\nMPEP?\n")


def test_mzml_counts_structure_without_decoding_binary_arrays() -> None:
    data = (
        b'<mzML xmlns="http://psi.hupo.org/ms/mzml"><run id="r">'
        b'<spectrumList count="1"><spectrum id="scan=1">'
        b'<cvParam name="ms level" value="2"/><precursor><selectedIonList/>'
        b"</precursor><binaryDataArrayList><binaryDataArray/><binaryDataArray/>"
        b"</binaryDataArrayList></spectrum></spectrumList>"
        b'<chromatogramList><chromatogram id="tic"/></chromatogramList>'
        b"</run></mzML>"
    )
    summary = extract_mzml_structure(data)
    assert summary.spectrum_count == 1
    assert summary.chromatogram_count == 1
    assert summary.precursor_count == 1
    assert summary.binary_array_count == EXPECTED_BINARY_ARRAYS
    assert summary.ms_level_counts == ((EXPECTED_MS_LEVEL, 1),)


def test_mzidentml_counts_identification_structure_without_inference() -> None:
    data = (
        b'<MzIdentML xmlns="http://psidev.info/psi/pi/mzIdentML/1.2">'
        b'<DataCollection><AnalysisData><SpectrumIdentificationResult id="sir1">'
        b'<SpectrumIdentificationItem id="sii1" passThreshold="true"/>'
        b'</SpectrumIdentificationResult><PeptideEvidence id="pe1"/>'
        b'<ProteinDetectionHypothesis id="pdh1"/></AnalysisData>'
        b"</DataCollection></MzIdentML>"
    )
    summary = extract_mzidentml_structure(data)
    assert summary.spectrum_identification_result_count == 1
    assert summary.spectrum_identification_item_count == 1
    assert summary.peptide_evidence_count == 1
    assert summary.protein_detection_hypothesis_count == 1
    assert summary.pass_threshold_item_count == 1


def test_mzidentml_reference_binding_rejects_unrelated_inputs() -> None:
    data = (
        b'<MzIdentML><SequenceCollection><DBSequence id="db1" accession="P1"/>'
        b'<PeptideEvidence id="pe1" dBSequence_ref="db1"/></SequenceCollection>'
        b'<AnalysisData><SpectrumIdentificationResult spectrumID="scan=missing"/>'
        b'</AnalysisData></MzIdentML>'
    )
    summary = extract_mzidentml_structure(data)
    with pytest.raises(FormatError, match="spectrumID"):
        bind_mzidentml_references(
            data,
            summary,
            spectrum_ids=("scan=1",),
            protein_accessions=("P1",),
        )


def test_mzidentml_reference_binding_closes_catalogue_and_structure_types() -> None:
    data = (
        b'<MzIdentML><SequenceCollection><DBSequence id="db1" accession="P1"/>'
        b'<PeptideEvidence id="pe1" dBSequence_ref="db1"/></SequenceCollection>'
        b'<AnalysisData><SpectrumIdentificationResult spectrumID="scan=1"/>'
        b'</AnalysisData></MzIdentML>'
    )
    summary = extract_mzidentml_structure(data)
    with pytest.raises(TypeError, match="structure"):
        bind_mzidentml_references(
            data,
            object(),
            spectrum_ids=("scan=1",),
            protein_accessions=("P1",),
        )
    with pytest.raises(FormatError, match="catalogues"):
        bind_mzidentml_references(
            data,
            summary,
            spectrum_ids=(1,),  # type: ignore[arg-type]
            protein_accessions=("P1",),
        )


@pytest.mark.parametrize(
    ("data", "message"),
    (
        (
            b'<MzIdentML><SequenceCollection><DBSequence accession="P1"/>'
            b"</SequenceCollection></MzIdentML>",
            "requires id",
        ),
        (
            b'<MzIdentML><SequenceCollection><DBSequence id="db1" accession="P1"/>'
            b'<DBSequence id="db1" accession="P1"/></SequenceCollection></MzIdentML>',
            "unique",
        ),
        (
            b'<MzIdentML><AnalysisData><SpectrumIdentificationResult spectrumID="scan=1"/>'
            b'<SpectrumIdentificationResult spectrumID="scan=1"/></AnalysisData></MzIdentML>',
            "unique",
        ),
        (
            b'<MzIdentML><SequenceCollection><PeptideEvidence dBSequence_ref="missing"/>'
            b"</SequenceCollection></MzIdentML>",
            "unresolved DBSequence",
        ),
    ),
)
def test_mzidentml_reference_binding_rejects_malformed_object_graph(
    data: bytes, message: str
) -> None:
    summary = extract_mzidentml_structure(data)
    with pytest.raises(FormatError, match=message):
        bind_mzidentml_references(
            data,
            summary,
            spectrum_ids=("scan=1",),
            protein_accessions=("P1",),
        )


def test_mzidentml_reference_binding_rejects_unresolved_protein_accession() -> None:
    data = (
        b'<MzIdentML><SequenceCollection><DBSequence id="db1" accession="P2"/>'
        b'<PeptideEvidence id="pe1" dBSequence_ref="db1"/></SequenceCollection>'
        b'<AnalysisData><SpectrumIdentificationResult spectrumID="scan=1"/>'
        b"</AnalysisData></MzIdentML>"
    )
    summary = extract_mzidentml_structure(data)
    with pytest.raises(FormatError, match="protein reference"):
        bind_mzidentml_references(
            data,
            summary,
            spectrum_ids=("scan=1",),
            protein_accessions=("P1",),
        )


def test_xml_rejects_dtd_and_wrong_root() -> None:
    with pytest.raises(FormatError, match="DTD"):
        extract_mzml_structure(b"<!DOCTYPE mzML><mzML/>")
    with pytest.raises(FormatError, match="root"):
        extract_mzml_structure(b"<notMzML/>")
