"""Adversarial tests for cohort source identity and replicate independence."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest
from evals.research_proteomics.cohort import _pdc_sample
from evals.research_proteomics.run import build_scenario_request, scenarios

from glio_proteogen.research import (
    CohortSourceBinding,
    CohortSourceManifest,
    ResearchCohortRequest,
    ResearchCohortSample,
    run_research_cohort,
)
from glio_proteogen.research.public_proteomics.pdc import PDCSnapshot, PDCStudyMetadata
from glio_proteogen.research.public_proteomics.provenance import SourceReference


def _sample(sample_id: str, replicate: str) -> ResearchCohortSample:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    request = replace(build_scenario_request(target), sample_id=sample_id)
    return ResearchCohortSample(sample_id, request, "fixture", replicate)


def _manifest(samples: tuple[ResearchCohortSample, ...], kind: str) -> CohortSourceManifest:
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
    assert result.raw_matrix == ((("P1",), (20.0, 20.0)),)
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
        request=replace(
            _sample("b", "r2").request,
            mzml_source=b"<!--different-->" + cast("bytes", first.request.mzml_source),
        ),
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
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    sample = _pdc_sample(target, "pdc-a", "r1")
    second = _pdc_sample(target, "pdc-b", "r2")
    manifest = CohortSourceManifest.from_requests(
        (sample.request, second.request),
        replicate_kinds={"pdc-a": "technical", "pdc-b": "technical"},
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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sample_id", "", "opaque"),
        ("source_id", "source id", "opaque"),
        ("source_kind", "ftp", "source_kind"),
        ("replicate_kind", "case", "replicate_kind"),
        ("source_sha256", "A" * 64, "lowercase"),
        ("source_size", 0, "source_size"),
    ],
)
def test_binding_schema_rejects_unbounded_or_untyped_identity(
    field: str, value: object, message: str
) -> None:
    values: dict[str, object] = {
        "sample_id": "sample",
        "source_kind": "local",
        "source_id": "local:sample",
        "source_sha256": "a" * 64,
        "source_size": 10,
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        CohortSourceBinding(**values)  # type: ignore[arg-type]


def test_binding_schema_rejects_invalid_optional_digests_and_pdc_local_mix() -> None:
    base = {
        "sample_id": "sample",
        "source_kind": "local",
        "source_id": "local:sample",
        "source_sha256": "a" * 64,
        "source_size": 10,
    }
    with pytest.raises(ValueError, match="catalog_response_sha256"):
        CohortSourceBinding(**base, catalog_response_sha256="not-a-digest")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="local bindings"):
        CohortSourceBinding(**base, pdc_study_id="PDC000204")  # type: ignore[arg-type]


def test_manifest_shape_lookup_and_counts_are_closed() -> None:
    sample = _sample("sample", "r1")
    binding = CohortSourceBinding.from_request(sample.request)
    with pytest.raises(TypeError, match="tuple"):
        CohortSourceManifest([binding, binding])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="outside"):
        CohortSourceManifest((binding,))
    with pytest.raises(TypeError, match="CohortSourceBinding"):
        CohortSourceManifest((binding, object()))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unique sample"):
        CohortSourceManifest((binding, binding))
    second = replace(binding, sample_id="second", source_id="local:second")
    manifest = CohortSourceManifest((binding, second))
    with pytest.raises(ValueError, match="no unique"):
        manifest.for_sample("missing")
    counts = manifest.source_identity_counts(("sample", "second"))
    assert counts == {
        "rows": 2,
        "unique_sources": 1,
        "duplicate_sources": 1,
        "biological": 0,
        "technical": 0,
        "unknown": 2,
    }


def test_manifest_validation_rejects_order_count_digest_and_size_mismatch() -> None:
    first = _sample("first", "r1")
    second = _sample("second", "r2")
    manifest = CohortSourceManifest.from_requests((first.request, second.request))
    observed = (
        manifest.for_sample("first").source_sha256,
        manifest.for_sample("second").source_sha256,
    )
    with pytest.raises(ValueError, match="sample order"):
        manifest.validate_against_samples(
            ("second", "first"), (first.request, second.request), observed
        )
    with pytest.raises(ValueError, match="observation count"):
        manifest.validate_against_samples(
            ("first", "second"), (first.request, second.request), observed[:1]
        )
    with pytest.raises(ValueError, match="mzML digest"):
        manifest.validate_against_samples(
            ("first", "second"), (first.request, second.request), ("0" * 64, observed[1])
        )
    altered = replace(
        manifest.for_sample("first"),
        source_size=manifest.for_sample("first").source_size + 1,
    )
    with pytest.raises(ValueError, match="size"):
        CohortSourceManifest((altered, manifest.for_sample("second"))).validate_against_samples(
            ("first", "second"), (first.request, second.request), observed
        )


def test_pdc_binding_receipt_and_snapshot_guards() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    sample = _pdc_sample(target, "pdc-guard", "r1")
    receipt = sample.request.external_pdc_receipt
    assert receipt is not None
    with pytest.raises(ValueError, match="do not match"):
        CohortSourceBinding.from_pdc_receipt(
            replace(sample.request, external_pdc_receipt=None), receipt
        )
    with pytest.raises(ValueError, match="metadata snapshot study"):
        CohortSourceBinding.from_pdc_receipt(
            sample.request,
            receipt,
            metadata_snapshot=cast(
                "PDCSnapshot",
                SimpleNamespace(
                    metadata=SimpleNamespace(pdc_study_id="PDC999999"),
                    digest="sha256:" + "a" * 64,
                ),
            ),
        )
    binding = CohortSourceBinding.from_pdc_receipt(sample.request, receipt)
    assert binding.metadata_snapshot_digest is None
    assert binding.source_kind == "pdc"


def test_manifest_pdc_validation_binds_receipt_locator_and_study() -> None:
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    sample = _pdc_sample(target, "pdc-a", "r1")
    second = _pdc_sample(target, "pdc-b", "r2")
    manifest = CohortSourceManifest.from_requests((sample.request, second.request))
    observed = tuple(manifest.for_sample(item).source_sha256 for item in ("pdc-a", "pdc-b"))
    bad_receipt = replace(manifest.for_sample("pdc-a"), receipt_digest="b" * 64)
    with pytest.raises(ValueError, match="receipt"):
        CohortSourceManifest((bad_receipt, manifest.for_sample("pdc-b"))).validate_against_samples(
            ("pdc-a", "pdc-b"), (sample.request, second.request), observed
        )
    bad_locator = replace(
        manifest.for_sample("pdc-a"), pdc_file_locator="https://wrong.example/file"
    )
    with pytest.raises(ValueError, match="locator"):
        CohortSourceManifest((bad_locator, manifest.for_sample("pdc-b"))).validate_against_samples(
            ("pdc-a", "pdc-b"), (sample.request, second.request), observed
        )
    bad_study = replace(manifest.for_sample("pdc-a"), pdc_study_id="PDC999999")
    with pytest.raises(ValueError, match="study"):
        CohortSourceManifest((bad_study, manifest.for_sample("pdc-b"))).validate_against_samples(
            ("pdc-a", "pdc-b"), (sample.request, second.request), observed
        )
