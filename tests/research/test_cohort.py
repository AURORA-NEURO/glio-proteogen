"""Deep tests for the research-only cohort matrix and QC layer."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import build_scenario_request, scenarios

from glio_proteogen.research import (
    ResearchCohortRequest,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.cohort import _compatible_configuration, _digest


def _sample(scenario_id: str, sample_id: str, replicate: str) -> ResearchCohortSample:
    scenario = next(item for item in scenarios() if item.scenario_id == scenario_id)
    return ResearchCohortSample(
        sample_id=sample_id,
        request=replace(build_scenario_request(scenario), sample_id=sample_id),
        cohort_label="fixture-cohort",
        replicate_label=replicate,
    )


def test_cohort_builds_deterministic_matrix_and_replicate_qc() -> None:
    request = ResearchCohortRequest(
        (
            _sample("target_supported", "sample-b", "r2"),
            _sample("target_supported", "sample-a", "r1"),
        )
    )
    result = run_research_cohort(request)
    assert result.sample_ids == ("sample-a", "sample-b")
    assert result.matrix == ((("P1",), (20.0, 20.0)),)
    assert result.group_qc[0].observed_samples == 2
    assert result.group_qc[0].missingness_rate == 0.0
    assert result.group_qc[0].median_intensity == 20.0
    assert result.group_qc[0].mad_intensity == 0.0
    assert tuple(item.sample_id for item in result.sample_qc) == ("sample-a", "sample-b")


def test_cohort_represents_absent_groups_as_null_missingness() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (
                _sample("target_supported", "present", "r1"),
                _sample("no_match", "absent", "r2"),
            )
        )
    )
    assert result.matrix == ((("P1",), (None, 20.0)),)
    assert result.group_qc[0].observed_samples == 1
    assert result.group_qc[0].missing_samples == 1
    assert result.group_qc[0].missingness_rate == 0.5
    assert result.sample_qc[0].missing_groups == 1
    assert result.sample_qc[0].missingness_rate == 1.0


def test_cohort_rejects_duplicate_ids_labels_and_incompatible_search_space() -> None:
    with pytest.raises(ValueError, match="sample IDs"):
        ResearchCohortRequest(
            (_sample("target_supported", "same", "r1"), _sample("target_supported", "same", "r2"))
        )
    with pytest.raises(ValueError, match="replicate labels"):
        ResearchCohortRequest(
            (_sample("target_supported", "a", "r1"), _sample("target_supported", "b", "r1"))
        )
    with pytest.raises(ValueError, match="FASTA and search"):
        run_research_cohort(
            ResearchCohortRequest(
                (
                    _sample("target_supported", "target", "r1"),
                    _sample("decoy_rejected", "decoy", "r2"),
                )
            )
        )


def test_cohort_order_permutation_and_replay_are_digest_bound() -> None:
    first_request = ResearchCohortRequest(
        (_sample("target_supported", "a", "r1"), _sample("no_match", "b", "r2"))
    )
    reversed_request = ResearchCohortRequest(tuple(reversed(first_request.samples)))
    first = run_research_cohort(first_request)
    second = run_research_cohort(reversed_request)
    assert first.result_digest == second.result_digest
    assert replay_research_cohort(first_request, first).result_digest == first.result_digest
    tampered = replace(first, result_digest="0" * 64)
    with pytest.raises(ValueError, match="digest"):
        replay_research_cohort(first_request, tampered)
    altered = replace(first, matrix=())
    altered_payload = altered.as_dict()
    altered_payload.pop("result_digest")
    altered = replace(altered, result_digest=_digest(altered_payload))
    with pytest.raises(ValueError, match="replay"):
        replay_research_cohort(first_request, altered)


def test_cohort_boundary_types_and_bounded_cardinality() -> None:
    valid = _sample("target_supported", "valid", "r1")
    with pytest.raises(ValueError, match="opaque"):
        ResearchCohortSample("bad id", valid.request, "fixture-cohort", "r2")
    with pytest.raises(ValueError, match="match"):
        ResearchCohortSample("other", valid.request, "fixture-cohort", "r2")
    with pytest.raises(TypeError, match="ResearchRunRequest"):
        ResearchCohortSample("valid", object(), "fixture-cohort", "r2")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple"):
        ResearchCohortRequest([valid, _sample("target_supported", "second", "r2")])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sample count"):
        ResearchCohortRequest((valid,))
    too_many = tuple(
        _sample("target_supported", f"sample-{index}", f"r{index}") for index in range(33)
    )
    with pytest.raises(ValueError, match="sample count"):
        ResearchCohortRequest(too_many)
    with pytest.raises(ValueError, match="no run"):
        _compatible_configuration(())
