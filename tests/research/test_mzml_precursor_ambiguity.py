"""Safety tests for ambiguous selected-ion metadata in research mzML."""

from __future__ import annotations

from glio_proteogen.research import ResearchRunRequest, parse_mzml, run_research_protein_inference


def _ambiguous_mzml() -> bytes:
    return (
        b'<mzML><run><spectrumList><spectrum id="scan=ambiguous">'
        b'<cvParam accession="MS:1000511" value="2"/>'
        b"<precursorList><precursor><selectedIonList>"
        b'<selectedIon><cvParam accession="MS:1000744" value="500.0"/>'
        b'<cvParam accession="MS:1000041" value="2"/></selectedIon>'
        b'<selectedIon><cvParam accession="MS:1000744" value="600.0"/>'
        b'<cvParam accession="MS:1000041" value="2"/></selectedIon>'
        b"</selectedIonList></precursor></precursorList>"
        b"</spectrum></spectrumList></run></mzML>"
    )


def test_parser_does_not_choose_an_arbitrary_selected_ion() -> None:
    spectrum = parse_mzml(_ambiguous_mzml())[0]
    assert spectrum.precursor_ambiguous
    assert spectrum.precursor_mz is None
    assert spectrum.precursor_charge is None


def test_pipeline_abstains_ambiguous_ms2_before_precursor_search() -> None:
    result = run_research_protein_inference(
        ResearchRunRequest(
            sample_id="ambiguous-precursor",
            mzml_source=_ambiguous_mzml(),
            fasta_source=b">P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
        )
    )
    assert result.ms2_spectra_seen == 1
    assert result.missing_precursor_ms2 == 1
    assert result.psms == ()
    assert result.accepted_psms == ()
