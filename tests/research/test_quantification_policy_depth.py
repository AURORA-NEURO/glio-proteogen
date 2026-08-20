"""Adversarial research-only quantification policy coverage."""

from __future__ import annotations

from dataclasses import replace

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
    "value",
    [
        PeptideQuant("sample", "P1", -1.0),
        PeptideQuant("sample", "P1", float("nan")),
        PeptideQuant("sample", "P1", intensity=True),  # type: ignore[arg-type]
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
