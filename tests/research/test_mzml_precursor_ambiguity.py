"""Safety tests for ambiguous selected-ion metadata in research mzML."""

from __future__ import annotations

import base64
import struct

import pytest

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


def test_parser_rejects_a_non_mzml_root_before_search() -> None:
    wrong_root = (
        _ambiguous_mzml().replace(b"<mzML>", b"<notMzML>").replace(b"</mzML>", b"</notMzML>")
    )
    with pytest.raises(ValueError, match="root"):
        parse_mzml(wrong_root)


def test_parser_rejects_duplicate_spectrum_ids_before_fdr() -> None:
    duplicate = _ambiguous_mzml().replace(
        b"</spectrum></spectrumList></run></mzML>",
        b'</spectrum><spectrum id="scan=ambiguous"/></spectrumList></run></mzML>',
    )
    with pytest.raises(ValueError, match="spectrum IDs must be unique"):
        parse_mzml(duplicate)


@pytest.mark.parametrize("spectrum_id", ["", "  scan=1  ", "scan=1\n"])
def test_parser_rejects_invalid_explicit_spectrum_ids(spectrum_id: str) -> None:
    malformed = _ambiguous_mzml().replace(b'id="scan=ambiguous"', f'id="{spectrum_id}"'.encode())
    with pytest.raises(ValueError, match="spectrum IDs"):
        parse_mzml(malformed)


def test_parser_rejects_ambiguous_arrays_and_nonphysical_values() -> None:
    def array(values: tuple[float, ...], accession: str) -> bytes:
        encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values))
        return (
            b'<binaryDataArray><cvParam accession="'
            + accession.encode()
            + b'"/><cvParam accession="MS:1000521"/><binary>'
            + encoded
            + b"</binary></binaryDataArray>"
        )

    prefix = b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
    suffix = b"</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    with pytest.raises(ValueError, match="positive"):
        parse_mzml(prefix + array((0.0,), "MS:1000514") + suffix)
    with pytest.raises(ValueError, match="non-negative"):
        parse_mzml(prefix + array((100.0,), "MS:1000514") + array((-1.0,), "MS:1000515") + suffix)
    duplicate = prefix + array((100.0,), "MS:1000514") + array((200.0,), "MS:1000514") + suffix
    with pytest.raises(ValueError, match="duplicate m/z"):
        parse_mzml(duplicate)
    dual_role = array((100.0,), "MS:1000514").replace(
        b'<cvParam accession="MS:1000514"/>',
        b'<cvParam accession="MS:1000514"/><cvParam accession="MS:1000515"/>',
    )
    with pytest.raises(ValueError, match="both m/z and intensity"):
        parse_mzml(prefix + dual_role + array((10.0,), "MS:1000515") + suffix)
    with pytest.raises(ValueError, match="retention"):
        parse_mzml(
            b'<mzML><run><spectrumList><spectrum><cvParam accession="MS:1000016" value="-1"/>'
            b"</spectrum></spectrumList></run></mzML>"
        )
    with pytest.raises(ValueError, match="limits"):
        parse_mzml(b"<mzML/>", max_bytes=True)


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


def test_pipeline_abstains_precursor_charge_outside_search_limit() -> None:
    mzml = _ambiguous_mzml().replace(
        b'<cvParam accession="MS:1000041" value="2"/></selectedIon>'
        b'<selectedIon><cvParam accession="MS:1000744" value="600.0"/>',
        b'<cvParam accession="MS:1000041" value="21"/></selectedIon>'
        b'<selectedIon><cvParam accession="MS:1000744" value="600.0"/>',
    )
    # Keep one selected ion so the only abstention reason is the unsupported
    # charge ceiling, rather than the ambiguity fixture's two-ion condition.
    mzml = mzml.replace(
        b'<selectedIon><cvParam accession="MS:1000744" value="600.0"/>'
        b'<cvParam accession="MS:1000041" value="2"/></selectedIon>',
        b"",
    )
    result = run_research_protein_inference(
        ResearchRunRequest(
            sample_id="unsupported-charge",
            mzml_source=mzml,
            fasta_source=b">P1\nMPEPTIDER\n",
            min_matched_ions=1,
            min_peptide_length=7,
            max_peptide_length=12,
        )
    )
    assert result.ms2_spectra_seen == 1
    assert result.missing_precursor_ms2 == 1
    assert result.psms == ()
