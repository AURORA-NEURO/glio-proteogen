from __future__ import annotations

import base64
import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest
from tools.verify_research_pilot import verify as verify_pilot_evidence

from glio_proteogen.research import (
    PilotError,
    PilotLimits,
    PilotPolicy,
    PilotRequest,
    SearchParameters,
    result_json,
    run_pilot,
    verify_pilot_replay,
)
from glio_proteogen.research.public_proteomics.provenance import sha256_digest

_ROOT = Path(__file__).parents[2]
_METADATA = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.metadata.json"
_NO_SPECTRA = _ROOT / "tests" / "fixtures" / "m01_03" / "mzml.valid.mzML"


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _mzml_with_ms2() -> bytes:
    return (
        '<mzML xmlns="http://psi.hupo.org/ms/mzml"><run><spectrumList>'
        '<spectrum id="pilot-scan-1"><cvParam accession="MS:1000511" value="2"/>'
        "<binaryDataArrayList>"
        + _array((132.0, 229.1, 358.1), "MS:1000514")
        + _array((10.0, 20.0, 30.0), "MS:1000515")
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()


def _request(mzml: bytes) -> PilotRequest:
    return PilotRequest(
        metadata_response=_METADATA.read_bytes(),
        fasta_bytes=b">P1 nonclinical fixture\nMPEPTIDER\n",
        mzml_bytes=mzml,
        sample_id="pilot-sample",
        parameters=SearchParameters(
            fragment_tolerance_da=0.2,
            min_matched_ions=1,
        ),
    )


def test_positive_pilot_is_content_addressed_and_replayable() -> None:
    request = _request(_mzml_with_ms2())
    result = run_pilot(request)
    assert result.status == "COMPLETED"
    assert result.abstention_reason is None
    assert result.ms2_spectra == 1
    assert result.searched_spectra == 1
    assert len(result.matched_psms) == 1
    assert result.matched_psms[0].peptide == "MPEPTIDER"
    assert result.protein_groups[0].accessions == ("P1",)
    assert result.signal_proxies[0].normalized_peak_signal == pytest.approx(60.0)
    assert result.policy.network_access is False
    assert "clinical" in " ".join(result.limitations)
    assert verify_pilot_replay(request, result).as_dict() == result.as_dict()
    assert json.loads(result_json(result))["result_digest"] == result.result_digest


def test_checked_in_empty_spectrum_fixture_abstains_safely() -> None:
    result = run_pilot(_request(_NO_SPECTRA.read_bytes()))
    assert result.status == "ABSTAINED"
    assert result.abstention_reason == "NO_MS2_SPECTRA"
    assert result.matched_psms == ()
    assert result.protein_groups == ()
    assert result.signal_proxies == ()


def test_strict_precursor_policy_abstains_without_precursor_metadata() -> None:
    request = _request(_mzml_with_ms2())
    request = replace(
        request,
        parameters=SearchParameters(
            fragment_tolerance_da=0.2,
            min_matched_ions=1,
            require_precursor_mz=True,
        ),
    )
    result = run_pilot(request)
    assert result.status == "ABSTAINED"
    assert result.abstention_reason == "NO_SUPPORTED_PSM"
    assert result.searched_spectra == 1


def test_policy_is_closed_against_network_or_claim_expansion() -> None:
    with pytest.raises(PilotError, match="network_access"):
        PilotPolicy(network_access=True)  # type: ignore[arg-type]
    with pytest.raises(PilotError, match="clinical_claims"):
        PilotPolicy(clinical_claims=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_input_bytes", 0), ("max_spectra", 0), ("max_peptides", 0), ("max_psms", 0)],
)
def test_limits_reject_zero_or_negative_caps(field: str, value: int) -> None:
    with pytest.raises(PilotError):
        PilotLimits(**{field: value})


def test_request_rejects_non_bytes_and_oversized_input() -> None:
    with pytest.raises(PilotError, match="metadata_response"):
        PilotRequest(metadata_response="not-bytes", fasta_bytes=b"x", mzml_bytes=b"x")  # type: ignore[arg-type]
    with pytest.raises(PilotError, match="fasta_bytes"):
        PilotRequest(
            metadata_response=b"{}",
            fasta_bytes=b"x" * 5,
            mzml_bytes=b"x",
            limits=PilotLimits(max_input_bytes=4),
        )


def test_request_rejects_invalid_sample_timestamp_and_search_bounds() -> None:
    with pytest.raises(PilotError, match="sample"):
        PilotRequest(metadata_response=b"{}", fasta_bytes=b"x", mzml_bytes=b"x", sample_id=" ")
    with pytest.raises(PilotError, match="sample"):
        PilotRequest(
            metadata_response=b"{}", fasta_bytes=b"x", mzml_bytes=b"x", retrieved_at="not-utc"
        )
    invalid_fragment = SearchParameters.__new__(SearchParameters)
    object.__setattr__(invalid_fragment, "fragment_tolerance_da", 0.0)
    object.__setattr__(invalid_fragment, "min_matched_ions", 1)
    with pytest.raises(PilotError, match="fragment tolerance"):
        PilotRequest(
            metadata_response=b"{}",
            fasta_bytes=b"x",
            mzml_bytes=b"x",
            parameters=invalid_fragment,
        )
    invalid_ions = SearchParameters.__new__(SearchParameters)
    object.__setattr__(invalid_ions, "fragment_tolerance_da", 0.2)
    object.__setattr__(invalid_ions, "min_matched_ions", 0)
    with pytest.raises(PilotError, match="minimum matched ions"):
        PilotRequest(
            metadata_response=b"{}",
            fasta_bytes=b"x",
            mzml_bytes=b"x",
            parameters=invalid_ions,
        )


def test_pilot_abstains_when_search_space_exceeds_cap() -> None:
    request = _request(_mzml_with_ms2())
    request = replace(
        request,
        fasta_bytes=b">P1\nMPEPTIDER\n>P2\nPEPTIDEK\n",
        limits=PilotLimits(max_peptides=1),
    )
    with pytest.raises(PilotError, match="search space"):
        run_pilot(request)


def test_pilot_stops_at_psm_limit() -> None:
    request = replace(_request(_mzml_with_ms2()), limits=PilotLimits(max_psms=1))
    result = run_pilot(request)
    assert result.status == "COMPLETED"
    assert len(result.matched_psms) == 1


def test_replay_detects_tampered_receipt() -> None:
    request = _request(_mzml_with_ms2())
    result = run_pilot(request)
    tampered = replace(result, sample_id="tampered")
    with pytest.raises(PilotError, match="replay"):
        verify_pilot_replay(request, tampered)

    changed_parameters = replace(
        result,
        parameters=SearchParameters(fragment_tolerance_da=0.1, min_matched_ions=1),
    )
    with pytest.raises(PilotError, match="replay"):
        verify_pilot_replay(request, changed_parameters)


def test_replay_binds_full_psm_measurement_and_collision_projection() -> None:
    request = _request(_mzml_with_ms2())
    result = run_pilot(request)
    original = result.matched_psms[0]
    tampered_psm = replace(
        original,
        matched_intensity=original.matched_intensity + 1.0,
        mean_fragment_error_da=original.mean_fragment_error_da + 0.01,
        precursor_error_ppm=1.0,
        target_decoy_collision=True,
    )
    tampered = replace(result, matched_psms=(tampered_psm,), result_digest="")
    payload = tampered.as_dict()
    payload.pop("result_digest")
    tampered = replace(tampered, result_digest=sha256_digest(payload))
    with pytest.raises(PilotError, match="replay"):
        verify_pilot_replay(request, tampered)


def test_replay_binds_resource_limits_even_when_output_is_unchanged() -> None:
    request = _request(_mzml_with_ms2())
    result = run_pilot(request)
    changed_limits = replace(request, limits=PilotLimits(max_psms=1, max_spectra=1))
    assert run_pilot(changed_limits).as_dict() != result.as_dict()
    with pytest.raises(PilotError, match="replay"):
        verify_pilot_replay(changed_limits, result)


def test_checked_in_pilot_evidence_and_package_receipt_are_closed() -> None:
    receipt = verify_pilot_evidence(_ROOT)
    assert receipt["module_id"] == "RESEARCH-PUBLIC-PROTEOMICS-PILOT"
    assert receipt["package"] == {
        "passed": True,
        "artifacts": ["wheel", "sdist"],
    }
