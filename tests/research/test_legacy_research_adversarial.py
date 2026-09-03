"""Adversarial closure tests for the legacy research computation lane."""

from __future__ import annotations

import io
from dataclasses import replace
from hashlib import md5, sha256
from typing import Any, cast

import pytest
from evals.research_proteomics.run import build_cohort_supported_request

from glio_proteogen.research import (
    CohortLabelContrast,
    PdcFile,
    PeptideQuant,
    QuantificationPolicy,
    ResearchCohortRequest,
    ResearchCohortResult,
    ResearchCohortSample,
    ResearchRunRequest,
    SourceReference,
    aggregate_cohort_evidence,
    bind_pdc_mzml_source,
    median_normalize,
    quantify_matched_ions_with_receipt,
    replay_research_protein_inference,
    run_research_cohort,
    run_research_protein_inference,
)
from glio_proteogen.research.cohort import _median_mad, _require_positive
from glio_proteogen.research.pipeline import (
    _read_bytes,
    _result_digest,
    _validate_pdc_file_binding,
    _validate_request,
)
from glio_proteogen.research.protein import (
    _validate_decoy_prefix,
    _validate_group_psm,
    infer_protein_group_candidates,
)
from glio_proteogen.research.public_proteomics.aggregate import _feature_record
from glio_proteogen.research.quantification import (
    _finite_median,
    _finite_sum,
    _interquartile_range,
)
from glio_proteogen.research.search import Psm


def _mzml() -> bytes:
    return (
        b'<mzML><run><spectrumList><spectrum id="scan=1">'
        b'<cvParam accession="MS:1000511" value="2"/>'
        b"<precursorList><precursor><selectedIonList><selectedIon>"
        b'<cvParam accession="MS:1000744" value="1087.508837466"/>'
        b'<cvParam accession="MS:1000041" value="1"/>'
        b"</selectedIon></selectedIonList></precursor></precursorList>"
        b"<binaryDataArrayList></binaryDataArrayList></spectrum>"
        b"</spectrumList></run></mzML>"
    )


def _scaled_receipt():
    return quantify_matched_ions_with_receipt(
        "receipt-sample",
        (("P1", 2.0), ("P2", 4.0), ("P1", 3.0)),
    ).receipt


