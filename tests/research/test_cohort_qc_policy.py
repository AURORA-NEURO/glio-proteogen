"""Deep tests for explicit cohort QC gates and safe evidence abstention."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import build_scenario_request, scenarios

from glio_proteogen.research import (
    CohortQcPolicy,
    ResearchCohortRequest,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)


def _sample(scenario_id: str, sample_id: str, replicate: str) -> ResearchCohortSample:
    scenario = next(item for item in scenarios() if item.scenario_id == scenario_id)
    request = replace(build_scenario_request(scenario), sample_id=sample_id)
    return ResearchCohortSample(sample_id, request, "qc-cohort", replicate)


def test_qc_policy_rejects_unbounded_or_boolean_thresholds() -> None:
    with pytest.raises(ValueError, match="min_replicates"):
        CohortQcPolicy(min_replicates=True)
    with pytest.raises(ValueError, match="max_missingness"):
        CohortQcPolicy(max_missingness_rate=float("nan"))
    with pytest.raises(ValueError, match="observed_groups"):
        CohortQcPolicy(min_observed_groups=-1)
    with pytest.raises(TypeError, match="qc_policy"):
        ResearchCohortRequest(
            (_sample("target_supported", "a", "r1"), _sample("target_supported", "b", "r2")),
            qc_policy=object(),  # type: ignore[arg-type]
        )


def test_missingness_gate_abstains_and_keeps_raw_matrix() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (_sample("target_supported", "present", "r1"), _sample("no_match", "absent", "r2")),
            qc_policy=CohortQcPolicy(max_missingness_rate=0.0),
        )
    )
    assert result.raw_matrix == ((("P1",), (None, 20.0)),)
    assert result.normalized_matrix == ((("P1",), (None, None)),)
    assert result.label_qc[0].status == "abstained_missingness"
    assert result.label_qc[0].normalization_status == "not_applied"
    assert result.label_group_evidence[0].status == "abstained_missingness"


def test_observed_group_gate_and_policy_replay_are_explicit() -> None:
    samples = (_sample("target_supported", "present", "r1"), _sample("no_match", "absent", "r2"))
    policy = CohortQcPolicy(min_observed_groups=2)
    result = run_research_cohort(ResearchCohortRequest(samples, qc_policy=policy))
    assert result.label_qc[0].status == "abstained_insufficient_observed_groups"
    altered = ResearchCohortRequest(samples, qc_policy=CohortQcPolicy(min_observed_groups=0))
    with pytest.raises(ValueError, match="replay"):
        replay_research_cohort(altered, result)
