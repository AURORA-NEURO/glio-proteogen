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
from hashlib import md5, sha256
from pathlib import Path
from typing import BinaryIO, Self, cast

import pytest

from glio_proteogen.research import (
    EvidenceRecord,
    PdcSourceReceipt,
    PdcStudySnapshot,
    PeptideQuant,
    Psm,
    QuantificationReceipt,
    SearchParameters,
    SourceReference,
    aggregate_evidence,
    digest_trypsin,
    infer_protein_group_candidates,
    infer_protein_groups,
    median_normalize,
    parse_mzml,
    pdc,
    quantify_matched_ions,
    quantify_matched_ions_with_receipt,
    quantify_protein_groups,
    read_fasta,
    search_spectrum,
    summarize_target_decoy,
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
    assert psm.mean_fragment_error_da == pytest.approx(0.030468466)
    assert psm.precursor_error_ppm == pytest.approx(0.0)
    qvalues = target_decoy_qvalues((psm,))
    assert qvalues[0].q_value == 0.0
    groups = infer_protein_groups({"MPEPTIDER": ("P1",), "MPEPTIDE": ("P1", "P2")})
    assert groups[0].accessions == ("P1", "P2")
    assert groups[0].shared_peptides == ("MPEPTIDE",)


def test_target_decoy_summary_is_explicit_and_threshold_bound() -> None:
    target = Psm("scan=1", "MPEPTIDER", ("P1",), 4.0, 3, decoy=False)
    decoy = Psm("scan=2", "MPEPTIDER", ("DECOY_P1",), 3.0, 3, decoy=True)
    summary = summarize_target_decoy((target, decoy), q_value_threshold=0.01)
    assert summary.method == "winner-per-spectrum-target-decoy-collision-abstain-1"
    assert summary.spectrum_winners == 2
    assert summary.target_winners == 1
    assert summary.decoy_winners == 1
    assert summary.accepted_targets == 1
    assert summary.max_accepted_q_value == 0.0
    assert summary.decoy_to_target_ratio == 1.0
    with pytest.raises(ValueError, match="between zero and one"):
        summarize_target_decoy((target,), q_value_threshold=1.1)


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


def test_matched_ion_quantification_aggregates_and_normalizes() -> None:
    quantified = quantify_matched_ions(
        "sample-1",
        (("PEPTIDE", 10.0), ("PEPTIDE", 30.0), ("OTHER", 20.0), ("MISSING", 0.0)),
    )
    assert quantified[0].peptide == "MISSING"
    assert quantified[0].missing is True
    assert quantified[0].intensity == 0.0
    assert quantified[1].peptide == "OTHER"
    assert quantified[1].intensity == pytest.approx(20.0)
    assert quantified[2].peptide == "PEPTIDE"
    assert quantified[2].intensity == pytest.approx(40.0)


def test_matched_ion_quantification_receipt_binds_units_duplicates_and_missingness() -> None:
    quantified = quantify_matched_ions_with_receipt(
        "sample-1",
        (("PEPTIDE", 10.0), ("PEPTIDE", 30.0), ("OTHER", 20.0), ("MISSING", 0.0)),
    )
    receipt = quantified.receipt
    assert isinstance(receipt, QuantificationReceipt)
    assert receipt.version == "matched-ion-median-2"
    assert receipt.measurement_unit == "median_scaled_matched_ion_intensity"
    assert receipt.normalization_method == "sample_median_scaled"
    assert receipt.missingness_policy == "zero_signal_is_missing_no_imputation"
    assert receipt.input_observations == 4
    assert receipt.unique_peptides == 3
    assert receipt.observed_peptides == 2
    assert receipt.missing_peptides == 1
    assert receipt.duplicate_observations == 1
    assert receipt.raw_total_signal == 60.0
    assert receipt.raw_positive_median == 30.0
    assert receipt.normalization_target == 30.0
    assert receipt.normalized_total_signal == 60.0
    assert receipt.scale_factor == 1.0
    assert receipt.raw_peptide_signals == (
        ("MISSING", 0.0, True),
        ("OTHER", 20.0, False),
        ("PEPTIDE", 40.0, False),
    )
    assert receipt.as_dict()["normalized_peptide_signals"] == [
        ["MISSING", 0.0, True],
        ["OTHER", 20.0, False],
        ["PEPTIDE", 40.0, False],
    ]


@pytest.mark.parametrize("observation", [("", 1.0), ("P", -1.0), ("P", math.nan)])
def test_matched_ion_quantification_rejects_invalid_observations(
    observation: tuple[str, float],
) -> None:
    with pytest.raises(ValueError):
        quantify_matched_ions("sample-1", (observation,))


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


def test_protein_group_fdr_retains_decoy_competition_and_is_permutation_stable() -> None:
    target = Psm("target", "PEPTIDER", ("P1",), 1.0, 3, decoy=False)
    decoy = Psm("decoy", "PEPTIDEK", ("DECOY_P1",), 2.0, 3, decoy=True)
    forward, summary = infer_protein_group_candidates((target, decoy), q_value_threshold=0.01)
    reverse, reverse_summary = infer_protein_group_candidates(
        (decoy, target), q_value_threshold=0.01
    )
    assert forward == reverse
    assert summary == reverse_summary
    assert summary.decoy_candidates == 1
    assert summary.target_candidates == 1
    assert summary.accepted_targets == 0
    assert tuple(item.acceptance for item in forward) == ("rejected", "rejected")
    assert all(item.q_value is None for item in forward if item.status == "decoy")
    assert next(item for item in forward if item.status == "target").q_value == 1.0


def test_protein_group_fdr_abstains_mixed_collision_and_allows_decoy_only_rejection() -> None:
    collision = Psm(
        "collision",
        "PEPTIDER",
        ("P1", "DECOY_P1"),
        4.0,
        3,
        decoy=False,
        target_decoy_collision=True,
    )
    candidates, summary = infer_protein_group_candidates((collision,), q_value_threshold=0.01)
    assert summary.collision_candidates == 1
    assert candidates[0].status == "collision"
    assert candidates[0].acceptance == "abstained"
    assert candidates[0].q_value is None
    decoy = Psm("decoy", "PEPTIDER", ("DECOY_P1",), 4.0, 3, decoy=True)
    decoy_candidates, decoy_summary = infer_protein_group_candidates(
        (decoy,), q_value_threshold=0.01
    )
    assert decoy_summary.decoy_candidates == 1
    assert decoy_candidates[0].acceptance == "rejected"


class _FakeResponse:
    def __init__(self, payload: bytes, *, content_type: str = "application/mzml") -> None:
        self.payload = payload
        self._read = False
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
        }

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
    monkeypatch.setattr(
        pdc, "_open_download_response", lambda *_args, **_kwargs: _FakeResponse(payload)
    )
    destination = io.BytesIO()
    assert pdc.PdcClient().download_file(file, destination) == len(payload)
    assert destination.getvalue() == payload
    with pytest.raises(pdc.PdcError):
        pdc.PdcClient().download_file(file, io.BytesIO(), max_bytes=4)
    with pytest.raises(ValueError):
        pdc.PdcClient().download_file(file, io.BytesIO(), max_bytes=0)
    monkeypatch.setattr(
        pdc, "_open_download_response", lambda *_args, **_kwargs: _FakeResponse(payload)
    )
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
    monkeypatch.setattr(
        pdc, "_open_download_response", lambda *_args, **_kwargs: _FakeResponse(payload)
    )
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
    monkeypatch.setattr(
        pdc, "_open_download_response", lambda *_args, **_kwargs: _FakeResponse(payload)
    )
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