def _reject_receipt(receipt: object, **changes: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(receipt, **changes)


def test_quantification_receipt_rejects_malformed_scalar_fields() -> None:
    receipt = _scaled_receipt()
    _reject_receipt(receipt, sample_id=" bad")
    _reject_receipt(receipt, version="unknown")
    _reject_receipt(receipt, measurement_unit="matched_ion_intensity_arbitrary")
    _reject_receipt(receipt, raw_total_signal=True)
    _reject_receipt(receipt, normalized_total_signal=float("inf"))
    _reject_receipt(receipt, raw_positive_mad=-1.0)
    _reject_receipt(receipt, unique_peptides=True)
    _reject_receipt(receipt, input_observations=1)
    _reject_receipt(receipt, duplicate_observations=0)
    _reject_receipt(receipt, observed_peptides=1)
    _reject_receipt(receipt, below_loq_peptides=1)
    _reject_receipt(receipt, quantifiable_peptides=1)
    _reject_receipt(receipt, positive_signal_fraction=2.0)
    _reject_receipt(receipt, max_input_observations=0)
    _reject_receipt(receipt, observation_digest="A" * 64)


def test_quantification_receipt_rejects_malformed_signal_projections() -> None:
    receipt = _scaled_receipt()
    raw = receipt.raw_peptide_signals
    normalized = receipt.normalized_peptide_signals
    _reject_receipt(receipt, raw_peptide_signals=list(raw))
    _reject_receipt(receipt, raw_peptide_signals=(("P1", 5.0),))
    _reject_receipt(receipt, raw_peptide_signals=(("P1", 5.0, 0), raw[1]))
    _reject_receipt(receipt, raw_peptide_signals=(raw[1], raw[0]))
    _reject_receipt(receipt, normalized_peptide_signals=normalized[:1])
    _reject_receipt(
        receipt,
        normalized_peptide_signals=(("PX", normalized[0][1], normalized[0][2]), normalized[1]),
    )
    _reject_receipt(receipt, raw_peptide_statuses=list(receipt.raw_peptide_statuses))
    _reject_receipt(receipt, raw_peptide_statuses=(("P1",),))
    _reject_receipt(receipt, raw_peptide_statuses=receipt.raw_peptide_statuses[:1])
    _reject_receipt(
        receipt,
        raw_peptide_statuses=(("PX", "quantified"), receipt.raw_peptide_statuses[1]),
    )
    _reject_receipt(receipt, raw_peptide_statuses=())
    _reject_receipt(receipt, normalized_peptide_statuses=())
    _reject_receipt(
        receipt,
        normalized_peptide_statuses=(("P1", "below_loq"), ("P2", "quantified")),
    )


def test_quantification_receipt_rejects_non_derived_projections() -> None:
    receipt = _scaled_receipt()
    raw = receipt.raw_peptide_signals
    normalized = receipt.normalized_peptide_signals
    _reject_receipt(
        receipt,
        normalized_peptide_signals=(
            (normalized[0][0], normalized[0][1], True),
            normalized[1],
        ),
    )
    _reject_receipt(
        receipt,
        normalized_peptide_signals=(
            (normalized[0][0], normalized[0][1] + 1.0, False),
            normalized[1],
        ),
    )
    _reject_receipt(
        receipt,
        raw_peptide_signals=((raw[0][0], raw[0][1], True), raw[1]),
        normalized_peptide_signals=((normalized[0][0], 0.0, True), normalized[1]),
    )
    _reject_receipt(
        receipt,
        raw_peptide_signals=((raw[0][0], 0.0, False), raw[1]),
        normalized_peptide_signals=((normalized[0][0], 0.0, False), normalized[1]),
    )
    _reject_receipt(receipt, positive_signal_fraction=0.5)
    _reject_receipt(receipt, signal_quality="single_positive_signal")
    _reject_receipt(receipt, raw_total_signal=receipt.raw_total_signal + 1.0)
    _reject_receipt(
        receipt,
        normalized_total_signal=receipt.normalized_total_signal + 1.0,
    )
    _reject_receipt(receipt, raw_positive_median=receipt.raw_positive_median + 1.0)
    _reject_receipt(receipt, raw_positive_mad=receipt.raw_positive_mad + 1.0)
    _reject_receipt(receipt, raw_positive_iqr=receipt.raw_positive_iqr + 1.0)
    _reject_receipt(receipt, raw_robust_cv=receipt.raw_robust_cv + 1.0)
    wrong_statuses = (("P1", "below_loq"), ("P2", "quantified"))
    _reject_receipt(
        receipt,
        raw_peptide_statuses=wrong_statuses,
        normalized_peptide_statuses=wrong_statuses,
    )
    _reject_receipt(receipt, normalization_target=1.0)


def test_quantification_receipt_rejects_loq_and_empty_scale_forgery() -> None:
    loq_receipt = quantify_matched_ions_with_receipt(
        "loq-sample",
        (("P1", 1.0), ("P2", 5.0)),
        policy=QuantificationPolicy(normalization_method="none_v1", limit_of_quantification=2.0),
    ).receipt
    _reject_receipt(loq_receipt, below_loq_peptides=0)
    _reject_receipt(loq_receipt, normalization_target=1.0)
    empty_receipt = quantify_matched_ions_with_receipt("empty-sample", ()).receipt
    _reject_receipt(empty_receipt, normalization_target=1.0, scale_factor=1.0)


def test_quantification_rejects_bad_observations_and_nonfinite_growth() -> None:
    with pytest.raises(TypeError, match="QuantificationPolicy"):
        quantify_matched_ions_with_receipt("sample", (), policy=cast("Any", object()))
    with pytest.raises(ValueError, match="sample_id"):
        quantify_matched_ions_with_receipt("bad sample", ())
    with pytest.raises(ValueError, match="tuples"):
        quantify_matched_ions_with_receipt("sample", cast("Any", (["P1", 1.0],)))
    with pytest.raises(ValueError, match="peptide"):
        quantify_matched_ions_with_receipt("sample", (("", 1.0),))
    with pytest.raises(ValueError, match="intensity"):
        quantify_matched_ions_with_receipt("sample", (("P1", float("nan")),))
    with pytest.raises(ValueError, match="remain finite"):
        quantify_matched_ions_with_receipt(
            "sample",
            (("P1", float.fromhex("0x1.fffffffffffffp+1023")),) * 2,
        )
    with pytest.raises(ValueError, match="remain finite"):
        _finite_sum((float("inf"),), "test sum")
    with pytest.raises(ValueError, match="remain finite"):
        _finite_median((float("inf"),), "test median")
    with pytest.raises(ValueError, match="remain finite"):
        _interquartile_range(
            (-float.fromhex("0x1.fffffffffffffp+1023"),) * 2
            + (float.fromhex("0x1.fffffffffffffp+1023"),) * 2
        )


@pytest.mark.parametrize(
    "item",
    [
        object(),
        PeptideQuant("bad sample", "P1", 1.0),
        PeptideQuant("sample", "bad peptide", 1.0),
        PeptideQuant("sample", "P1", float("nan")),
        PeptideQuant("sample", "P1", -1.0),
        PeptideQuant("sample", "P1", 1.0, missing=cast("Any", 1)),
    ],
)
def test_median_normalize_rejects_malformed_quant_values(item: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        median_normalize(cast("Any", (item,)))


def test_median_normalize_rejects_nonfinite_scale_and_product() -> None:
    tiny = float.fromhex("0x0.0000000000001p-1022")
    maximum = float.fromhex("0x1.fffffffffffffp+1023")
    with pytest.raises(ValueError, match="scale"):
        median_normalize(
            (
                PeptideQuant("tiny", "P1", tiny),
                PeptideQuant("large", "P2", 1.0),
            )
        )
    with pytest.raises(ValueError, match="intensity"):
        median_normalize(
            (
                PeptideQuant("mixed", "P1", 1e-308),
                PeptideQuant("mixed", "P2", maximum),
                PeptideQuant("large", "P3", maximum),
            )
        )


def _pdc_binding() -> tuple[bytes, PdcFile, SourceReference]:
    payload = _mzml()
    pdc_file = PdcFile(
        "PDC000204",
        "fixture.mzML",
        "processed",
        "Proteome",
        "mzML",
        len(payload),
        md5(payload, usedforsecurity=False).hexdigest(),
        "memory://PDC000204/fixture.mzML",
    )
    reference = SourceReference(
        "pdc:PDC000204:fixture",
        pdc_file.location,
        "application/mzml",
        "sha256:" + sha256(payload).hexdigest(),
        len(payload),
        "2026-08-28T00:00:00Z",
        "public research fixture",
    )
    return payload, pdc_file, reference


def test_pipeline_input_boundary_covers_each_supported_source_type() -> None:
    assert _read_bytes(bytearray(b"x"), 1) == b"x"
    assert _read_bytes("x", 1) == b"x"
    for source in (b"xx", bytearray(b"xx"), "xx", io.BytesIO(b"xx")):
        with pytest.raises(ValueError, match="byte limit"):
            _read_bytes(source, 1)
    with pytest.raises(ValueError, match="max_bytes"):
        ResearchRunRequest("sample", b"x", b">P1\nMPEPTIDER\n", max_bytes=0)
    with pytest.raises(TypeError, match="QuantificationPolicy"):
        ResearchRunRequest(
            "sample",
            b"x",
            b">P1\nMPEPTIDER\n",
            quantification_policy=cast("Any", object()),
        )
    with pytest.raises(ValueError, match="between zero and three"):
        ResearchRunRequest(
            "sample",
            b"x",
            b">P1\nMPEPTIDER\n",
            max_variable_modifications=4,
        )
    with pytest.raises(TypeError, match="external_pdc_file"):
        ResearchRunRequest(
            "sample",
            b"x",
            b">P1\nMPEPTIDER\n",
            external_pdc_file=cast("Any", object()),
        )


def test_pipeline_pdc_binding_rejects_each_identity_mismatch() -> None:
    payload, pdc_file, reference = _pdc_binding()
    with pytest.raises(ValueError, match="source reference"):
        _validate_pdc_file_binding(pdc_file, None, payload)
    with pytest.raises(ValueError, match="mzML format"):
        _validate_pdc_file_binding(replace(pdc_file, file_format="raw"), reference, payload)
    with pytest.raises(ValueError, match="locator"):
        _validate_pdc_file_binding(
            replace(pdc_file, location="memory://other"), reference, payload
        )
    with pytest.raises(ValueError, match="size"):
        _validate_pdc_file_binding(replace(pdc_file, file_size=1), reference, payload)
    with pytest.raises(TypeError, match="MD5"):
        _validate_pdc_file_binding(
            replace(pdc_file, md5=cast("Any", 1)), reference, payload
        )
    with pytest.raises(ValueError, match="MD5"):
        _validate_pdc_file_binding(replace(pdc_file, md5="0" * 32), reference, payload)
    with pytest.raises(ValueError, match="source reference"):
        _validate_pdc_file_binding(
            replace(pdc_file, md5=None), replace(reference, byte_length=1), payload
        )


def test_pipeline_public_pdc_binding_rejects_bad_types_and_references() -> None:
    payload, pdc_file, reference = _pdc_binding()
    request = ResearchRunRequest("sample", payload, b">P1\nMPEPTIDER\n")
    with pytest.raises(TypeError, match="pdc_file"):
        bind_pdc_mzml_source(request, cast("Any", object()), reference)
    with pytest.raises(TypeError, match="source_reference"):
        bind_pdc_mzml_source(request, pdc_file, cast("Any", object()))
    with pytest.raises(TypeError, match="pdc_snapshot"):
        bind_pdc_mzml_source(request, pdc_file, reference, pdc_snapshot=cast("Any", object()))
    with pytest.raises(ValueError, match="mzML format"):
        bind_pdc_mzml_source(request, replace(pdc_file, file_format="raw"), reference)
    with pytest.raises(ValueError, match="locator"):
        bind_pdc_mzml_source(
            request,
            replace(pdc_file, location="memory://other"),
            reference,
        )
    with pytest.raises(ValueError, match="source reference"):
        bind_pdc_mzml_source(request, pdc_file, replace(reference, byte_length=1))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fragment_tolerance_da", 6.0, "fragment_tolerance_da"),
        ("min_matched_ions", 101, "min_matched_ions"),
        ("decoy_strategy", "invented", "decoy_strategy"),
        ("decoy_prefix", "bad prefix", "decoy_prefix"),
    ],
)
def test_pipeline_rejects_controls_above_closed_limits(
    field: str, value: object, message: str
) -> None:
    request = ResearchRunRequest("sample", _mzml(), b">P1\nMPEPTIDER\n")
    object.__setattr__(request, field, value)
    with pytest.raises(ValueError, match=message):
        _validate_request(request)


