"""Adversarial tests for caller-bound precursor matching policy."""

from __future__ import annotations

from dataclasses import replace

import pytest

from glio_proteogen.research import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)

from .test_pipeline import _mzml


def _request(
    *, precursor_mz: str = "1087.508837466", tolerance_ppm: int = 20
) -> ResearchRunRequest:
    mzml = _mzml().replace(b"1087.508837466", precursor_mz.encode("ascii"))
    return ResearchRunRequest(
        sample_id="precursor-policy",
        mzml_source=mzml,
        fasta_source=b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
        precursor_tolerance_ppm=tolerance_ppm,
    )


def test_precursor_tolerance_is_applied_to_candidates_and_diagnostics() -> None:
    """A 1 ppm policy must reject a 1.07 ppm precursor error that 20 ppm accepts."""

    narrow = run_research_protein_inference(
        _request(precursor_mz="1087.510000000", tolerance_ppm=1)
    )
    broad = run_research_protein_inference(
        _request(precursor_mz="1087.510000000", tolerance_ppm=20)
    )

    assert narrow.psms == ()
    assert narrow.accepted_psms == ()
    assert dict(narrow.search_diagnostics)["precursor_tolerance_ppm"] == 1
    assert len(broad.psms) == 1
    assert broad.psms[0].precursor_error_ppm == pytest.approx(1.0690, rel=1e-3)
    assert dict(broad.search_diagnostics)["precursor_tolerance_ppm"] == 20
    assert narrow.result_digest != broad.result_digest
    assert dict(narrow.configuration)["precursor_tolerance_ppm"] == 1
    assert dict(broad.configuration)["precursor_tolerance_ppm"] == 20


def test_precursor_tolerance_is_replay_bound() -> None:
    request = _request(tolerance_ppm=20)
    result = run_research_protein_inference(request)

    assert replay_research_protein_inference(request, result).result_digest == result.result_digest
    changed_request = replace(request, precursor_tolerance_ppm=1)
    with pytest.raises(ValueError, match="replay"):
        replay_research_protein_inference(changed_request, result)


@pytest.mark.parametrize("value", [-1, 501, True, 1.5])
def test_precursor_tolerance_rejects_unbounded_or_non_integer_values(value: object) -> None:
    request = _request()
    object.__setattr__(request, "precursor_tolerance_ppm", value)
    with pytest.raises(ValueError, match="precursor_tolerance_ppm"):
        run_research_protein_inference(request)
