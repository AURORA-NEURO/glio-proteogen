"""Adversarial research-only quantification policy coverage."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

from glio_proteogen.research import (
    PeptideQuant,
    QuantificationPolicy,
    QuantificationReceipt,
    ResearchRunRequest,
    median_normalize,
    quantify_matched_ions_with_receipt,
    replay_research_protein_inference,
    run_research_protein_inference,
)


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


def test_policy_rejects_open_ended_units_and_controls() -> None:
    with pytest.raises(ValueError, match="arbitrary matched-ion"):
        QuantificationPolicy(measurement_unit="molar")
    with pytest.raises(ValueError, match="normalization_method"):
        QuantificationPolicy(normalization_method="mean_scaled")
    with pytest.raises(ValueError, match="missingness_policy"):
        QuantificationPolicy(missingness_policy="zero_imputed")
    with pytest.raises(ValueError, match="finite"):
        QuantificationPolicy(limit_of_quantification=float("nan"))
    with pytest.raises(ValueError, match="max_input_observations"):
        QuantificationPolicy(max_input_observations=0)
    with pytest.raises(ValueError, match="limit_of_quantification"):
        QuantificationPolicy(limit_of_quantification=True)


@pytest.mark.parametrize("intensity", [True, -1.0, float("nan"), float("inf"), "1.0"])
def test_quantification_rejects_nonphysical_observation_values(intensity: object) -> None:
    with pytest.raises(ValueError, match="intensity"):
        quantify_matched_ions_with_receipt("sample", (("P1", intensity),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "observations",
    [
        (("P1", 1e308), ("P1", 1e308)),
        (("P1", 1e308), ("P2", 1e308)),
    ],
)
def test_quantification_rejects_finite_inputs_that_overflow_derived_signal(
    observations: tuple[tuple[str, float], ...],
) -> None:
    with pytest.raises(ValueError, match="finite"):
        quantify_matched_ions_with_receipt("overflow", observations)


@pytest.mark.parametrize(
    "value",
    [
        PeptideQuant("sample", "P1", -1.0),
        PeptideQuant("sample", "P1", float("nan")),
        PeptideQuant("sample", "P1", intensity=True),
    ],
)
def test_direct_normalization_rejects_invalid_peptide_values(value: PeptideQuant) -> None:
    with pytest.raises(ValueError, match="intensity"):
        median_normalize((value,))


def test_loq_and_no_normalization_are_explicit_and_non_imputing() -> None:
    policy = QuantificationPolicy(
        normalization_method="none_v1",
        limit_of_quantification=4.0,
    )
    quantified = quantify_matched_ions_with_receipt(
        "sample-loq",
        (("P1", 2.0), ("P1", 3.0), ("P2", 0.0), ("P3", 1.0), ("P4", 10.0)),
        policy=policy,
    )
    assert quantified.values[0].status == "quantified"
    assert quantified.values[2].status == "below_loq"
    assert quantified.values[2].missing is True
    assert quantified.values[2].intensity == 0.0
    receipt = quantified.receipt
    assert isinstance(receipt, QuantificationReceipt)
    assert receipt.raw_total_signal == 16.0
    assert receipt.normalized_total_signal == 15.0
    assert receipt.below_loq_peptides == 1
    assert receipt.quantifiable_peptides == 2
    assert receipt.limit_of_quantification == 4.0
    assert receipt.normalization_method == "none"
    assert receipt.normalization_target is None
    assert receipt.scale_factor is None
    assert receipt.max_input_observations == 100_000
    assert len(receipt.observation_digest) == 64
    assert receipt.as_dict()["raw_peptide_statuses"] == [
        ["P1", "quantified"],
        ["P2", "zero_signal"],
        ["P3", "below_loq"],
        ["P4", "quantified"],
    ]


def test_median_normalize_rejects_unknown_method_and_zeroes_missing_signal() -> None:
    quantified = quantify_matched_ions_with_receipt(
        "sample",
        (("P1", 1.0), ("P2", 10.0)),
        policy=QuantificationPolicy(limit_of_quantification=2.0),
    )
    assert quantified.values[0].intensity == 0.0
    with pytest.raises(ValueError, match="not supported"):
        median_normalize(quantified.values, method="global_mean")


def test_observation_receipt_is_order_invariant_but_value_bound() -> None:
    first = quantify_matched_ions_with_receipt(
        "sample",
        (("P1", 2.0), ("P2", 4.0), ("P1", 3.0)),
    ).receipt
    reordered = quantify_matched_ions_with_receipt(
        "sample",
        (("P1", 3.0), ("P1", 2.0), ("P2", 4.0)),
    ).receipt
    changed = quantify_matched_ions_with_receipt(
        "sample",
        (("P1", 2.0), ("P2", 4.0), ("P1", 3.1)),
    ).receipt
    assert first.observation_digest == reordered.observation_digest
    assert first.observation_digest != changed.observation_digest


def test_observation_limit_is_enforced_before_materialization() -> None:
    policy = QuantificationPolicy(max_input_observations=2)
    with pytest.raises(ValueError, match="max_input_observations"):
        quantify_matched_ions_with_receipt(
            "sample",
            (("P1", 1.0), ("P2", 2.0), ("P3", 3.0)),
            policy=policy,
        )


def test_observation_limit_stops_lazy_producer_at_first_excess_item() -> None:
    touched = 0

    def observations() -> Iterator[tuple[str, float]]:
        nonlocal touched
        for index in range(10):
            touched += 1
            yield (f"P{index}", 1.0)

    with pytest.raises(ValueError, match="max_input_observations"):
        quantify_matched_ions_with_receipt(
            "sample",
            observations(),
            policy=QuantificationPolicy(max_input_observations=2),
        )

    assert touched == 3


def test_pipeline_binds_non_default_policy_to_configuration_and_replay() -> None:
    policy = QuantificationPolicy(
        normalization_method="none_v1",
        limit_of_quantification=25.0,
    )
    request = ResearchRunRequest(
        "policy-replay",
        _mzml(),
        b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
        quantification_policy=policy,
    )
    result = run_research_protein_inference(request)
    config = dict(result.configuration)
    assert config["quantification_policy"] == policy.as_dict()
    assert result.quantification_receipt is not None
    assert result.quantification_receipt.limit_of_quantification == 25.0
    assert result.quantification_receipt.below_loq_peptides == 0
    assert config["quantification_version"] == result.quantification_receipt.version
    assert config["quantification_receipt_version"] == result.quantification_receipt.version
    assert config["quantification_unit"] == "matched_ion_intensity_arbitrary"
    protein_group_evidence = next(
        record
        for record in result.evidence.records
        if record.evidence_id == "computed:protein-groups"
    )
    assert protein_group_evidence.payload_jsonable["quantification_version"] == (
        result.quantification_receipt.version
    )
    assert protein_group_evidence.payload_jsonable["quantification_unit"] == (
        result.quantification_receipt.measurement_unit
    )
    assert replay_research_protein_inference(request, result).result_digest == result.result_digest
    forged = replace(
        result,
        quantification_receipt=replace(
            result.quantification_receipt,
            limit_of_quantification=26.0,
        ),
    )
    with pytest.raises(ValueError, match="digest"):
        replay_research_protein_inference(request, forged)


def test_quantification_receipt_rejects_invalid_default_omitted_fields() -> None:
    quantified = quantify_matched_ions_with_receipt("sample", ())
    with pytest.raises(ValueError, match="limit_of_quantification"):
        replace(quantified.receipt, limit_of_quantification=-1.0)
    with pytest.raises(ValueError, match="below_loq_peptides"):
        replace(quantified.receipt, below_loq_peptides=-1)
    with pytest.raises(ValueError, match="quantifiable_peptides"):
        replace(quantified.receipt, quantifiable_peptides=-1)


def test_quantification_receipt_accepts_only_a_canonical_projection() -> None:
    receipt = quantify_matched_ions_with_receipt(
        "receipt-canonical",
        (("P2", 4.0), ("P1", 2.0)),
    ).receipt
    assert replace(receipt) == receipt
    assert receipt.raw_total_signal == 6.0
    assert receipt.raw_positive_median == 3.0
    assert receipt.normalized_total_signal == 6.0
    assert receipt.raw_peptide_statuses == (
        ("P1", "quantified"),
        ("P2", "quantified"),
    )


def test_quantification_receipt_rejects_malformed_metadata_and_derived_counts() -> None:
    receipt = quantify_matched_ions_with_receipt(
        "receipt-boundary",
        (("P1", 2.0), ("P2", 4.0)),
    ).receipt
    with pytest.raises(ValueError, match="sample_id"):
        replace(receipt, sample_id=" ")
    with pytest.raises(ValueError, match="version"):
        replace(receipt, version="unversioned")
    with pytest.raises(ValueError, match="measurement_unit"):
        replace(receipt, measurement_unit="matched_ion_intensity_arbitrary")
    with pytest.raises(ValueError, match="input_observations"):
        replace(receipt, input_observations=True)
    with pytest.raises(ValueError, match="positive_signal_fraction"):
        replace(receipt, positive_signal_fraction=1.1)
    with pytest.raises(ValueError, match="max_input_observations"):
        replace(receipt, max_input_observations=0)
    with pytest.raises(ValueError, match="observation_digest"):
        replace(receipt, observation_digest="A" * 64)


def test_quantification_receipt_rejects_malformed_signal_and_status_projections() -> None:
    receipt = quantify_matched_ions_with_receipt(
        "receipt-signals",
        (("P1", 2.0), ("P2", 4.0)),
    ).receipt
    with pytest.raises(ValueError, match=r"ordered|unique"):
        replace(
            receipt,
            raw_peptide_signals=(("P2", 4.0, False), ("P1", 2.0, False)),
        )
    with pytest.raises(ValueError, match="aligned"):
        replace(
            receipt,
            raw_peptide_statuses=(("P1", "forged"), ("P2", "quantified")),
        )
    with pytest.raises(ValueError, match="normalized signal"):
        replace(
            receipt,
            normalized_peptide_signals=(("P1", 9.0, False), ("P2", 4.0, False)),
        )
    with pytest.raises(ValueError, match="raw_positive_median"):
        replace(receipt, raw_positive_median=2.0)


def test_quantification_receipt_rejects_nonzero_loq_policy_mismatch() -> None:
    receipt = quantify_matched_ions_with_receipt(
        "receipt-loq-boundary",
        (("P1", 2.0), ("P2", 4.0)),
        policy=QuantificationPolicy(
            normalization_method="none_v1",
            limit_of_quantification=3.0,
        ),
    ).receipt
    assert receipt.missingness_policy == "zero_or_below_loq_is_missing_no_imputation_v1"
    with pytest.raises(ValueError, match="missingness_policy"):
        replace(receipt, missingness_policy="zero_signal_is_missing_no_imputation")
    with pytest.raises(ValueError, match="normalized_total_signal"):
        replace(receipt, normalized_total_signal=999.0)


def test_quantification_receipt_closes_every_direct_projection_boundary() -> None:
    receipt = quantify_matched_ions_with_receipt(
        "receipt-projection-boundary",
        (("P1", 2.0), ("P2", 4.0)),
    ).receipt
    with pytest.raises(ValueError, match="finite numeric"):
        replace(receipt, raw_total_signal="2")
    with pytest.raises(ValueError, match="finite numeric"):
        replace(receipt, raw_positive_mad=float("nan"))
    with pytest.raises(TypeError, match="raw_peptide_signals"):
        replace(receipt, raw_peptide_signals=[])
    with pytest.raises(ValueError, match="entries"):
        replace(receipt, raw_peptide_signals=(("P1", 2.0), ("P2", 4.0)))
    with pytest.raises(ValueError, match="intensity"):
        replace(receipt, raw_peptide_signals=(("P1", True, False), ("P2", 4.0, False)))
    with pytest.raises(ValueError, match="missingness"):
        replace(receipt, raw_peptide_signals=(("P1", 2.0, 1), ("P2", 4.0, False)))
    with pytest.raises(TypeError, match="raw_peptide_statuses"):
        replace(receipt, raw_peptide_statuses=[])
    with pytest.raises(ValueError, match="cover"):
        replace(receipt, raw_peptide_statuses=(("P1", "quantified"),))
    with pytest.raises(ValueError, match="entries"):
        replace(
            receipt,
            raw_peptide_statuses=(("P1", "quantified", "extra"), ("P2", "quantified")),
        )
    with pytest.raises(ValueError, match="status"):
        replace(receipt, raw_peptide_statuses=(("P1", True), ("P2", "quantified")))
    with pytest.raises(ValueError, match="input_observations"):
        replace(receipt, input_observations=1)
    with pytest.raises(ValueError, match="duplicate_observations"):
        replace(receipt, duplicate_observations=1)
    with pytest.raises(ValueError, match="observed/missing"):
        replace(receipt, observed_peptides=0, missing_peptides=0)
    with pytest.raises(ValueError, match="below-LOQ"):
        replace(receipt, below_loq_peptides=1)
    with pytest.raises(ValueError, match="quantifiable count"):
        replace(receipt, quantifiable_peptides=1)
    with pytest.raises(ValueError, match="signal projections"):
        replace(
            receipt,
            input_observations=2,
            unique_peptides=1,
            duplicate_observations=1,
            observed_peptides=1,
            missing_peptides=0,
            quantifiable_peptides=1,
        )
    with pytest.raises(ValueError, match="normalized signal projection"):
        replace(
            receipt,
            normalized_peptide_signals=(("P1", 2.0, False), ("Q2", 4.0, False)),
        )
    with pytest.raises(ValueError, match="raw peptide statuses"):
        replace(receipt, raw_peptide_statuses=())
    with pytest.raises(ValueError, match="normalized peptide statuses"):
        replace(receipt, normalized_peptide_statuses=())
    with pytest.raises(ValueError, match="not derived"):
        replace(
            receipt,
            normalized_peptide_statuses=(("P1", "zero_signal"), ("P2", "quantified")),
        )
    with pytest.raises(ValueError, match="normalized missingness"):
        replace(
            receipt,
            normalized_peptide_signals=(("P1", 2.0, True), ("P2", 4.0, False)),
        )
    with pytest.raises(ValueError, match="missingness counts"):
        replace(receipt, observed_peptides=1, missing_peptides=1, quantifiable_peptides=1)
    with pytest.raises(ValueError, match="quantifiable count"):
        replace(
            receipt,
            raw_peptide_signals=(("P1", 0.0, True), ("P2", 0.0, False)),
            normalized_peptide_signals=(("P1", 0.0, True), ("P2", 0.0, False)),
            observed_peptides=1,
            missing_peptides=1,
            quantifiable_peptides=1,
            positive_signal_fraction=0.0,
        )
    with pytest.raises(ValueError, match="positive_signal_fraction"):
        replace(receipt, positive_signal_fraction=0.5)
    with pytest.raises(ValueError, match="signal_quality"):
        replace(receipt, signal_quality="single_positive_signal")
    loq_receipt = quantify_matched_ions_with_receipt(
        "receipt-projection-loq",
        (("P1", 2.0), ("P2", 4.0)),
        policy=QuantificationPolicy(normalization_method="none_v1", limit_of_quantification=3.0),
    ).receipt
    with pytest.raises(ValueError, match="below-LOQ count"):
        replace(loq_receipt, below_loq_peptides=0)
    with pytest.raises(ValueError, match="raw_total_signal"):
        replace(receipt, raw_total_signal=999.0)
    with pytest.raises(ValueError, match="normalized_total_signal"):
        replace(receipt, normalized_total_signal=999.0)
    with pytest.raises(ValueError, match="raw_positive_mad"):
        replace(receipt, raw_positive_mad=0.0)
    with pytest.raises(ValueError, match="raw_positive_iqr"):
        replace(receipt, raw_positive_iqr=0.0)
    with pytest.raises(ValueError, match="raw_robust_cv"):
        replace(receipt, raw_robust_cv=0.0)
    with pytest.raises(ValueError, match="raw peptide status"):
        replace(
            receipt,
            raw_peptide_statuses=(("P1", "zero_signal"), ("P2", "quantified")),
            normalized_peptide_statuses=(("P1", "zero_signal"), ("P2", "quantified")),
        )
    with pytest.raises(ValueError, match="no-normalization"):
        replace(loq_receipt, normalization_target=1.0)
    empty_receipt = quantify_matched_ions_with_receipt("receipt-empty", ()).receipt
    with pytest.raises(ValueError, match="empty normalization"):
        replace(empty_receipt, normalization_target=1.0)
    with pytest.raises(ValueError, match="normalization scale"):
        replace(receipt, normalization_target=2.0)