def test_pipeline_requires_site_limit_for_variable_modifications() -> None:
    request = ResearchRunRequest(
        "sample",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        variable_modifications=("UNIMOD:35",),
    )
    with pytest.raises(ValueError, match="positive site limit"):
        _validate_request(request)


def test_pipeline_external_reference_and_optional_receipt_are_replay_bound() -> None:
    payload, _, reference = _pdc_binding()
    request = ResearchRunRequest(
        "sample",
        payload,
        b">P1\nMPEPTIDER\n",
        external_source_reference=replace(reference, byte_length=1),
    )
    with pytest.raises(ValueError, match="external source reference"):
        run_research_protein_inference(request)

    valid_request = ResearchRunRequest("valid-sample", payload, b">P1\nMPEPTIDER\n")
    result = run_research_protein_inference(valid_request)
    assert result.limitations == result.evidence.limitations
    without_receipt = replace(result, search_space_receipt=None, result_digest="")
    projection = without_receipt.as_dict()
    projection.pop("result_digest")
    without_receipt = replace(without_receipt, result_digest=_result_digest(projection))
    with pytest.raises(ValueError, match="replay"):
        replay_research_protein_inference(valid_request, without_receipt)


def _cohort_result() -> ResearchCohortResult:
    samples = tuple(
        ResearchCohortSample(
            sample_id=sample_id,
            request=build_cohort_supported_request(sample_id),
            cohort_label="fixture-cohort",
            replicate_label=replicate,
        )
        for sample_id, replicate in (("sample-a", "r1"), ("sample-b", "r2"))
    )
    return run_research_cohort(ResearchCohortRequest(samples))


