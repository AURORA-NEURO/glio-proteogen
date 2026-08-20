"""High-value validation and provenance closure for the research pipeline."""

from __future__ import annotations

from hashlib import sha256

import pytest

from glio_proteogen.research import (
    PdcFile,
    ResearchRunRequest,
    SourceReference,
    bind_pdc_mzml_source,
    run_research_protein_inference,
)

from .test_cohort_provenance import _metadata_snapshot
from .test_pipeline import _mzml
from .test_pipeline_mzidentml_provenance import _MZIDENTML


def _request(**changes: object) -> ResearchRunRequest:
    values: dict[str, object] = {
        "sample_id": "depth-closure",
        "mzml_source": _mzml(),
        "fasta_source": b">P1\nMPEPTIDER\n",
        "min_matched_ions": 1,
        "min_peptide_length": 7,
        "max_peptide_length": 12,
    }
    values.update(changes)
    return ResearchRunRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"fragment_tolerance_da": 0.0},
        {"precursor_tolerance_ppm": 501},
        {"min_matched_ions": 101},
        {"missed_cleavages": 5},
        {"min_peptide_length": 13, "max_peptide_length": 12},
        {"max_spectra": 0},
        {"max_variable_modifications": 4},
        {"variable_modifications": ("Oxidation@M",)},
        {"q_value_threshold": float("nan")},
        {"decoy_strategy": "unverified"},
        {"decoy_prefix": "bad prefix"},
    ],
)
def test_pipeline_rejects_unsafe_computation_controls(changes: dict[str, object]) -> None:
    if "max_variable_modifications" in changes or "variable_modifications" in changes:
        with pytest.raises(ValueError):
            _request(**changes)
        return
    request = _request(**changes)
    with pytest.raises(ValueError):
        run_research_protein_inference(request)


def test_request_constructor_closes_size_policy_and_metadata_attachment() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        _request(max_bytes=0)
    with pytest.raises(TypeError, match="quantification_policy"):
        _request(quantification_policy=object())
    with pytest.raises(TypeError, match="external_pdc_metadata_snapshot"):
        _request(external_pdc_metadata_snapshot=object())
    with pytest.raises(ValueError, match="requires an external PDC file"):
        _request(external_pdc_metadata_snapshot=_metadata_snapshot())


def test_pdc_binding_rejects_types_before_byte_access() -> None:
    request = _request()
    with pytest.raises(TypeError, match="pdc_file"):
        bind_pdc_mzml_source(request, object(), object())  # type: ignore[arg-type]
    data = b"raw"
    digest = "sha256:" + sha256(data).hexdigest()
    source = SourceReference(
        source_id="pdc:depth",
        locator="https://pdc.cancer.gov/files/depth.mzML",
        media_type="application/mzml",
        sha256=digest,
        byte_length=len(data),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="fixture",
    )
    declaration = PdcFile(
        study_id="PDC000204",
        file_name="depth.mzML",
        file_type="processed_mzML",
        data_category="Proteome",
        file_format="mzML",
        file_size=len(data),
        md5=None,
        location=source.locator,
    )
    with pytest.raises(TypeError, match="source_reference"):
        bind_pdc_mzml_source(request, declaration, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pdc_snapshot"):
        bind_pdc_mzml_source(request, declaration, source, pdc_snapshot=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pdc_metadata_snapshot"):
        bind_pdc_mzml_source(
            request,
            declaration,
            source,
            pdc_metadata_snapshot=object(),  # type: ignore[arg-type]
        )


def test_mzidentml_structure_is_present_in_result_projection() -> None:
    result = run_research_protein_inference(_request(mzidentml_source=_MZIDENTML))
    projection = result.as_dict()
    assert projection["mzidentml_sha256"] == result.mzidentml_structure.sha256  # type: ignore[union-attr]
    assert projection["mzidentml_structure"] == result.mzidentml_structure.as_dict()  # type: ignore[union-attr]


def test_metadata_snapshot_mismatch_is_rejected_before_execution() -> None:
    snapshot = _metadata_snapshot()
    request = _request()
    data = request.mzml_source
    assert isinstance(data, bytes)
    locator = "https://pdc.cancer.gov/files/depth.mzML"
    source = SourceReference(
        source_id="pdc:depth",
        locator=locator,
        media_type="application/mzml",
        sha256="sha256:" + sha256(data).hexdigest(),
        byte_length=len(data),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="fixture",
    )
    declaration = PdcFile(
        study_id="PDC999999",
        file_name="depth.mzML",
        file_type="processed_mzML",
        data_category="Proteome",
        file_format="mzML",
        file_size=len(data),
        md5=None,
        location=locator,
    )
    with pytest.raises(ValueError, match="study"):
        _request(
            external_pdc_metadata_snapshot=snapshot,
            external_pdc_file=declaration,
            external_source_reference=source,
        )
