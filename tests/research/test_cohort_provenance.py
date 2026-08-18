"""Adversarial tests for cohort source identity and replicate independence."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import build_scenario_request, scenarios

from glio_proteogen.research import (
    CohortSourceBinding,
    CohortSourceManifest,
    ResearchCohortRequest,
    ResearchCohortSample,
    run_research_cohort,
)


def _sample(sample_id: str, replicate: str) -> ResearchCohortSample:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    request = replace(build_scenario_request(target), sample_id=sample_id)
    return ResearchCohortSample(sample_id, request, "fixture", replicate)


def _manifest(
    samples: tuple[ResearchCohortSample, ...], kind: str
) -> CohortSourceManifest:
    return CohortSourceManifest.from_requests(
        tuple(sample.request for sample in samples),
        replicate_kinds={sample.sample_id: kind for sample in samples},
    )


def test_biological_replicates_cannot_reuse_identical_source_bytes() -> None:
    samples = (_sample("a", "r1"), _sample("b", "r2"))
    with pytest.raises(ValueError, match="biological replicates"):
        run_research_cohort(
            ResearchCohortRequest(samples, source_manifest=_manifest(samples, "biological"))
        )


def test_technical_duplicate_is_visible_but_not_independent_support() -> None:
    samples = (_sample("a", "r1"), _sample("b", "r2"))
    result = run_research_cohort(
        ResearchCohortRequest(
            samples,
            normalization_policy="within_label_median_v1",
            source_manifest=_manifest(samples, "technical"),
        )
    )
    assert result.raw_matrix == ((('P1',), (20.0, 20.0)),)
    assert all(value is None for _, values in result.normalized_matrix for value in values)
    assert result.label_qc[0].independent_replicates == 0
    assert result.label_qc[0].technical_replicates == 2
    assert result.label_qc[0].duplicate_sources == 1
    assert result.label_qc[0].status == "abstained_insufficient_replicates"


def test_technical_duplicate_of_one_biological_run_is_allowed_but_not_support() -> None:
    samples = (_sample("a", "r1"), _sample("b", "r2"))
    manifest = CohortSourceManifest.from_requests(
        tuple(sample.request for sample in samples),
        replicate_kinds={"a": "biological", "b": "technical"},
    )
    result = run_research_cohort(
        ResearchCohortRequest(
            samples,
            normalization_policy="within_label_median_v1",
            source_manifest=manifest,
        )
    )
    assert result.label_qc[0].independent_replicates == 1
    assert result.label_qc[0].technical_replicates == 1
    assert result.label_qc[0].status == "abstained_insufficient_replicates"


def test_unknown_independence_abstains_only_when_normalization_is_requested() -> None:
    samples = (_sample("a", "r1"), _sample("b", "r2"))
    result = run_research_cohort(
        ResearchCohortRequest(
            samples,
            normalization_policy="within_label_median_v1",
        )
    )
    assert result.label_qc[0].status == "abstained_unknown_independence"
    assert all(value is None for _, values in result.normalized_matrix for value in values)


def test_source_swap_is_rejected_by_digest_binding() -> None:
    first = _sample("a", "r1")
    second = replace(
        _sample("b", "r2"),
        request=replace(_sample("b", "r2").request, mzml_source=b"<!--different-->" + bytes(first.request.mzml_source)),
    )
    normal = _manifest((first, second), "technical")
    swapped = CohortSourceManifest(
        (
            replace(normal.for_sample("a"), sample_id="b"),
            replace(normal.for_sample("b"), sample_id="a"),
        )
    )
    with pytest.raises(ValueError, match="digest"):
        run_research_cohort(ResearchCohortRequest((first, second), source_manifest=swapped))


def test_wrong_pdc_study_binding_is_rejected() -> None:
    from evals.research_proteomics.cohort import _pdc_sample

    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    sample = _pdc_sample(target, "pdc-a", "r1")
    second = _pdc_sample(target, "pdc-b", "r2")
    manifest = CohortSourceManifest.from_requests(
        (sample.request, second.request), replicate_kinds={"pdc-a": "technical", "pdc-b": "technical"}
    )
    altered = replace(manifest.for_sample("pdc-a"), pdc_study_id="PDC999999")
    bad = CohortSourceManifest((altered, manifest.for_sample("pdc-b")))
    with pytest.raises(ValueError, match="PDC study"):
        run_research_cohort(
            ResearchCohortRequest(
                (sample, second),
                provenance_policy="external_same_study",
                source_manifest=bad,
            )
        )


def test_manifest_digest_is_permutation_stable_and_tamper_visible() -> None:
    samples = (_sample("a", "r1"), _sample("b", "r2"))
    manifest = _manifest(samples, "technical")
    assert manifest.digest == CohortSourceManifest(tuple(reversed(manifest.bindings))).digest
    changed = replace(manifest.for_sample("a"), declared_aliquot_id="caller-aliquot-a")
    assert CohortSourceManifest((changed, manifest.for_sample("b"))).digest != manifest.digest


def test_binding_rejects_inconsistent_pdc_fields() -> None:
    with pytest.raises(ValueError, match="PDC bindings"):
        CohortSourceBinding(
            sample_id="s",
            source_kind="pdc",
            source_id="pdc:s",
            source_sha256="a" * 64,
            source_size=1,
            pdc_study_id="PDC000001",
        )


def test_pdc_binding_can_join_a_matching_study_metadata_snapshot() -> None:
    from evals.research_proteomics.cohort import _pdc_sample
    from glio_proteogen.research.public_proteomics.pdc import PDCStudyMetadata, PDCSnapshot
    from glio_proteogen.research.public_proteomics.provenance import SourceReference

    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    sample = _pdc_sample(target, "pdc-a", "r1")
    receipt = sample.request.external_pdc_receipt
    assert receipt is not None
    metadata = PDCStudyMetadata.from_dict(
        {
            "study_id": "PDC000204",
            "pdc_study_id": "PDC000204",
            "study_submitter_id": "submitter",
            "project_id": "project",
            "study_name": "fixture",
            "study_description": "fixture metadata",
            "program_name": "program",
            "project_name": "project",
            "disease_type": "not asserted",
            "primary_site": "not asserted",
            "analytical_fraction": "proteome",
            "experiment_type": "discovery",
            "cases_count": 1,
            "aliquots_count": 1,
        }
    )
    metadata_source = SourceReference(
        source_id="pdc:PDC000204:metadata",
        locator="https://pdc.cancer.gov/graphql",
        media_type="application/json",
        sha256="sha256:" + "a" * 64,
        byte_length=1,
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="fixture metadata",
    )
    snapshot = PDCSnapshot(
        metadata=metadata,
        endpoint="https://pdc.cancer.gov/graphql",
        query="fixture-query",
        query_sha256="a" * 64,
        response_sha256="a" * 64,
        response_bytes=1,
        source_reference=metadata_source,
    )
    binding = CohortSourceBinding.from_pdc_receipt(
        sample.request, receipt, metadata_snapshot=snapshot, replicate_kind="technical"
    )
    assert binding.pdc_study_id == "PDC000204"
    assert binding.metadata_snapshot_digest == snapshot.digest.removeprefix("sha256:")