def _configuration(
    result: ResearchCohortResult, **changes: object
) -> tuple[tuple[str, object], ...]:
    configuration = dict(result.configuration)
    configuration.update(changes)
    return tuple(sorted(configuration.items()))


def _reject_cohort(result: ResearchCohortResult, **changes: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        aggregate_cohort_evidence(replace(result, **changes))


def test_cohort_contrast_rejects_internally_inconsistent_descriptive_state() -> None:
    contrast = CohortLabelContrast(
        cohort_label_a="case",
        cohort_label_b="control",
        group_accessions=("P1",),
        label_a_median=10.0,
        label_b_median=20.0,
        median_difference=-10.0,
        median_ratio=0.5,
        log2_median_ratio=-1.0,
        label_a_observed_replicates=2,
        label_b_observed_replicates=2,
        label_a_missingness_rate=0.0,
        label_b_missingness_rate=0.0,
        label_a_status="descriptive",
        label_b_status="descriptive",
        status="descriptive",
    )
    with pytest.raises(ValueError, match="label QC"):
        replace(contrast, label_a_status="abstained_label_qc")
    with pytest.raises(ValueError, match="ratio"):
        replace(contrast, median_ratio=0.6)
    with pytest.raises(ValueError, match="log2 ratio"):
        replace(contrast, log2_median_ratio=0.0)


def test_cohort_evidence_rejects_non_replayable_configuration_and_digest() -> None:
    result = _cohort_result()
    _reject_cohort(result, configuration=_configuration(result, cohort_qc_policy=None))
    _reject_cohort(
        result,
        configuration=_configuration(
            result,
            cohort_qc_policy={
                "min_replicates": 0,
                "max_missingness_rate": 0.5,
                "min_observed_groups": 1,
            },
        ),
    )
    _reject_cohort(
        result,
        configuration=_configuration(result, cohort_normalization_policy="invented"),
    )
    normalized = ((result.normalized_matrix[0][0], (21.0, 20.0)),)
    _reject_cohort(result, normalized_matrix=normalized)
    _reject_cohort(result, result_digest="0" * 64)
    with pytest.raises(TypeError, match="ResearchCohortResult"):
        aggregate_cohort_evidence(cast("Any", object()))


def test_cohort_matrix_projection_rejects_order_shape_and_value_forgery() -> None:
    result = _cohort_result()
    group, values = result.matrix[0]
    _reject_cohort(result, sample_ids=tuple(reversed(result.sample_ids)))
    _reject_cohort(result, matrix=((('PX',), values),))
    _reject_cohort(result, raw_matrix=())
    _reject_cohort(result, normalized_matrix=((('PX',), values),))
    short = ((group, values[:1]),)
    _reject_cohort(result, matrix=short, raw_matrix=short)
    _reject_cohort(result, normalized_matrix=((group, values[:1]),))
    invalid = ((group, (float("nan"), values[1])),)
    _reject_cohort(result, matrix=invalid, raw_matrix=invalid)
    _reject_cohort(result, sample_qc=tuple(reversed(result.sample_qc)))
    _reject_cohort(result, group_qc=())
    _reject_cohort(result, sample_scales=tuple(reversed(result.sample_scales)))


def test_cohort_matrix_projection_rejects_qc_and_scale_forgery() -> None:
    result = _cohort_result()
    bad_qc = (
        replace(
            result.sample_qc[0],
            quantified_groups=result.sample_qc[0].quantified_groups + 1,
        ),
        result.sample_qc[1],
    )
    _reject_cohort(result, sample_qc=bad_qc)
    bad_scale_link = (
        replace(result.sample_qc[0], normalization_scale=2.0),
        result.sample_qc[1],
    )
    _reject_cohort(result, sample_qc=bad_scale_link)
    with pytest.raises(RuntimeError, match="positive"):
        _require_positive(None)
    assert _median_mad(()) == (None, None)


@pytest.mark.parametrize(
    "psm",
    [
        Psm("", "PEPTIDE", ("P1",), 1.0, 1, decoy=False),
        Psm("scan=1", "PEPTIDE", (), 1.0, 1, decoy=False),
        Psm("scan=1", "PEPTIDE", ("",), 1.0, 1, decoy=False),
        Psm("scan=1", "PEPTIDE", ("P1",), float("nan"), 1, decoy=False),
    ],
)
def test_protein_group_psm_validation_rejects_malformed_evidence(psm: Psm) -> None:
    with pytest.raises(ValueError):
        _validate_group_psm(psm, decoy_prefix="DECOY_")


def test_protein_group_controls_reject_nonfinite_threshold_and_prefix() -> None:
    with pytest.raises(ValueError, match="q_value_threshold"):
        infer_protein_group_candidates((), q_value_threshold=float("nan"))
    with pytest.raises(ValueError, match="decoy_prefix"):
        _validate_decoy_prefix("bad prefix")


class _Summary:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def as_dict(self) -> dict[str, object]:
        return dict(self.payload)


def test_public_aggregate_feature_projection_rejects_unsupported_shapes() -> None:
    with pytest.raises(TypeError, match="identity fields"):
        _feature_record(
            "source",
            cast(
                "Any",
                _Summary({"format": 1, "byte_length": 1, "sha256": "digest"}),
            ),
        )
    record = _feature_record(
        "source",
        cast(
            "Any",
            _Summary(
                {
                    "format": "fixture",
                    "byte_length": 1,
                    "sha256": "digest",
                    "flag": True,
                }
            ),
        ),
    )
    assert dict(record.attributes)["flag"] == 1
    with pytest.raises(TypeError, match="unsupported structural attribute"):
        _feature_record(
            "source",
            cast(
                "Any",
                _Summary(
                    {
                        "format": "fixture",
                        "byte_length": 1,
                        "sha256": "digest",
                        "value": object(),
                    }
                ),
            ),
        )
