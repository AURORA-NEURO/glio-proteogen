"""Deep tests for the research-only cohort matrix and QC layer."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from evals.research_proteomics.cohort import _pdc_sample
from evals.research_proteomics.run import (
    build_cohort_no_match_request,
    build_cohort_supported_request,
    build_scenario_request,
    scenarios,
)

from glio_proteogen.research import (
    CohortLabelContrast,
    CohortSourceManifest,
    ResearchCohortRequest,
    ResearchCohortSample,
    aggregate_cohort_evidence,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.cohort import _compatible_configuration, _digest


def _sample(scenario_id: str, sample_id: str, replicate: str) -> ResearchCohortSample:
    if scenario_id == "target_supported":
        return ResearchCohortSample(
            sample_id=sample_id,
            request=build_cohort_supported_request(sample_id),
            cohort_label="fixture-cohort",
            replicate_label=replicate,
        )
    if scenario_id == "no_match":
        return ResearchCohortSample(
            sample_id=sample_id,
            request=build_cohort_no_match_request(sample_id),
            cohort_label="fixture-cohort",
            replicate_label=replicate,
        )
    scenario = next(item for item in scenarios() if item.scenario_id == scenario_id)
    return ResearchCohortSample(
        sample_id=sample_id,
        request=replace(build_scenario_request(scenario), sample_id=sample_id),
        cohort_label="fixture-cohort",
        replicate_label=replicate,
    )


def _valid_contrast() -> CohortLabelContrast:
    return CohortLabelContrast(
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


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"cohort_label_a": "control"}, "lexical order"),
        ({"group_accessions": ()}, "group accession"),
        ({"label_a_observed_replicates": -1}, "label_a_observed"),
        ({"label_b_observed_replicates": -1}, "label_b_observed"),
        ({"label_a_missingness_rate": 2.0}, "finite fraction"),
        ({"status": "accepted"}, "status"),
        ({"label_a_median": -1.0}, "median fields"),
        ({"log2_median_ratio": float("inf")}, "derived fields"),
        ({"median_difference": 1.0}, "derived from"),
        ({"label_a_median": None}, "two positive"),
        (
            {"status": "abstained_missing_or_nonpositive", "median_difference": -10.0},
            "abstained contrast",
        ),
    ],
)
def test_label_contrast_rejects_malformed_or_overstated_receipts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_valid_contrast(), **changes)


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


def test_cohort_evidence_bundle_is_domain_split_and_recomputable() -> None:
    request = ResearchCohortRequest(
        (_sample("target_supported", "a", "r1"), _sample("no_match", "b", "r2"))
    )
    result = run_research_cohort(request)
    assert result.evidence_bundle is not None
    bundle = aggregate_cohort_evidence(result)
    assert bundle.digest == result.evidence_bundle.digest
    assert bundle.quality_summary is not None
    assert bundle.quality_summary.scored_records == 4
    assert bundle.quality_summary.independent_sources == 2
    assert bundle.quality_summary.weighted_score is not None
    assert tuple(record.evidence_id for record in bundle.records) == (
        "cohort.contrast.v1",
        "cohort.matrix.v1",
        "cohort.provenance.v1",
        "cohort.qc.v1",
    )
    projection = bundle.as_dict()
    records = projection["records"]
    assert isinstance(records, list)
    assert {record["kind"] for record in records if isinstance(record, dict)} == {
        "computed_matrix",
        "descriptive_qc",
        "source_provenance",
        "descriptive_label_contrast",
    }
    assert all(
        isinstance(record, dict)
        and isinstance(record.get("payload"), dict)
        and record.get("digest")
        for record in records
    )


def test_cohort_label_contrast_is_descriptive_and_replay_bound() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (
                replace(_sample("target_supported", "case", "r1"), cohort_label="case"),
                replace(_sample("target_supported", "control", "r1"), cohort_label="control"),
            )
        )
    )
    assert len(result.label_contrasts) == 1
    contrast = result.label_contrasts[0]
    assert contrast.cohort_label_a == "case"
    assert contrast.cohort_label_b == "control"
    assert contrast.status == "descriptive"
    assert contrast.median_difference == 0.0
    assert contrast.median_ratio == 1.0
    assert contrast.log2_median_ratio == 0.0
    assert dict(result.configuration)["cohort_contrast_version"] == (
        "caller-label-median-contrast-v1"
    )
    tampered = replace(
        result,
        label_contrasts=(replace(contrast, median_ratio=2.0),),
    )
    with pytest.raises(ValueError, match="not reproducible"):
        aggregate_cohort_evidence(tampered)


def test_cohort_label_contrast_abstains_without_two_positive_medians() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (
                replace(_sample("target_supported", "present", "r1"), cohort_label="case"),
                replace(_sample("no_match", "absent", "r1"), cohort_label="control"),
            )
        )
    )
    assert len(result.label_contrasts) == 1
    contrast = result.label_contrasts[0]
    assert contrast.status == "abstained_missing_or_nonpositive"
    assert contrast.median_difference is None
    assert contrast.median_ratio is None
    assert contrast.log2_median_ratio is None


def test_cohort_evidence_bundle_rejects_tampered_outer_or_inner_receipt() -> None:
    request = ResearchCohortRequest(
        (_sample("target_supported", "a", "r1"), _sample("target_supported", "b", "r2"))
    )
    result = run_research_cohort(request)
    assert result.evidence_bundle is not None
    tampered_outer = replace(
        result,
        evidence_bundle=replace(result.evidence_bundle, digest="0" * 64),
    )
    with pytest.raises(ValueError, match="not reproducible"):
        aggregate_cohort_evidence(tampered_outer)
    tampered_record = replace(
        result.evidence_bundle.records[0],
        digest="f" * 64,
    )
    tampered_inner = replace(
        result,
        evidence_bundle=replace(
            result.evidence_bundle,
            records=(tampered_record, *result.evidence_bundle.records[1:]),
        ),
    )
    with pytest.raises(ValueError, match="not reproducible"):
        aggregate_cohort_evidence(tampered_inner)


def test_cohort_evidence_bundle_requires_complete_result_shape() -> None:
    request = ResearchCohortRequest(
        (_sample("target_supported", "a", "r1"), _sample("target_supported", "b", "r2"))
    )
    result = run_research_cohort(request)
    with pytest.raises(TypeError, match="ResearchCohortResult"):
        aggregate_cohort_evidence(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source manifest"):
        aggregate_cohort_evidence(replace(result, source_manifest=None))
    with pytest.raises(ValueError, match="evidence bundle"):
        aggregate_cohort_evidence(replace(result, evidence_bundle=None))


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
    with pytest.raises(TypeError, match="CohortSourceManifest"):
        ResearchCohortRequest(
            (valid, _sample("target_supported", "second", "r2")),
            source_manifest=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="sample count"):
        ResearchCohortRequest((valid,))
    too_many = tuple(
        _sample("target_supported", f"sample-{index}", f"r{index}") for index in range(33)
    )
    with pytest.raises(ValueError, match="sample count"):
        ResearchCohortRequest(too_many)
    with pytest.raises(ValueError, match="no run"):
        _compatible_configuration(())


def test_cohort_provenance_policy_rejects_mixed_and_binds_external_catalog() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    local = _sample("target_supported", "local", "r1")
    external = _pdc_sample(target, "external", "r2")
    with pytest.raises(ValueError, match="mix local"):
        run_research_cohort(ResearchCohortRequest((local, external)))
    result = run_research_cohort(
        ResearchCohortRequest(
            (external, _pdc_sample(target, "external-2", "r3")),
            provenance_policy="external_same_study",
        )
    )
    configuration = dict(result.configuration)
    assert configuration["cohort_provenance_policy"] == "external_same_study"
    provenance = configuration["sample_source_provenance"]
    assert isinstance(provenance, list)
    assert all(isinstance(item, dict) and item["external_pdc_receipt"] for item in provenance)


def test_cohort_provenance_policy_rejects_different_catalog_response() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    first = _pdc_sample(target, "pdc-a", "r1")
    second = _pdc_sample(target, "pdc-b", "r2")
    assert first.request.external_pdc_receipt is not None
    assert second.request.external_pdc_receipt is not None
    second_receipt = replace(
        second.request.external_pdc_receipt,
        snapshot=replace(second.request.external_pdc_receipt.snapshot, response_sha256="e" * 64),
    )
    second_request = replace(
        second.request,
        external_pdc_receipt=second_receipt,
        external_pdc_response_sha256="e" * 64,
    )
    altered = replace(second, request=second_request)
    with pytest.raises(ValueError, match="one study and one catalog response"):
        run_research_cohort(
            ResearchCohortRequest((first, altered), provenance_policy="external_same_study")
        )


def test_cohort_provenance_rejects_mixed_metadata_snapshot_digests() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    first = _pdc_sample(target, "pdc-a", "r1")
    second = _pdc_sample(target, "pdc-b", "r2")
    manifest = CohortSourceManifest.from_requests(
        (first.request, second.request),
        replicate_kinds={"pdc-a": "biological", "pdc-b": "biological"},
    )
    altered = replace(
        manifest.bindings[1],
        metadata_snapshot_digest="f" * 64,
    )
    mixed_manifest = CohortSourceManifest((manifest.bindings[0], altered))
    with pytest.raises(ValueError, match="metadata snapshot"):
        run_research_cohort(
            ResearchCohortRequest(
                (first, second),
                provenance_policy="external_same_study",
                source_manifest=mixed_manifest,
            )
        )


def test_cohort_provenance_policy_closes_local_only_and_unattested_external_paths() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    local_a = _sample("target_supported", "local-a", "r1")
    local_b = _sample("target_supported", "local-b", "r2")
    with pytest.raises(ValueError, match="provenance_policy"):
        ResearchCohortRequest((local_a, local_b), provenance_policy="unknown")
    with pytest.raises(ValueError, match="external_same_study"):
        run_research_cohort(
            ResearchCohortRequest((local_a, local_b), provenance_policy="external_same_study")
        )
    external = _pdc_sample(target, "external", "r1")
    unattested_request = replace(external.request, external_pdc_receipt=None)
    unattested = replace(external, request=unattested_request)
    unattested_two = replace(
        unattested,
        sample_id="external-2",
        request=replace(unattested.request, sample_id="external-2"),
        replicate_label="r2",
    )
    with pytest.raises(ValueError, match="local_only"):
        run_research_cohort(
            ResearchCohortRequest((unattested, unattested_two), provenance_policy="local_only")
        )
    with pytest.raises(ValueError, match="catalog receipts"):
        run_research_cohort(
            ResearchCohortRequest(
                (unattested, unattested_two),
                provenance_policy="homogeneous",
            )
        )
    mixed = run_research_cohort(
        ResearchCohortRequest((local_a, external), provenance_policy="mixed_declared")
    )
    assert dict(mixed.configuration)["cohort_provenance_policy"] == "mixed_declared"
