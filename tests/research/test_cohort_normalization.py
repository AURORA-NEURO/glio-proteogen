"""Adversarial tests for label-aware research cohort normalization."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from evals.research_proteomics.run import build_cohort_supported_request

import glio_proteogen.research.cohort as cohort_module
from glio_proteogen.research import (
    CohortSourceBinding,
    CohortSourceManifest,
    ProteinGroup,
    ProteinGroupQuant,
    ResearchCohortRequest,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.pipeline import run_research_protein_inference


def _source_bytes(sample: ResearchCohortSample) -> bytes:
    source = sample.request.mzml_source
    if isinstance(source, bytes):
        return source
    if isinstance(source, bytearray):
        return bytes(source)
    raise TypeError("normalization fixture requires an in-memory mzML source")  # noqa: TRY003


def _sample(sample_id: str, label: str, replicate: str) -> ResearchCohortSample:
    base = build_cohort_supported_request(sample_id)
    request = replace(
        base,
        sample_id=sample_id,
        mzml_source=b"<!--"
        + sample_id.encode()
        + b"-->"
        + _source_bytes(ResearchCohortSample(sample_id, base, label, replicate)),
    )
    return ResearchCohortSample(sample_id, request, label, replicate)


def _manifest(samples: tuple[ResearchCohortSample, ...]) -> CohortSourceManifest:
    return CohortSourceManifest.from_requests(
        tuple(sample.request for sample in samples),
        replicate_kinds={sample.sample_id: "biological" for sample in samples},
    )


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


def test_technical_only_group_cannot_emit_a_descriptive_label_contrast() -> None:
    samples = tuple(
        cohort_module._CohortLabelSample(sample_id, label)
        for sample_id, label in (
            ("case-a", "case"),
            ("case-b", "case"),
            ("case-tech", "case"),
            ("control-a", "control"),
            ("control-b", "control"),
        )
    )
    manifest = CohortSourceManifest(
        tuple(
            CohortSourceBinding(
                sample_id=sample.sample_id,
                source_kind="local",
                source_id=f"local:{sample.sample_id}",
                source_sha256=f"{index + 1:064x}",
                source_size=1,
                replicate_kind=("technical" if sample.sample_id == "case-tech" else "biological"),
            )
            for index, sample in enumerate(samples)
        )
    )
    raw_matrix = (
        (("P1",), (None, None, 100.0, 10.0, 10.0)),
        (("P2",), (10.0, 10.0, 10.0, 10.0, 10.0)),
    )
    _, _, label_qc, group_evidence, _ = cohort_module._build_label_evidence(
        samples,
        (("P1",), ("P2",)),
        raw_matrix,
        "none",
        cohort_module.CohortQcPolicy(),
        manifest,
    )

    case_p1 = next(
        item
        for item in group_evidence
        if item.cohort_label == "case" and item.group_accessions == ("P1",)
    )
    assert next(item for item in label_qc if item.cohort_label == "case").status == "descriptive"
    assert case_p1.independent_observed_replicates == 0
    assert case_p1.status == "abstained_insufficient_replicates"
    p1_contrast = next(
        item
        for item in cohort_module._build_label_contrasts(group_evidence)
        if item.group_accessions == ("P1",)
    )
    assert p1_contrast.status == "abstained_label_qc"
    assert p1_contrast.median_ratio is None


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
            mzml_sha256=sha256(
                _source_bytes(
                    _sample(sample_id, "case" if sample_id.startswith("case") else "control", "r1")
                )
            ).hexdigest(),
        )
        for sample_id, pair in values.items()
    }
    monkeypatch.setattr(
        cohort_module, "run_research_protein_inference", lambda request: results[request.sample_id]
    )
    request = ResearchCohortRequest(
        samples := (
            _sample("control-b", "control", "r2"),
            _sample("case-b", "case", "r2"),
            _sample("control-a", "control", "r1"),
            _sample("case-a", "case", "r1"),
        ),
        normalization_policy="within_label_median_v1",
        source_manifest=_manifest(samples),
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
            mzml_sha256=sha256(_source_bytes(_sample(sample_id, "case", "r1"))).hexdigest(),
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
            (samples := (_sample("a", "case", "r1"), _sample("b", "case", "r2"))),
            normalization_policy="within_label_median_v1",
            source_manifest=_manifest(samples),
        )
    )
    assert all(item.status == "abstained_insufficient_overlap" for item in result.sample_scales)
    assert result.raw_matrix[0][1] == (10.0, None)
    assert all(value is None for _, values in result.normalized_matrix for value in values)
    assert result.label_qc[0].status == "abstained_insufficient_overlap"


def test_single_replicate_labels_abstain_before_scaling() -> None:
    result = run_research_cohort(
        ResearchCohortRequest(
            (samples := (_sample("a", "case", "r1"), _sample("b", "control", "r1"))),
            normalization_policy="within_label_median_v1",
            source_manifest=_manifest(samples),
        )
    )
    assert {item.status for item in result.sample_scales} == {"abstained_insufficient_replicates"}
    assert all(value is None for _, values in result.normalized_matrix for value in values)
    assert all(
        item.status == "abstained_insufficient_replicates" for item in result.label_group_evidence
    )


def test_normalization_policy_is_replay_visible_and_permutation_stable() -> None:
    samples = (_sample("a", "case", "r1"), _sample("b", "case", "r2"))
    manifest = _manifest(samples)
    with pytest.raises(ValueError, match="normalization_policy"):
        ResearchCohortRequest(samples, normalization_policy="mean_impute")
    first = run_research_cohort(
        ResearchCohortRequest(
            samples,
            normalization_policy="within_label_median_v1",
            source_manifest=manifest,
        )
    )
    second = run_research_cohort(
        ResearchCohortRequest(
            tuple(reversed(samples)),
            normalization_policy="within_label_median_v1",
            source_manifest=manifest,
        )
    )
    assert first.result_digest == second.result_digest
    assert dict(first.configuration)["cohort_normalization_version"] == "within-label-median-v1"
    with pytest.raises(ValueError, match="replay"):
        replay_research_cohort(
            ResearchCohortRequest(samples, normalization_policy="none", source_manifest=manifest),
            first,
        )
