"""Adversarial safety tests for the private GBmap development-fit driver."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import copy
import json
import os
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    AggregateReference,
    DevelopmentTrainingResult,
    DonorLabelAggregate,
    GbmapDonorCrosswalk,
    GbmapDonorCrosswalkRule,
    GbmapExtractionReceipt,
    GbmapExtractionRecipe,
    GbmapExtractionResult,
    GbmapLabelTaxonomy,
    GbmapSourceAdmissionError,
    GbmapStudyCrosswalk,
    GbmapStudyCrosswalkRule,
    GbmapTaxonomyRule,
    HierarchySolverConfiguration,
    SparseCountBlock,
    TrainingConfiguration,
    aggregate_sparse_count_blocks,
    build_validation_split_plan,
    production_extraction_recipe,
    production_label_taxonomy,
    production_reduction_recipe_digest,
    train_development_candidate,
)
from tools import fit_gbmap_development_candidate as driver

_REVIEWED_SHA256 = "sha256:" + "a" * 64
_OTHER_SHA256 = "sha256:" + "b" * 64
_SOURCE_BYTES = 8_975_644_082


@lru_cache(maxsize=1)
def _reference() -> AggregateReference:
    feature_ids = tuple(f"ENSG{index:05d}" for index in range(24))
    mes_like = np.asarray([1_500] * 12 + [166] * 11 + [174], dtype=np.int64)
    npc_like = np.asarray([166] * 11 + [174] + [1_500] * 12, dtype=np.int64)
    studies = tuple(sorted(driver._ALLOWED_STUDY_KEYS))[:4]
    records: list[DonorLabelAggregate] = []
    for study_index, study in enumerate(studies):
        for donor_index in range(3):
            donor = f"private-donor-{study_index}-{donor_index:02d}"
            for label, counts in (("MES-like", mes_like), ("NPC-like", npc_like)):
                records.append(
                    DonorLabelAggregate(
                        donor_key=donor,
                        study_key=study,
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=40,
                        gene_counts=counts,
                        detected_cell_counts=np.asarray([30] * 24, dtype=np.int32),
                        total_umis=20_000,
                    )
                )
    return AggregateReference(
        feature_ids=feature_ids,
        gene_symbols=feature_ids,
        records=tuple(records),
        source_file_sha256=_REVIEWED_SHA256,
        source_bytes=_SOURCE_BYTES,
        taxonomy_digest=production_label_taxonomy().taxonomy_digest,
        extraction_recipe_digest=production_reduction_recipe_digest(),
    )


@lru_cache(maxsize=1)
def _trained() -> DevelopmentTrainingResult:
    hierarchy = HierarchySolverConfiguration(
        max_outer_iterations=6,
        max_study_sweeps=2,
        max_signature_iterations=20,
        max_golden_iterations=12,
        golden_log_tolerance=1e-4,
        kkt_tolerance=2e-6,
    )
    return train_development_candidate(
        _reference(),
        configuration=TrainingConfiguration(
            shrinkage_grid=(1.0,),
            minimum_whole_study_folds=1,
            minimum_within_study_donor_folds=1,
            hierarchy=hierarchy,
        ),
    )


@lru_cache(maxsize=1)
def _extraction() -> GbmapExtractionResult:
    reference = _reference()
    fields: dict[str, object] = {
        "receipt_id": "gbmap-extraction-receipt/1.0.0",
        "source_sha256": _REVIEWED_SHA256,
        "source_bytes": _SOURCE_BYTES,
        "extraction_recipe_digest": reference.extraction_recipe_digest,
        "taxonomy_digest": reference.taxonomy_digest,
        "feature_order_digest": reference.feature_order_digest,
        "h5py_version": "3.16.0",
        "cell_count": 338_564,
        "retained_cell_count": 338_564,
        "explicitly_excluded_cell_count": 0,
        "source_donor_category_count": 113,
        "grouped_donor_category_count": 110,
        "source_study_category_count": 17,
        "grouped_study_count": 16,
        "source_label_count": 20,
        "modeled_label_count": 20,
        "record_count": len(reference.records),
        "cell_level_material_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "donor_profiles_retained": False,
        "aggregate_content_digest_retained": False,
    }
    receipt = GbmapExtractionReceipt(
        receipt_digest=sha256_digest(fields),
        **fields,  # type: ignore[arg-type]
    )
    return GbmapExtractionResult(reference=reference, receipt=receipt)


def _real_aggregate_extraction_fixture() -> tuple[
    GbmapExtractionResult,
    GbmapExtractionRecipe,
    GbmapLabelTaxonomy,
]:
    """Exercise the same aggregate builder that finishes a real H5AD extraction."""

    source_donors = tuple(f"fixture-donor-{index}" for index in range(4))
    source_studies = tuple(f"fixture-study-{index}" for index in range(4))
    source_labels = ("fixture-lineage-a", "fixture-lineage-b")
    donor_crosswalk = GbmapDonorCrosswalk(
        crosswalk_id="fit-validator-fixture-donors/1.0.0",
        rules=tuple(
            GbmapDonorCrosswalkRule(
                source_donor_category=donor,
                grouped_donor_key=donor,
            )
            for donor in source_donors
        ),
    )
    study_crosswalk = GbmapStudyCrosswalk(
        crosswalk_id="fit-validator-fixture-studies/1.0.0",
        rules=tuple(
            GbmapStudyCrosswalkRule(
                source_study_category=study,
                grouped_study_key=study,
            )
            for study in source_studies
        ),
    )
    taxonomy = GbmapLabelTaxonomy(
        taxonomy_id="fit-validator-fixture-taxonomy/1.0.0",
        rules=tuple(
            GbmapTaxonomyRule(source_label=label, modeled_label=label) for label in source_labels
        ),
    )
    rows = tuple(
        (donor, study, label)
        for donor, study in zip(source_donors, source_studies, strict=True)
        for label in source_labels
        for _ in range(40)
    )
    recipe = GbmapExtractionRecipe(
        source_profile="generic_fixture",
        matrix_path="layers/counts",
        donor_path="obs/patient",
        study_path="obs/author",
        source_label_path="obs/CellID",
        feature_id_path="var/_index",
        expected_cell_count=len(rows),
        expected_feature_count=2,
        expected_source_donor_category_count=len(source_donors),
        expected_grouped_donor_category_count=len(source_donors),
        expected_source_study_category_count=len(source_studies),
        expected_grouped_study_count=len(source_studies),
        expected_source_label_count=len(source_labels),
        reviewed_donor_crosswalk_digest=donor_crosswalk.crosswalk_digest,
        reviewed_study_crosswalk_digest=study_crosswalk.crosswalk_digest,
        reviewed_label_taxonomy_digest=taxonomy.taxonomy_digest,
        expected_nnz=len(rows),
        row_block_size=len(rows),
    )
    block = SparseCountBlock(
        row_start=0,
        donor_keys=tuple(row[0] for row in rows),
        study_keys=tuple(row[1] for row in rows),
        source_labels=tuple(row[2] for row in rows),
        indptr=np.arange(len(rows) + 1, dtype=np.int64),
        indices=np.asarray(
            [source_labels.index(row[2]) for row in rows],
            dtype=np.int64,
        ),
        data=np.full(len(rows), 500, dtype=np.int64),
    )
    result = aggregate_sparse_count_blocks(
        blocks=(block,),
        feature_ids=("fixture-feature-a", "fixture-feature-b"),
        gene_symbols=(None, None),
        source_sha256=_REVIEWED_SHA256,
        source_bytes=123,
        taxonomy=taxonomy,
        donor_crosswalk=donor_crosswalk,
        study_crosswalk=study_crosswalk,
        recipe=recipe,
    )
    return result, recipe, taxonomy


def _source(tmp_path: Path, name: str = "scarches_core_GBmap.h5ad") -> Path:
    source = tmp_path / "private-source" / name
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"small mocked source; extractor remains mocked")
    return source


def _install_successful_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], dict[str, object]]:
    events: list[str] = []
    captured: dict[str, object] = {}

    def fake_extract(source: Path, **kwargs: object) -> GbmapExtractionResult:
        events.append("extract")
        captured["source"] = source
        captured.update(kwargs)
        return _extraction()

    def fake_train(reference: AggregateReference) -> DevelopmentTrainingResult:
        events.append("train")
        captured["trained_reference"] = reference
        assert reference is _reference()
        return _trained()

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", fake_extract)
    monkeypatch.setattr(driver, "train_development_candidate", fake_train)
    return events, captured


def _redigest(payload: dict[str, object]) -> None:
    body = {key: value for key, value in payload.items() if key != "bundle_digest"}
    payload["bundle_digest"] = driver._bundle_digest(body)


def _as_dict(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast("dict[str, object]", value)


def _as_list(value: object) -> list[object]:
    assert type(value) is list
    return cast("list[object]", value)


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    _install_successful_boundaries(monkeypatch)
    return driver.build_development_fit_receipts(
        _source(tmp_path),
        _REVIEWED_SHA256,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )


def test_driver_uses_original_path_exact_production_dependencies_and_typed_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, captured = _install_successful_boundaries(monkeypatch)
    source = _source(tmp_path)
    payload = driver.build_development_fit_receipts(
        source,
        _REVIEWED_SHA256,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )

    assert events == ["extract", "train"]
    assert captured["source"] is source
    assert captured["trained_reference"] is _reference()
    lock = cast("Any", captured["lock"])
    assert lock.source_id == "gbmap-core-zenodo-6962901"
    assert lock.expected_bytes == _SOURCE_BYTES
    assert lock.md5 == "308f143ba384bd9a8acb0fbf2ea005fc"
    assert lock.sha256 == _REVIEWED_SHA256
    assert lock.sha256_independently_reviewed is True
    assert cast("Any", captured["recipe"]).source_profile == "gbmap-core-zenodo-6962901"
    assert cast("Any", captured["taxonomy"]).taxonomy_id == "gbmap-cellid-identity/1.0.0"
    assert (
        cast("Any", captured["donor_crosswalk"]).crosswalk_id
        == "gbmap-zenodo-patient-to-donor/1.0.0"
    )
    assert cast("Any", captured["study_crosswalk"]).crosswalk_id == "gbmap-author-to-study/1.0.0"
    validated = driver._validate_bundle(payload)
    assert type(validated.extraction) is GbmapExtractionReceipt
    assert type(validated.training) is type(_trained().summary)
    assert payload["bundle_digest_basis"] == driver.BUNDLE_DIGEST_BASIS
    body = {key: value for key, value in payload.items() if key != "bundle_digest"}
    assert payload["bundle_digest"] == driver._bundle_digest(body)


def test_fit_bundle_requires_extractor_reduction_digest_not_plain_recipe_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _bundle(tmp_path, monkeypatch)
    reduction_digest = production_reduction_recipe_digest()
    plain_recipe_digest = production_extraction_recipe().extraction_recipe_digest
    assert reduction_digest != plain_recipe_digest
    assert _as_dict(payload["extraction_receipt"])["extraction_recipe_digest"] == (reduction_digest)

    forged = copy.deepcopy(payload)
    extraction = _as_dict(forged["extraction_receipt"])
    extraction["extraction_recipe_digest"] = plain_recipe_digest
    extraction_body = {key: value for key, value in extraction.items() if key != "receipt_digest"}
    extraction["receipt_digest"] = sha256_digest(extraction_body)
    _as_dict(forged["validation_split_receipt"])["extraction_recipe_digest"] = plain_recipe_digest
    _as_dict(forged["training_summary"])["extraction_recipe_digest"] = plain_recipe_digest
    _redigest(forged)

    with pytest.raises(driver.GbmapDevelopmentFitDriverError):
        driver._validate_bundle(forged)


def test_fit_validator_matches_digest_emitted_by_real_aggregate_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction, recipe, taxonomy = _real_aggregate_extraction_fixture()
    split = build_validation_split_plan(extraction.reference).receipt
    emitted_digest = extraction.reference.extraction_recipe_digest
    assert extraction.receipt.extraction_recipe_digest == emitted_digest
    assert emitted_digest != recipe.extraction_recipe_digest

    monkeypatch.setattr(driver, "production_extraction_recipe", lambda: recipe)
    monkeypatch.setattr(driver, "production_label_taxonomy", lambda: taxonomy)
    monkeypatch.setattr(
        driver,
        "production_reduction_recipe_digest",
        lambda: emitted_digest,
    )
    monkeypatch.setattr(
        driver,
        "development_profile",
        lambda: SimpleNamespace(source=SimpleNamespace(expected_bytes=123)),
    )
    monkeypatch.setattr(driver, "_ALLOWED_MODELED_LABELS", frozenset(taxonomy.modeled_labels))
    training = SimpleNamespace(
        source_file_sha256=extraction.reference.source_file_sha256,
        source_bytes=extraction.reference.source_bytes,
        taxonomy_digest=extraction.reference.taxonomy_digest,
        extraction_recipe_digest=emitted_digest,
        feature_order_digest=extraction.reference.feature_order_digest,
    )
    driver._validate_production_bindings(
        extraction.receipt,
        split,
        cast("Any", training),
    )

    monkeypatch.setattr(
        driver,
        "production_reduction_recipe_digest",
        lambda: recipe.extraction_recipe_digest,
    )
    with pytest.raises(ValueError, match="production semantic digests"):
        driver._validate_production_bindings(
            extraction.receipt,
            split,
            cast("Any", training),
        )


@pytest.mark.parametrize(
    "digest",
    ["a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63, "sha256:" + "g" * 64],
)
def test_noncanonical_reviewed_digest_is_rejected_before_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    digest: str,
) -> None:
    called = False

    def forbidden_snapshot(_source: Path) -> object:
        nonlocal called
        called = True
        raise AssertionError("source must not be inspected")

    monkeypatch.setattr(driver, "_capture_source_snapshot", forbidden_snapshot)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="reviewed SHA-256"):
        driver.build_development_fit_receipts(
            tmp_path / "source.h5ad",
            digest,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False


@pytest.mark.parametrize(
    ("acknowledgements", "match"),
    [((False, True), "development-only"), ((True, False), "independent SHA-256")],
)
def test_acknowledgements_are_required_before_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    acknowledgements: tuple[bool, bool],
    match: str,
) -> None:
    development_ack, review_ack = acknowledgements
    called = False

    def forbidden_snapshot(_source: Path) -> object:
        nonlocal called
        called = True
        raise AssertionError("source must not be inspected")

    monkeypatch.setattr(driver, "_capture_source_snapshot", forbidden_snapshot)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match=match):
        driver.build_development_fit_receipts(
            tmp_path / "source.h5ad",
            _REVIEWED_SHA256,
            development_only_acknowledged=development_ack,
            sha256_independently_reviewed=review_ack,
        )
    assert called is False


def test_source_inside_repository_is_rejected_before_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "source.h5ad"
    source.write_bytes(b"private")
    monkeypatch.setattr(driver, "_REPOSITORY_ROOT", repository)
    called = False

    def forbidden_extract(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("extractor must not run")

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", forbidden_extract)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="outside the repository"):
        driver.build_development_fit_receipts(
            source,
            _REVIEWED_SHA256,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False


def test_reparse_ancestor_is_rejected_without_resolving_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    reparse_parent = source.parent
    original_lstat = os.lstat

    def marked_lstat(path: os.PathLike[str] | str) -> object:
        info = original_lstat(path)
        if Path(path) != reparse_parent:
            return info
        return SimpleNamespace(
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_mode=info.st_mode,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=info.st_ctime_ns,
            st_file_attributes=driver._REPARSE_ATTRIBUTE,
        )

    monkeypatch.setattr(os, "lstat", marked_lstat)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="ancestors"):
        driver.build_development_fit_receipts(
            source,
            _REVIEWED_SHA256,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )


def test_source_identity_is_revalidated_after_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_successful_boundaries(monkeypatch)
    source = _source(tmp_path)
    original_capture = driver._capture_source_snapshot
    calls = 0

    def changed_capture(path: Path) -> object:
        nonlocal calls
        calls += 1
        snapshot = original_capture(path)
        if calls == 2:
            return replace(
                snapshot,
                source_identity=(*snapshot.source_identity[:-1], snapshot.source_identity[-1] + 1),
            )
        return snapshot

    monkeypatch.setattr(driver, "_capture_source_snapshot", changed_capture)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="identity or containment"):
        driver.build_development_fit_receipts(
            source,
            _REVIEWED_SHA256,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )


def test_sensitive_extractor_cause_is_not_retained_or_rendered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    sensitive_detail = "C:/private/patient-ALPHA/source.h5ad sha256:secret"

    def failed_extract(*_args: object, **_kwargs: object) -> object:
        raise GbmapSourceAdmissionError(sensitive_detail)

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", failed_extract)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError) as raised:
        driver.build_development_fit_receipts(
            source,
            _REVIEWED_SHA256,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert str(raised.value) == "GBmap source extraction failed closed"
    assert sensitive_detail not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize("injected_key", ["notes", "Unexpected", "serialized_parameters"])
def test_exact_nested_allowlists_reject_demonstrated_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injected_key: str,
) -> None:
    payload = copy.deepcopy(_bundle(tmp_path, monkeypatch))
    training = _as_dict(payload["training_summary"])
    if injected_key == "notes":
        training[injected_key] = "C:/private/patient.txt"
    elif injected_key == "Unexpected":
        candidate = _as_dict(_as_list(training["candidate_evaluations"])[0])
        candidate[injected_key] = "private-donor-0"
    else:
        lineage = _as_dict(_as_list(training["lineage_summaries"])[0])
        lineage[injected_key] = {"signature_matrix": [[1.0]], "concentrations": [2.0]}
    _redigest(payload)
    destination = tmp_path / f"{injected_key}.json"
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="strict validation"):
        driver.write_receipts_atomically(destination, payload)
    assert not destination.exists()


def test_allowlisted_value_domains_reject_path_or_pii_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = copy.deepcopy(_bundle(tmp_path, monkeypatch))
    training = _as_dict(payload["training_summary"])
    lineage = _as_dict(_as_list(training["lineage_summaries"])[0])
    lineage["modeled_label"] = "C:/private/patient-ALPHA/model.pkl"
    _redigest(payload)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="strict validation"):
        driver.write_receipts_atomically(tmp_path / "pii.json", payload)


def test_bundle_digest_tamper_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _bundle(tmp_path, monkeypatch)
    payload["bundle_digest"] = "sha256:" + "0" * 64
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="strict validation"):
        driver.write_receipts_atomically(tmp_path / "tampered.json", payload)


@pytest.mark.parametrize(
    ("section", "field"),
    [("training_summary", "source_file_sha256"), ("training_summary", "feature_order_digest")],
)
def test_cross_section_provenance_mismatch_is_rejected_even_with_fresh_bundle_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    field: str,
) -> None:
    payload = copy.deepcopy(_bundle(tmp_path, monkeypatch))
    _as_dict(payload[section])[field] = _OTHER_SHA256
    _redigest(payload)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="strict validation"):
        driver.write_receipts_atomically(tmp_path / f"mismatch-{field}.json", payload)


def test_atomic_outputs_are_canonical_deterministic_and_never_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_successful_boundaries(monkeypatch)
    first_source = _source(tmp_path, "first.h5ad")
    second_source = _source(tmp_path, "second.h5ad")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_size = driver.run(
        first_source,
        _REVIEWED_SHA256,
        first,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    second_size = driver.run(
        second_source,
        _REVIEWED_SHA256,
        second,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    assert first_size == second_size
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")
    parsed = json.loads(first.read_bytes())
    driver._validate_bundle(parsed)
    assert first_source.name.encode() not in first.read_bytes()

    sentinel = first.read_bytes()
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="refusing to overwrite"):
        driver.run(
            first_source,
            _REVIEWED_SHA256,
            first,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert first.read_bytes() == sentinel
    assert list(tmp_path.glob(".*.tmp")) == []


def test_existing_destination_equal_to_source_is_rejected_before_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    sentinel = source.read_bytes()
    called = False

    def forbidden_extract(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("extractor must not run")

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", forbidden_extract)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="refusing to overwrite"):
        driver.run(
            source,
            _REVIEWED_SHA256,
            source,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False
    assert source.read_bytes() == sentinel


def test_training_failure_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    destination = tmp_path / "receipts.json"
    monkeypatch.setattr(
        driver,
        "extract_pinned_gbmap_reference",
        lambda *_args, **_kwargs: _extraction(),
    )

    def failed_train(_reference: AggregateReference) -> DevelopmentTrainingResult:
        raise ValueError("private-donor-secret")

    monkeypatch.setattr(driver, "train_development_candidate", failed_train)
    with pytest.raises(driver.GbmapDevelopmentFitDriverError, match="training failed closed"):
        driver.run(
            source,
            _REVIEWED_SHA256,
            destination,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert not destination.exists()


def test_cli_failure_is_sanitized_and_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _source(tmp_path)
    destination = tmp_path / "receipt.json"

    def failed_extract(*_args: object, **_kwargs: object) -> object:
        raise GbmapSourceAdmissionError("C:/private/person/source.h5ad")

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", failed_extract)
    result = driver.main(
        [
            str(source),
            "--reviewed-sha256",
            _REVIEWED_SHA256,
            "--output",
            str(destination),
            "--acknowledge-development-only",
            "--acknowledge-sha256-independently-reviewed",
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: GBmap offline development fit failed closed\n"
    assert not destination.exists()
