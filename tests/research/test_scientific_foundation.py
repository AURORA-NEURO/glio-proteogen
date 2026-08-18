"""Deep tests for the additive research-only proteomics foundation."""

from __future__ import annotations

import base64
import gzip
import io
import json
import math
import struct
import zlib
from dataclasses import replace
from hashlib import md5
from pathlib import Path
from typing import BinaryIO, Self, cast

import pytest

from glio_proteogen.research import (
    EvidenceRecord,
    PeptideQuant,
    SearchParameters,
    aggregate_evidence,
    digest_trypsin,
    infer_protein_groups,
    median_normalize,
    parse_mzml,
    pdc,
    read_fasta,
    search_spectrum,
    target_decoy_qvalues,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "research" / "pdc000204_snapshot.json"
HEX_DIGEST_LENGTH = 64
REPRESENTATIVE_MZML_BYTES = 193_963_708
MS2_LEVEL = 2


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        '<binaryDataArray encodedLength="0">'
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def test_real_pdc_snapshot_is_explicit_and_content_addressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = json.dumps(
        {
            "filesCountPerStudy": record["counts"],
            "filesPerStudy": record["representative_files"],
        },
        separators=(",", ":"),
    ).encode("utf-8")

    def fake_post(query: str, *, timeout: float = 30.0) -> tuple[dict[str, object], bytes]:
        del query, timeout
        return json.loads(raw), raw

    monkeypatch.setattr(pdc, "_post", fake_post)
    snapshot = pdc.PdcClient().study_snapshot("PDC000204", limit=1)
    assert snapshot.study_id == "PDC000204"
    assert ("Raw Mass Spectra", "Proprietary", 264) in snapshot.counts
    assert snapshot.files[0].file_format == "mzML"
    assert snapshot.files[0].file_size == REPRESENTATIVE_MZML_BYTES
    assert len(snapshot.response_sha256) == HEX_DIGEST_LENGTH


def test_mzml_binary_arrays_and_gzip_roundtrip() -> None:
    payload = (
        '<mzML xmlns="http://psi.hupo.org/ms/mzml" version="1.1.0"><run>'
        '<spectrumList count="1"><spectrum id="scan=1">'
        '<cvParam accession="MS:1000511" value="2"/><binaryDataArrayList count="2">'
        + _array((100.0, 200.0), "MS:1000514")
        + _array((10.0, 20.0), "MS:1000515")
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()
    spectra = parse_mzml(payload)
    assert spectra[0].ms_level == MS2_LEVEL
    assert spectra[0].mz == (100.0, 200.0)
    assert spectra[0].intensity == (10.0, 20.0)


def test_digest_search_target_decoy_and_protein_ambiguity() -> None:
    fasta = read_fasta(b">P1\nMPEPTIDER\n>P2\nMPEPTIDEK\n>DECOY_P1\nMPEPTIDEX")
    peptide_map = digest_trypsin(fasta, min_length=7, max_length=12)
    assert "MPEPTIDER" in peptide_map
    psm = search_spectrum(
        "scan=1",
        1087.508837466,
        {"MPEPTIDER": ("P1",)},
        (132.0, 229.1, 358.1),
        (10.0, 20.0, 30.0),
        parameters=SearchParameters(
            fragment_tolerance_da=0.2, min_matched_ions=1, require_precursor_mz=True
        ),
    )
    assert psm is not None
    qvalues = target_decoy_qvalues((psm,))
    assert qvalues[0].q_value == 0.0
    groups = infer_protein_groups({"MPEPTIDER": ("P1",), "MPEPTIDE": ("P1", "P2")})
    assert groups[0].accessions == ("P1", "P2")
    assert groups[0].shared_peptides == ("MPEPTIDE",)


def test_median_quantification_preserves_missingness() -> None:
    values = (
        PeptideQuant("A", "PEPTIDE", 100.0),
        PeptideQuant("A", "SHARED", 200.0),
        PeptideQuant("B", "PEPTIDE", 200.0),
        PeptideQuant("B", "SHARED", 400.0),
        PeptideQuant("B", "MISSING", 0.0, missing=True),
    )
    normalized = median_normalize(values)
    assert normalized[0].intensity == pytest.approx(133.3333333333)
    assert normalized[2].intensity == pytest.approx(133.3333333333)
    assert normalized[-1].missing is True
    assert normalized[-1].intensity == 0.0


def test_evidence_aggregation_is_order_stable_and_explicitly_limited() -> None:
    records = (
        EvidenceRecord.create("pdc", "PDC000204", "cohort_metadata", {"cases": 111}),
        EvidenceRecord.create("psm", "local-spectrum", "psm", {"q_value": 0.01}),
    )
    bundle = aggregate_evidence(tuple(reversed(records)))
    assert [record.evidence_id for record in bundle.records] == ["pdc", "psm"]
    assert len(bundle.digest) == HEX_DIGEST_LENGTH
    assert any("clinical" in item for item in bundle.limitations)


@pytest.mark.parametrize("source", [b"", b">P1\n", b"P1\nACDEFGH"])
def test_fasta_rejects_empty_or_malformed_sources(source: bytes) -> None:
    with pytest.raises(ValueError):
        read_fasta(source)


def test_fasta_file_like_and_missed_cleavage() -> None:
    entry = read_fasta(b">P1 description\nAKRPEPTIDER\n")[0]
    digested = digest_trypsin((entry,), missed_cleavages=1, min_length=2, max_length=20)
    assert "AK" in digested
    assert "RPEPTIDER" in digested


def test_mzml_gzip_and_limit_failures() -> None:
    payload = (
        b'<mzML version="1.1.0"><run><spectrumList><spectrum id="x" /></spectrumList></run></mzML>'
    )
    assert parse_mzml(gzip.compress(payload))[0].spectrum_id == "x"
    with pytest.raises(ValueError):
        parse_mzml(payload, max_spectra=0)
    with pytest.raises(ValueError):
        parse_mzml(payload, max_bytes=4)


def test_mzml_rejects_unsupported_precision_and_mismatched_arrays() -> None:
    bad_precision = (
        b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
        b"<binaryDataArray><binary>AAAA</binary></binaryDataArray>"
        b"</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    )
    with pytest.raises(ValueError):
        parse_mzml(bad_precision)
    mismatch = (
        b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
        + _array((100.0,), "MS:1000514").encode()
        + _array((10.0, 20.0), "MS:1000515").encode()
        + b"</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    )
    with pytest.raises(ValueError):
        parse_mzml(mismatch)


def test_search_no_match_and_decoy_q_values() -> None:
    assert search_spectrum("none", 1.0, {"PEPTIDE": ("P1",)}, (1.0,), (1.0,)) is None
    decoy = search_spectrum(
        "decoy",
        1087.508837466,
        {"MPEPTIDER": ("DECOY_P1",)},
        (132.0,),
        (10.0,),
        parameters=SearchParameters(
            fragment_tolerance_da=0.2, min_matched_ions=1, require_precursor_mz=True
        ),
    )
    assert decoy is not None
    assert decoy.decoy
    assert target_decoy_qvalues((decoy,))[0].q_value is None


def test_quantification_all_missing_is_identity() -> None:
    values = (PeptideQuant("A", "P", 0.0, missing=True),)
    assert median_normalize(values) == values


def test_evidence_rejects_empty_and_duplicate_ids() -> None:
    record = EvidenceRecord.create("x", "source", "kind", {})
    with pytest.raises(ValueError):
        aggregate_evidence(())
    with pytest.raises(ValueError):
        aggregate_evidence((record, record))


@pytest.mark.parametrize(
    "data",
    [
        {"filesCountPerStudy": {}, "filesPerStudy": []},
        {"filesCountPerStudy": [], "filesPerStudy": {}},
        {"filesCountPerStudy": [{"files_count": "bad"}], "filesPerStudy": []},
    ],
)
def test_pdc_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, object]
) -> None:
    monkeypatch.setattr(pdc, "_post", lambda _query, _timeout=30.0: (data, b"{}"))
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().study_snapshot("PDC000204", limit=1)


def test_pdc_validates_accession_and_limit() -> None:
    with pytest.raises(ValueError):
        pdc.PdcClient().study_snapshot("not-pdc")
    with pytest.raises(ValueError):
        pdc.PdcClient().study_snapshot("PDC000204", limit=129)


def test_fasta_stream_and_digest_validation_edges() -> None:
    stream = io.BytesIO(b">P1 description\nAKRPEPTIDER\n>P2\nMPEPTIDEK\n")
    entries = read_fasta(stream)
    assert [entry.accession for entry in entries] == ["P1", "P2"]
    assert digest_trypsin(entries, min_length=2, max_length=20)
    assert read_fasta("\n>P3\nACDEFGH\n")[0].accession == "P3"
    for bad in (b">\nACDEFGH", b"ACDEFGH", b">P1\n", b">P1\nACD!EFG"):
        with pytest.raises(ValueError):
            read_fasta(bad)
    with pytest.raises(ValueError):
        read_fasta(b">P1\n>P2\nACDEFGH")
    with pytest.raises(ValueError):
        digest_trypsin(entries, missed_cleavages=4)
    with pytest.raises(ValueError):
        digest_trypsin(entries, min_length=0)


def test_mzml_precision_compression_retention_and_limits() -> None:
    def float_array(values: tuple[float, ...], accession: str, *, compressed: bool) -> str:
        raw = struct.pack(f"<{len(values)}f", *values)
        if compressed:
            raw = zlib.compress(raw)
        encoded = base64.b64encode(raw).decode("ascii")
        compression = '<cvParam accession="MS:1000574"/>' if compressed else ""
        return (
            "<binaryDataArray>"
            f'<cvParam accession="{accession}"/><cvParam accession="MS:1000523"/>'
            f"{compression}<binary>{encoded}</binary></binaryDataArray>"
        )

    payload = (
        '<mzML><run><spectrumList><spectrum id="minute">'
        '<cvParam accession="MS:1000511" value="1"/>'
        '<cvParam accession="MS:1000016" value="2" unitName="minute"/>'
        "<binaryDataArrayList>"
        + float_array((100.0, 200.0), "MS:1000514", compressed=True)
        + float_array((10.0, 20.0), "MS:1000515", compressed=True)
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()
    spectrum = parse_mzml(payload)[0]
    assert spectrum.retention_time_seconds == 120.0
    assert spectrum.mz == pytest.approx((100.0, 200.0))
    assert spectrum.intensity == pytest.approx((10.0, 20.0))
    seconds = parse_mzml(payload.replace(b'unitName="minute"', b'unitName="second"'))[0]
    assert seconds.retention_time_seconds == 2.0
    precursor_payload = payload.replace(
        b"<binaryDataArrayList>",
        b"<precursorList><precursor><selectedIonList><selectedIon>"
        b'<cvParam accession="MS:1000744" value="544.258056966"/>'
        b'<cvParam accession="MS:1000041" value="2"/>'
        b"</selectedIon></selectedIonList></precursor></precursorList>"
        b"<binaryDataArrayList>",
    )
    precursor = parse_mzml(precursor_payload)[0]
    assert precursor.precursor_mz == pytest.approx(544.258056966)
    assert precursor.precursor_charge == 2
    empty = (
        b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
        b"<binaryDataArray /></binaryDataArrayList></spectrum>"
        b"</spectrumList></run></mzML>"
    )
    assert parse_mzml(empty)[0].mz == ()
    with pytest.raises(ValueError):
        parse_mzml(payload, max_spectra=0)
    with pytest.raises(ValueError):
        parse_mzml(
            b"<mzML><spectrumList><spectrum /><spectrum /></spectrumList></mzML>", max_spectra=1
        )
    partial = base64.b64encode(b"abc").decode("ascii")
    with pytest.raises(ValueError):
        parse_mzml(
            (
                "<mzML><spectrumList><spectrum><binaryDataArrayList>"
                '<binaryDataArray><cvParam accession="MS:1000523"/>'
                f"<binary>{partial}</binary></binaryDataArray>"
                "</binaryDataArrayList></spectrum></spectrumList></mzML>"
            ).encode()
        )
    with pytest.raises(ValueError):
        parse_mzml(gzip.compress(b"x" * 256), max_bytes=64)
    expanded = zlib.compress(struct.pack("<1024f", *([0.0] * 1024)))
    expanded_payload = (
        b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
        b'<binaryDataArray><cvParam accession="MS:1000574"/>'
        b'<cvParam accession="MS:1000523"/>'
        + b"<binary>"
        + base64.b64encode(expanded)
        + b"</binary></binaryDataArray></binaryDataArrayList>"
        b"</spectrum></spectrumList></run></mzML>"
    )
    with pytest.raises(ValueError):
        parse_mzml(expanded_payload, max_bytes=1024)
    truncated = zlib.compress(b"\x00\x00\x00\x00")[:-1]
    truncated_payload = (
        b"<mzML><run><spectrumList><spectrum><binaryDataArrayList>"
        b'<binaryDataArray><cvParam accession="MS:1000574"/>'
        b'<cvParam accession="MS:1000523"/><binary>'
        + base64.b64encode(truncated)
        + b"</binary></binaryDataArray></binaryDataArrayList>"
        b"</spectrum></spectrumList></run></mzML>"
    )
    with pytest.raises(ValueError):
        parse_mzml(truncated_payload)


def test_mzml_nonseekable_gzip_and_precursor_validation() -> None:
    payload = b'<mzML><run><spectrumList><spectrum id="x"/></spectrumList></run></mzML>'

    class NonSeekable:
        def __init__(self, value: bytes) -> None:
            self.value = value

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                value, self.value = self.value, b""
                return value
            value, self.value = self.value[:size], self.value[size:]
            return value

        def seekable(self) -> bool:
            return False

    assert parse_mzml(cast("BinaryIO", NonSeekable(gzip.compress(payload))))[0].spectrum_id == "x"
    precursor = (
        b"<mzML><run><spectrumList><spectrum><precursorList><precursor>"
        b'<selectedIonList><selectedIon><cvParam accession="MS:1000744" value="nan"/>'
        b"</selectedIon></selectedIonList></precursor></precursorList></spectrum>"
        b"</spectrumList></run></mzML>"
    )
    with pytest.raises(ValueError):
        parse_mzml(precursor)
    charge = precursor.replace(b'value="nan"', b'value="1.0"').replace(
        b'accession="MS:1000744" value="1.0"',
        b'accession="MS:1000744" value="1.0"/><cvParam accession="MS:1000041" value="0"',
    )
    with pytest.raises(ValueError):
        parse_mzml(charge)


def test_search_and_quantification_edge_closures() -> None:
    with pytest.raises(ValueError):
        search_spectrum("bad", 1.0, {"PEPTIDE": ("P1",)}, (1.0,), ())
    assert search_spectrum("bad", 1.0, {"X*": ("P1",)}, (), ()) is None
    values = (
        PeptideQuant("A", "P", 0.0),
        PeptideQuant("B", "P", 20.0),
        PeptideQuant("C", "P", 0.0),
    )
    normalized = median_normalize(values)
    assert normalized[0].intensity == 0.0
    assert normalized[2].intensity == 0.0


def test_search_parameter_and_peak_validation() -> None:
    for kwargs in (
        {"precursor_tolerance_ppm": -1},
        {"fragment_tolerance_da": math.nan},
        {"min_matched_ions": 0},
        {"precursor_charge": 0},
    ):
        with pytest.raises(ValueError):
            SearchParameters(**kwargs)
    assert (
        search_spectrum(
            "negative-intensity",
            1.0,
            {"PEPTIDE": ("P1",)},
            (1.0,),
            (-1.0,),
        )
        is None
    )
    assert (
        search_spectrum(
            "infinite-intensity",
            1.0,
            {"PEPTIDE": ("P1",)},
            (1.0,),
            (math.inf,),
        )
        is None
    )


def test_target_tie_prefers_target_winner() -> None:
    target = search_spectrum(
        "tie",
        1087.508837466,
        {"MPEPTIDER": ("P1",)},
        (132.0, 229.1, 358.1),
        (10.0, 20.0, 30.0),
        parameters=SearchParameters(fragment_tolerance_da=0.2, min_matched_ions=1),
    )
    assert target is not None
    decoy = replace(target, protein_accessions=("DECOY_P1",), decoy=True)
    scored = target_decoy_qvalues((decoy, target))
    assert len(scored) == 1
    assert scored[0].decoy is False
    assert scored[0].q_value == 0.0
    lower = replace(target, score=0.5)
    assert len(target_decoy_qvalues((target, lower))) == 1
    with pytest.raises(ValueError):
        target_decoy_qvalues((replace(target, score=math.nan),))


def test_search_requires_precursor_and_matches_each_peak_once() -> None:
    assert (
        search_spectrum(
            "missing-precursor",
            0.0,
            {"MPEPTIDER": ("P1",)},
            (132.0, 229.1, 358.1),
            (10.0, 20.0, 30.0),
            parameters=SearchParameters(
                fragment_tolerance_da=0.2, min_matched_ions=1, require_precursor_mz=True
            ),
        )
        is None
    )
    assert (
        search_spectrum(
            "wrong-precursor",
            500.0,
            {"MPEPTIDER": ("P1",)},
            (132.0, 229.1, 358.1),
            (10.0, 20.0, 30.0),
            parameters=SearchParameters(
                fragment_tolerance_da=0.2, min_matched_ions=1, require_precursor_mz=True
            ),
        )
        is None
    )
    assert (
        search_spectrum(
            "non-finite-peak",
            1087.508837466,
            {"MPEPTIDER": ("P1",)},
            (math.nan,),
            (10.0,),
            parameters=SearchParameters(
                fragment_tolerance_da=0.2, min_matched_ions=1, require_precursor_mz=True
            ),
        )
        is None
    )
    assert (
        search_spectrum(
            "one-to-one",
            1087.508837466,
            {"MPEPTIDER": ("P1",)},
            (100.0,),
            (10.0,),
            parameters=SearchParameters(
                fragment_tolerance_da=100.0, min_matched_ions=2, require_precursor_mz=True
            ),
        )
        is None
    )


def test_target_decoy_competition_is_per_spectrum_and_decoys_have_no_qvalue() -> None:
    target = search_spectrum(
        "same-spectrum",
        1087.508837466,
        {"MPEPTIDER": ("P1",)},
        (132.0, 229.1, 358.1),
        (10.0, 20.0, 30.0),
        parameters=SearchParameters(fragment_tolerance_da=0.2, min_matched_ions=1),
    )
    assert target is not None
    target = replace(target, score=1.0)
    decoy = replace(target, protein_accessions=("DECOY_P1",), decoy=True, score=2.0)
    scored = target_decoy_qvalues((target, decoy))
    assert len(scored) == 1
    assert scored[0].decoy is True
    assert scored[0].q_value is None


def test_protein_components_are_non_overlapping() -> None:
    groups = infer_protein_groups({"UNIQUE_A": ("A",), "SHARED": ("A", "B"), "UNIQUE_B": ("B",)})
    assert len(groups) == 1
    assert groups[0].accessions == ("A", "B")
    assert groups[0].unique_peptides == ("UNIQUE_A", "UNIQUE_B")
    assert groups[0].shared_peptides == ("SHARED",)
    disjoint = infer_protein_groups({"ONLY_A": ("A",), "ONLY_B": ("B",)})
    assert len(disjoint) == 2
    assert {group.accessions for group in disjoint} == {("A",), ("B",)}


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self._read = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self.payload


def test_pdc_transport_and_file_validation_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    valid = {
        "data": {
            "filesCountPerStudy": [
                {"data_category": "Raw", "file_type": "Mass", "files_count": "1"}
            ],
            "filesPerStudy": [
                {
                    "pdc_study_id": "PDC000204",
                    "file_name": "x.mzML",
                    "file_type": "Mass",
                    "data_category": "Raw",
                    "file_format": "mzML",
                    "file_size": "2",
                    "md5sum": "abc",
                    "file_location": "studies/204/x.mzML",
                }
            ],
        }
    }
    monkeypatch.setattr(
        pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(json.dumps(valid).encode())
    )
    assert pdc.PdcClient().study_snapshot("PDC000204", limit=1).files[0].md5 == "abc"
    for payload in (
        b"not-json",
        json.dumps({"errors": ["bad"]}).encode(),
        json.dumps({"data": None}).encode(),
    ):
        monkeypatch.setattr(
            pdc, "urlopen", lambda *_args, payload=payload, **_kwargs: _FakeResponse(payload)
        )
        with pytest.raises(pdc.PdcError):
            pdc.PdcClient().study_snapshot("PDC000204", limit=1)
    monkeypatch.setattr(
        pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(b"x" * (8 * 1024 * 1024 + 1))
    )
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().study_snapshot("PDC000204", limit=1)
    bad_file = {"data": {"filesCountPerStudy": [], "filesPerStudy": [None]}}
    monkeypatch.setattr(
        pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(json.dumps(bad_file).encode())
    )
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().study_snapshot("PDC000204", limit=1)


@pytest.mark.parametrize(
    "value",
    [[], {"files_count": "1"}, {"files_count": "-1"}, {"files_count": "bad"}],
)
def test_pdc_count_rejections(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    payload = {
        "filesCountPerStudy": [value],
        "filesPerStudy": [],
    }
    monkeypatch.setattr(pdc, "_post", lambda _query: (payload, b"{}"))
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().study_snapshot("PDC000204", limit=1)


def test_pdc_file_entry_must_be_an_object() -> None:
    with pytest.raises(pdc.PdcError):
        pdc._file(None)


def test_pdc_explicit_signed_download_verifies_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"bounded-real-data"
    file = pdc.PdcFile(
        study_id="PDC000204",
        file_name="fixture.mzML",
        file_type="Processed Mass Spectra",
        data_category="Processed Mass Spectra",
        file_format="mzML",
        file_size=len(payload),
        md5=md5(payload, usedforsecurity=False).hexdigest(),
        location="studies/204/fixture.mzML",
        signed_url="https://pdc.cancer.gov/download/fixture",
    )
    monkeypatch.setattr(pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    destination = io.BytesIO()
    assert pdc.PdcClient().download_file(file, destination) == len(payload)
    assert destination.getvalue() == payload
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(file, io.BytesIO(), max_bytes=4)
    with pytest.raises(ValueError):
        pdc.PdcClient().download_file(file, io.BytesIO(), max_bytes=0)
    monkeypatch.setattr(pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(replace(file, file_size=4, md5=None), io.BytesIO())
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(
            replace(file, file_size=len(payload) + 1, md5=None), io.BytesIO()
        )
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(replace(file, md5="0" * 32), io.BytesIO())
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(
            replace(file, signed_url="http://evil.example/x"),
            io.BytesIO(),
        )
    cloudfront_file = replace(file, signed_url="https://d3iwtkuvwz4jtf.cloudfront.net/x")
    assert pdc.PDC_DOWNLOAD_HOSTS
    monkeypatch.setattr(pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    assert pdc.PdcClient().download_file(cloudfront_file, io.BytesIO()) == len(payload)


def test_pdc_signed_download_rejects_missing_or_bad_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"content"
    file = pdc.PdcFile(
        "PDC000204",
        "fixture",
        "Mass",
        "Raw",
        "mzML",
        len(payload),
        "0" * 32,
        "fixture",
        "https://pdc.cancer.gov/download/fixture",
    )
    monkeypatch.setattr(pdc, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(file, io.BytesIO())
    missing = file.__class__(
        file.study_id,
        file.file_name,
        file.file_type,
        file.data_category,
        file.file_format,
        file.file_size,
        file.md5,
        file.location,
    )
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(missing, io.BytesIO())


def test_pdc_private_file_size_and_required_fields() -> None:
    base = {
        "pdc_study_id": "PDC000204",
        "file_name": "x",
        "file_type": "mass",
        "data_category": "raw",
        "file_size": "1",
        "file_location": "x",
    }
    assert pdc._file(base).file_size == 1
    with pytest.raises(pdc.PdcError):
        pdc._file({**base, "file_size": "bad"})
    with pytest.raises(pdc.PdcError):
        pdc._file({**base, "file_size": "-1"})
    with pytest.raises(pdc.PdcError):
        pdc._file({**base, "file_name": ""})
