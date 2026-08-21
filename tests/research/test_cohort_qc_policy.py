"""Deep tests for explicit cohort QC gates and safe evidence abstention."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import (
    build_cohort_no_match_request,
    build_cohort_supported_request,
    build_scenario_request,
    scenarios,
)

from glio_proteogen.research import (
    CohortQcPolicy,
    ResearchCohortRequest,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)


def _sample(scenario_id: str, sample_id: str, replicate: str) -> ResearchCohortSample:
    if scenario_id == "target_supported":
        return ResearchCohortSample(
            sample_id=sample_id,
            request=build_cohort_supported_request(sample_id),
            cohort_label="qc-cohort",
            replicate_label=replicate,
        )
    if scenario_id == "no_match":
        return ResearchCohortSample(
            sample_id=sample_id,
            request=build_cohort_no_match_request(sample_id),
            cohort_label="qc-cohort",
            replicate_label=replicate,
        )
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


def test_missingness_gate_preserves_none_identity_projection() -> None:
    request = ResearchCohortRequest(
        (_sample("target_supported", "present", "r1"), _sample("no_match", "absent", "r2")),
        normalization_policy="none",
        qc_policy=CohortQcPolicy(max_missingness_rate=0.0),
    )
    result = run_research_cohort(request)
    assert result.raw_matrix == ((("P1",), (None, 20.0)),)
    assert result.normalized_matrix == result.raw_matrix
    assert result.label_qc[0].status == "abstained_missingness"
    assert result.label_qc[0].normalization_status == "not_applied"
    assert result.label_group_evidence[0].status == "abstained_missingness"
    assert {item.status for item in result.sample_scales} == {"not_applied"}
    assert {item.scale_factor for item in result.sample_scales} == {1.0}
    assert replay_research_cohort(request, result) == result
    with pytest.raises(ValueError, match="digest"):
        replay_research_cohort(
            request,
            replace(result, normalized_matrix=((("P1",), (None, None)),)),
        )


def test_observed_group_gate_and_policy_replay_are_explicit() -> None:
    samples = (_sample("target_supported", "present", "r1"), _sample("no_match", "absent", "r2"))
    policy = CohortQcPolicy(min_observed_groups=2)
    result = run_research_cohort(ResearchCohortRequest(samples, qc_policy=policy))
    assert result.label_qc[0].status == "abstained_insufficient_observed_groups"
    altered = ResearchCohortRequest(samples, qc_policy=CohortQcPolicy(min_observed_groups=0))
    with pytest.raises(ValueError, match="replay"):
        replay_research_cohort(altered, result)