def test_pdc_download_receipt_binds_catalog_and_observed_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"catalog-attested-bytes"
    file = pdc.PdcFile(
        "PDC000204",
        "fixture.mzML",
        "Processed",
        "Proteome",
        "mzML",
        len(payload),
        md5(payload, usedforsecurity=False).hexdigest(),
        "https://pdc.cancer.gov/files/fixture.mzML",
        "https://pdc.cancer.gov/download/fixture",
    )
    snapshot = PdcStudySnapshot(
        "PDC000204",
        (("Proteome", "Processed", 1),),
        (file,),
        "https://pdc.cancer.gov/pdc/study/PDC000204",
        "a" * 64,
    )
    reference = SourceReference(
        "pdc:PDC000204:fixture",
        file.location,
        "application/mzml",
        "sha256:" + sha256(payload).hexdigest(),
        len(payload),
        "2026-08-18T00:00:00Z",
        "public metadata-bound research fixture",
    )
    monkeypatch.setattr(
        pdc, "_open_download_response", lambda *_args, **_kwargs: _FakeResponse(payload)
    )
    destination = io.BytesIO()
    receipt = pdc.PdcClient().download_file_with_receipt(file, snapshot, reference, destination)
    assert isinstance(receipt, PdcSourceReceipt)
    assert receipt.response_sha256 == "a" * 64
    assert receipt.observed_size == len(payload)
    assert receipt.as_dict()["file"] == {
        **pdc._file_dict(file),
    }
    with pytest.raises(pdc.PdcError, match="absent"):
        pdc.PdcClient().download_file_with_receipt(
            replace(file, file_name="not-listed.mzML"), snapshot, reference, io.BytesIO()
        )
    with pytest.raises(TypeError, match="PdcStudySnapshot"):
        pdc.PdcClient().download_file_with_receipt(
            file, cast("PdcStudySnapshot", object()), reference, io.BytesIO()
        )
    with pytest.raises(TypeError, match="SourceReference"):
        pdc.PdcClient().download_file_with_receipt(
            file, snapshot, cast("SourceReference", object()), io.BytesIO()
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("snapshot", object(), "PdcStudySnapshot"),
        ("file", object(), "PdcFile"),
        ("source_reference", object(), "SourceReference"),
        ("observed_sha256", "x", "SHA-256"),
        ("observed_md5", "x", "MD5"),
        ("observed_size", -1, "size"),
        ("observed_size", True, "size"),
    ],
)
def test_pdc_receipt_rejects_malformed_identity_fields(
    field: str, value: object, message: str
) -> None:
    payload = b"receipt"
    file = pdc.PdcFile(
        "PDC000204",
        "x.mzML",
        "Processed",
        "Proteome",
        "mzML",
        len(payload),
        md5(payload, usedforsecurity=False).hexdigest(),
        "locator",
    )
    snapshot = PdcStudySnapshot(
        "PDC000204",
        (("Proteome", "Processed", 1),),
        (file,),
        "https://pdc.cancer.gov/pdc/study/PDC000204",
        "a" * 64,
    )
    reference = SourceReference(
        "pdc:x",
        "locator",
        "application/mzml",
        "sha256:" + sha256(payload).hexdigest(),
        len(payload),
        "2026-08-18T00:00:00Z",
        "research fixture",
    )
    values: dict[str, object] = {
        "snapshot": snapshot,
        "file": file,
        "source_reference": reference,
        "observed_sha256": "sha256:" + sha256(payload).hexdigest(),
        "observed_md5": md5(payload, usedforsecurity=False).hexdigest(),
        "observed_size": len(payload),
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        PdcSourceReceipt(**values)  # type: ignore[arg-type]


def test_pdc_receipt_rejects_catalog_and_source_mismatches() -> None:
    payload = b"receipt-mismatch"
    file = pdc.PdcFile(
        "PDC000204",
        "x.mzML",
        "Processed",
        "Proteome",
        "mzML",
        len(payload),
        md5(payload, usedforsecurity=False).hexdigest(),
        "locator",
    )
    snapshot = PdcStudySnapshot(
        "PDC000204",
        (("Proteome", "Processed", 1),),
        (file,),
        "https://pdc.cancer.gov/pdc/study/PDC000204",
        "a" * 64,
    )
    reference = SourceReference(
        "pdc:x",
        "locator",
        "application/mzml",
        "sha256:" + sha256(payload).hexdigest(),
        len(payload),
        "2026-08-18T00:00:00Z",
        "research fixture",
    )
    valid = {
        "snapshot": snapshot,
        "file": file,
        "source_reference": reference,
        "observed_sha256": "sha256:" + sha256(payload).hexdigest(),
        "observed_md5": md5(payload, usedforsecurity=False).hexdigest(),
        "observed_size": len(payload),
    }
    cases = [
        (replace(snapshot, study_id="PDC000205"), "study"),
        (replace(snapshot, response_sha256="z" * 64), "SHA-256"),
        (replace(file, file_format="FASTA"), "mzML"),
        (replace(file, location="other"), "locator"),
        (replace(reference, sha256="sha256:" + "b" * 64), "observed bytes"),
        (replace(reference, byte_length=len(payload) + 1), "size"),
        (replace(file, file_size=len(payload) + 1), "size"),
        (replace(file, md5="0" * 32), "MD5"),
    ]
    for value, message in cases:
        changed = dict(valid)
        if isinstance(value, PdcStudySnapshot):
            changed["snapshot"] = value
        elif isinstance(value, pdc.PdcFile):
            changed["file"] = value
            changed["snapshot"] = replace(snapshot, files=(value,))
        else:
            changed["source_reference"] = value
        with pytest.raises(ValueError, match=message):
            PdcSourceReceipt(**changed)  # type: ignore[arg-type]


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


def test_protein_group_quantification_is_unique_signal_bound_and_deterministic() -> None:
    groups = infer_protein_groups(
        {
            "UNIQUE_A": ("P1",),
            "UNIQUE_B": ("P1",),
            "SHARED": ("P2", "P3"),
            "MISSING": ("P4",),
        }
    )
    quantified = quantify_protein_groups(
        tuple(reversed(groups)),
        {"UNIQUE_A": 10.0, "UNIQUE_B": 30.0, "SHARED": 5.0, "MISSING": 0.0},
        {"UNIQUE_A": 2, "UNIQUE_B": 1, "SHARED": 3},
    )
    assert tuple(item.group_accessions for item in quantified) == (("P1",), ("P2", "P3"), ("P4",))
    by_accessions = {item.group_accessions: item for item in quantified}
    shared_only = by_accessions[("P2", "P3")]
    assert shared_only.status == "non_quantifiable_shared_only"
    assert shared_only.primary_intensity is None
    assert shared_only.shared_signal == 5.0
    assert by_accessions[("P4",)].status == "missing"
    p1 = by_accessions[("P1",)]
    assert p1.status == "quantified"
    assert p1.primary_intensity == 20.0
    assert p1.unique_signal == 40.0
    assert p1.supporting_psms == 3
