"""Adversarial tests for label-aware research cohort normalization."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import build_scenario_request, scenarios

import glio_proteogen.research.cohort as cohort_module
from glio_proteogen.research import (
    ProteinGroup,
    ProteinGroupQuant,
    ResearchCohortRequest,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.pipeline import run_research_protein_inference


def _sample(sample_id: str, label: str, replicate: str) -> ResearchCohortSample:
    scenario = next(item for item in scenarios() if item.scenario_id == "target_supported")
    request = replace(build_scenario_request(scenario), sample_id=sample_id)
    return ResearchCohortSample(sample_id, request, label, replicate)


def _quant(group: tuple[str, ...], intensity: float) -> ProteinGroupQuant:
    return ProteinGroupQuant(
        group_accessions=group,
        unique_peptides=("PEPTIDE",),
        shared_peptides=(),
        unique_signal=intensity,
        shared_signal=0.0,
        total_signal=intensity,
        primary_intensity=intensity,
        status="quantified",
        supporting_psms=1,
    )


def test_within_label_normalization_preserves_raw_and_aligns_replicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = run_research_protein_inference(_sample("template", "x", "r1").request)
    values = {
        "case-a": (10.0, 30.0),
        "case-b": (20.0, 60.0),
        "control-a": (100.0, 300.0),
        "control-b": (200.0, 600.0),
    }
    results = {
        sample_id: replace(
            base,
            sample_id=sample_id,
            protein_group_quantifications=(
                _quant(("P1",), pair[0]),
                _quant(("P2",), pair[1]),
            ),
            protein_groups=(
                ProteinGroup(("P1",), ("PEPTIDE",), ()),
                ProteinGroup(("P2",), ("PEPTIDE2",), ()),
            ),
        )
        for sample_id, pair in values.items()
    }
    monkeypatch.setattr(
        cohort_module, "run_research_protein_inference", lambda request: results[request.sample_id]
    )
    request = ResearchCohortRequest(
        (
            _sample("control-b", "control", "r2"),
            _sample("case-b", "case", "r2"),
            _sample("control-a", "control", "r1"),
            _sample("case-a", "case", "r1"),
        ),
        normalization_policy="within_label_median_v1",
    )
    result = run_research_cohort(request)
    assert result.sample_ids == ("case-a", "case-b", "control-a", "control-b")
    assert result.raw_matrix[0][1] == (10.0, 20.0, 100.0, 200.0)
    assert result.normalized_matrix[0][1] == (15.0, 15.0, 150.0, 150.0)
    assert result.normalized_matrix[1][1] == (45.0, 45.0, 450.0, 450.0)
    assert {item.cohort_label for item in result.label_qc} == {"case", "control"}
    assert all(item.status == "normalized" for item in result.sample_scales)
    assert all(item.status == "descriptive" for item in result.label_group_evidence), (
        result.label_group_evidence
    )
    assert dict(result.configuration)["cohort_normalization_policy"] == ("within_label_median_v1")


def test_insufficient_label_overlap_abstains_without_imputation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = run_research_protein_inference(_sample("template", "x", "r1").request)
    results = {
        sample_id: replace(
            base,
            sample_id=sample_id,
            protein_group_quantifications=(
                _quant((group,), 10.0 if sample_id.endswith("a") else 20.0),
            ),
            protein_groups=(ProteinGroup((group,), ("PEPTIDE",), ()),),
        )
        for sample_id, group in (("a", "P1"), ("b", "P2"))
    }
    monkeypatch.setattr(
        cohort_module,
        "run_research_protein_inference",
        lambda request: results[request.sample_id],
    )
    result = run_research_cohort(
        ResearchCohortRequest(
            (_sample("a", "case", "r1"), _sample("b", "case", "r2")),
            normalization_policy="within_label_median_v1",
        )
    )
    assert all(item.status == "abstained_insufficient_overlap" for item in result.sample_scales)
    assert result.raw_matrix[0][1] == (10.0, None)
    assert all(value is None for _, values in result.normalized_matrix for value in values)
    assert result.label_qc[0].status == "abstained_insufficient_overlap"


def test_single_replicate_labels_abstain_before_scaling() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (_sample("a", "case", "r1"), _sample("b", "control", "r1")),
            normalization_policy="within_label_median_v1",
        )
    )
    assert {item.status for item in result.sample_scales} == {"abstained_insufficient_replicates"}
    assert all(value is None for _, values in result.normalized_matrix for value in values)
    assert all(
        item.status == "abstained_insufficient_replicates" for item in result.label_group_evidence
    )


def test_normalization_policy_is_replay_visible_and_permutation_stable() -> None:
    samples = (_sample("a", "case", "r1"), _sample("b", "case", "r2"))
    with pytest.raises(ValueError, match="normalization_policy"):
        ResearchCohortRequest(samples, normalization_policy="mean_impute")
    first = run_research_cohort(
        ResearchCohortRequest(samples, normalization_policy="within_label_median_v1")
    )
    second = run_research_cohort(
        ResearchCohortRequest(
            tuple(reversed(samples)), normalization_policy="within_label_median_v1"
        )
    )
    assert first.result_digest == second.result_digest
    assert dict(first.configuration)["cohort_normalization_version"] == "within-label-median-v1"
    with pytest.raises(ValueError, match="replay"):
        replay_research_cohort(ResearchCohortRequest(samples, normalization_policy="none"), first)
