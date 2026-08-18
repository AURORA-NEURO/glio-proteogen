"""Deep tests for the additive research-only proteomics foundation."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

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
        500.0,
        {"MPEPTIDER": ("P1",)},
        (132.0, 229.1, 358.1),
        (10.0, 20.0, 30.0),
        parameters=SearchParameters(fragment_tolerance_da=0.2, min_matched_ions=1),
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
