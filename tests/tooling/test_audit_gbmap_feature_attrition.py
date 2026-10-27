"""Source-bound feature-diagnostic driver tests using synthetic private aggregates."""

# ruff: noqa: PLR2004 -- compact synthetic fixtures and deliberate private failures

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    AggregateReference,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    build_validation_split_plan,
    training,
)
from glio_proteogen.research.gbmap_development_diagnostics import (
    ReferenceAttritionReceipt,
    audit_reference,
)
from tests.tooling import test_preflight_gbmap_development_candidate as base
from tools import audit_gbmap_feature_attrition as driver
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as tasks


def _hash(label):
    return sha256_digest({"synthetic": label})


def _forbidden(*_args, **_kwargs):
    pytest.fail("feature diagnostics must not fit, load checkpoints, or build numerical tasks")


@lru_cache(maxsize=1)
def _state():
    extraction = base._extraction()
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, base._REVIEWED_SHA256)
    manifest, _ = tasks._build_manifest_and_tasks(extraction, plan, preflight)
    report = audit_reference(
        extraction.reference, development_profile_digest=preflight.profile_digest
    )
    return extraction, preflight, manifest, report


@pytest.fixture
def case(tmp_path, monkeypatch):
    extraction, preflight, manifest, report = _state()
    source = base._source(tmp_path)
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_bytes(preflight_driver.canonical_preflight_receipt_bytes(preflight))
    state = SimpleNamespace(
        source=source,
        preflight_path=preflight_path,
        run_directory=tmp_path / "private-run",
        extraction=extraction,
        preflight=preflight,
        manifest=manifest,
        report=report,
        extraction_calls=[],
        diagnostic_calls=[],
        guards=[],
    )

    def extract(source, **kwargs):
        state.extraction_calls.append((source, kwargs))
        return extraction

    def audit(reference, **kwargs):
        state.diagnostic_calls.append((reference, kwargs))
        return report

    original_guard = driver.fit_driver._open_source_guard

    def guard(snapshot):
        handle = original_guard(snapshot)
        state.guards.append(handle)
        return handle

    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", extract)
    monkeypatch.setattr(driver, "audit_reference", audit)
    monkeypatch.setattr(driver, "method_digest", lambda: _hash("current-method"))
    monkeypatch.setattr(driver.fit_driver, "_open_source_guard", guard)
    for name in (
        "run_batch",
        "_load_checkpoints",
        "_build_manifest_and_tasks",
        "_execute_task",
        "_training_matrix_digest",
        "_fit_label",
    ):
        monkeypatch.setattr(tasks, name, _forbidden)
    monkeypatch.setattr(training, "_fit_label", _forbidden)
    monkeypatch.setattr(training, "train_development_candidate", _forbidden)
    monkeypatch.setattr(driver.fit_driver, "train_development_candidate", _forbidden)
    return state


def _run(case, *, run_directory=None, **changes):
    return driver.run_audit(
        case.source,
        changes.get("reviewed_sha256", base._REVIEWED_SHA256),
        case.preflight_path,
        run_directory=run_directory,
        development_only_acknowledged=changes.get("development_only_acknowledged", True),
        sha256_independently_reviewed=changes.get("sha256_independently_reviewed", True),
    )


def _seal(document, field, *, schema=None):
    result = deepcopy(document)
    result.pop(field, None)
    return {
        **result,
        field: sha256_digest(result if schema is None else {"schema": schema, **result}),
    }


def _manifest(case, *, change=None):
    document = case.manifest.model_dump(mode="json")
    if change is not None:
        change(document)
    document["tasks"] = [
        _seal(row, "task_digest", schema=tasks.TASK_SCHEMA) for row in document["tasks"]
    ]
    document["tasks"].sort(
        key=lambda row: (row["fold_id"], row["shrinkage_index"], row["modeled_label"])
    )
    document["task_inventory_digest"] = sha256_digest(
        {"schema": tasks.TASK_INVENTORY_SCHEMA, "tasks": document["tasks"]}
    )
    receipt = tasks.GbmapHierarchyRunManifest.model_validate_json(
        canonical_json_bytes(_seal(document, "manifest_digest"))
    )
    case.run_directory.mkdir(exist_ok=True)
    path = case.run_directory / tasks.MANIFEST_NAME
    path.write_bytes(tasks.canonical_manifest_bytes(receipt))
    return path, receipt


def _cli(case, *options):
    return [
        "run",
        str(case.source),
        "--reviewed-sha256",
        base._REVIEWED_SHA256,
        "--preflight",
        str(case.preflight_path),
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
        *options,
    ]


def test_run_replays_exact_source_and_preflight_without_fitting_or_numerical_tasks(case):
    bundle = _run(case)
    assert bundle.report == case.report
    assert bundle.source_replay.preflight_receipt_digest == case.preflight.receipt_digest
    assert bundle.manifest_comparison is None
    assert len(case.extraction_calls) == 1
    assert case.diagnostic_calls == [
        (case.extraction.reference, {"development_profile_digest": case.preflight.profile_digest})
    ]
    source, arguments = case.extraction_calls[0]
    assert source == case.source
    assert arguments["lock"].sha256 == base._REVIEWED_SHA256
    assert arguments["lock"].expected_bytes == base._SOURCE_BYTES
    assert arguments["lock"].sha256_independently_reviewed is True
    assert arguments["recipe"].source_profile == "gbmap-core-zenodo-6962901"
    assert arguments["taxonomy"].taxonomy_id == "gbmap-cellid-identity/1.0.0"
    assert arguments["donor_crosswalk"].crosswalk_id == "gbmap-zenodo-patient-to-donor/1.0.0"
    assert arguments["study_crosswalk"].crosswalk_id == "gbmap-author-to-study/1.0.0"
    assert len(case.guards) == 1
    assert case.guards[0].mode == "rb"
    assert case.guards[0].closed
    assert not case.run_directory.exists()
    payload = driver.canonical_bundle_bytes(bundle)
    for private in (b"private-donor", b"ENSG", b"gene_counts", b"detected_cell_counts"):
        assert private not in payload
    assert str(case.source).encode() not in payload
    assert b'"manifest_comparison":null' in payload
    assert bundle.report.model_fitting_performed is False
    assert bundle.report.inference_performed is False
    assert bundle.report.final_fit_eligibility_established is False


def test_run_can_project_the_real_pure_diagnostic_over_synthetic_aggregates(monkeypatch, case):
    monkeypatch.setattr(driver, "audit_reference", audit_reference)
    assert _run(case).report == case.report


@pytest.mark.parametrize(
    "field", ["development_only_acknowledged", "sha256_independently_reviewed"]
)
@pytest.mark.parametrize("value", [False, 0, 1, None])
def test_acknowledgements_are_exact_and_precede_all_private_io(monkeypatch, case, field, value):
    monkeypatch.setattr(tasks, "_read_regular_bytes", _forbidden)
    monkeypatch.setattr(driver.fit_driver, "_capture_source_snapshot", _forbidden)
    with pytest.raises(driver.fit_driver.GbmapDevelopmentFitDriverError, match="acknowledgement"):
        _run(case, **{field: value})
    assert case.extraction_calls == case.diagnostic_calls == case.guards == []


@pytest.mark.parametrize("value", ["a" * 64, "sha256:" + "A" * 64, "private-source-token"])
def test_reviewed_digest_format_is_checked_before_private_io(monkeypatch, case, value):
    monkeypatch.setattr(tasks, "_read_regular_bytes", _forbidden)
    with pytest.raises(driver.fit_driver.GbmapDevelopmentFitDriverError):
        _run(case, reviewed_sha256=value)
    assert case.extraction_calls == []


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_json",
        "indentation",
        "missing_newline",
        "seal",
        "profile",
        "engine",
        "configuration",
        "extra",
    ],
)
def test_invalid_or_noncanonical_preflight_rejects_before_source_access(monkeypatch, case, kind):
    document = case.preflight.model_dump(mode="json")
    payload = case.preflight_path.read_bytes()
    if kind == "duplicate_json":
        payload = payload.replace(
            b'"receipt_digest":',
            b'"receipt_digest":"' + _hash("bad").encode() + b'","receipt_digest":',
            1,
        )
    elif kind == "indentation":
        payload = json.dumps(document, indent=2).encode() + b"\n"
    elif kind == "missing_newline":
        payload = payload[:-1]
    elif kind == "seal":
        document["receipt_digest"] = _hash("bad seal")
        payload = canonical_json_bytes(document) + b"\n"
    else:
        field = {
            "profile": "profile_digest",
            "engine": "engine_semantic_digest",
            "configuration": "training_configuration_digest",
            "extra": "private_donor_key",
        }[kind]
        document[field] = _hash("foreign or private field")
        payload = canonical_json_bytes(_seal(document, "receipt_digest")) + b"\n"
    case.preflight_path.write_bytes(payload)
    monkeypatch.setattr(driver.fit_driver, "_capture_source_snapshot", _forbidden)
    with pytest.raises(driver.fit_driver.GbmapDevelopmentFitDriverError):
        _run(case)
    assert case.extraction_calls == case.diagnostic_calls == []


def test_preflight_must_bind_the_reviewed_sha_before_extraction(case):
    with pytest.raises(driver.AttritionAuditError, match="independently reviewed source"):
        _run(case, reviewed_sha256=_hash("other reviewed source"))
    assert case.extraction_calls == case.diagnostic_calls == []


def test_fresh_preflight_equality_is_required_before_diagnostic_projection(monkeypatch, case):
    fields = case.extraction.receipt.model_dump(mode="json")
    fields["record_count"] += 1
    changed = GbmapExtractionReceipt.model_validate_json(
        canonical_json_bytes(_seal(fields, "receipt_digest"))
    )
    extraction = GbmapExtractionResult(reference=case.extraction.reference, receipt=changed)
    monkeypatch.setattr(
        driver, "extract_pinned_gbmap_reference", lambda *_args, **_kwargs: extraction
    )
    with pytest.raises(driver.AttritionAuditError, match="approved preflight"):
        _run(case)
    assert case.diagnostic_calls == []
    assert all(handle.closed for handle in case.guards)


def test_optional_manifest_compares_preparation_only_and_reads_no_checkpoint_material(case):
    path, manifest = _manifest(case)
    before = path.read_bytes()
    checkpoint_directory = case.run_directory / tasks.CHECKPOINT_DIRECTORY_NAME
    checkpoint_directory.mkdir()
    sentinel = checkpoint_directory / "do-not-read.private"
    sentinel.write_bytes(b"synthetic unparsed numerical material")
    bundle = _run(case, run_directory=case.run_directory)
    comparison = bundle.manifest_comparison
    assert comparison.manifest_digest == manifest.manifest_digest
    assert comparison.compared_fold_count == len(manifest.preparation_receipts)
    assert comparison.scheduled_task_count == manifest.task_count
    assert comparison.comparison_scope == "preparation_counts_and_scheduled_lineage_axis_only"
    assert comparison.hierarchy_results_inspected is False
    assert comparison.training_matrix_replay_performed is False
    assert path.read_bytes() == before
    assert sentinel.read_bytes() == b"synthetic unparsed numerical material"


def test_optional_manifest_never_creates_a_run_or_checkpoint_directory(case):
    with pytest.raises(driver.AttritionAuditError, match="existing private hierarchy"):
        _run(case, run_directory=case.run_directory)
    assert not case.run_directory.exists()
    assert case.extraction_calls == []


def test_optional_existing_directory_requires_a_manifest_and_remains_unchanged(case):
    case.run_directory.mkdir()
    sentinel = case.run_directory / "unrelated.private"
    sentinel.write_bytes(b"synthetic unrelated file")
    with pytest.raises(tasks.GbmapHierarchyTaskDriverError):
        _run(case, run_directory=case.run_directory)
    assert tuple(case.run_directory.iterdir()) == (sentinel,)
    assert case.extraction_calls == case.guards == []


def test_source_must_remain_outside_the_optional_run_before_guard_or_extraction(case):
    _manifest(case)
    contained = case.run_directory / "source.h5ad"
    contained.write_bytes(b"small synthetic contained source")
    case.source = contained
    with pytest.raises(driver.AttritionAuditError, match="outside its hierarchy run"):
        _run(case, run_directory=case.run_directory)
    assert case.extraction_calls == case.guards == []


@pytest.mark.parametrize("kind", ["duplicate_json", "indentation", "seal"])
def test_optional_manifest_must_be_canonical_before_source_access(case, kind):
    path, manifest = _manifest(case)
    payload = path.read_bytes()
    if kind == "duplicate_json":
        payload = payload.replace(
            b'"manifest_digest":',
            b'"manifest_digest":"' + _hash("bad").encode() + b'","manifest_digest":',
            1,
        )
    else:
        document = manifest.model_dump(mode="json")
        if kind == "indentation":
            payload = json.dumps(document, indent=2).encode() + b"\n"
        else:
            document["manifest_digest"] = _hash("bad seal")
            payload = canonical_json_bytes(document) + b"\n"
    path.write_bytes(payload)
    with pytest.raises(tasks.GbmapHierarchyTaskDriverError):
        _run(case, run_directory=case.run_directory)
    assert case.extraction_calls == case.guards == []


@pytest.mark.parametrize("kind", ["omitted", "reordered", "wrong_family", "planning_unavailable"])
def test_report_fold_axis_is_bound_to_preflight_even_without_a_manifest(monkeypatch, case, kind):
    document = case.report.model_dump(mode="json")
    if kind == "omitted":
        document["partitions"].pop(1)
    elif kind == "reordered":
        document["partitions"][1], document["partitions"][2] = (
            document["partitions"][2],
            document["partitions"][1],
        )
    elif kind == "wrong_family":
        partition = document["partitions"][1]
        partition.update(
            partition_id="within-study-donor-0999",
            fold_id="within-study-donor-0999",
            kind="within_study_donor",
        )
        document["partitions"][1] = _seal(partition, "partition_digest")
        document["partitions"][1:] = sorted(
            document["partitions"][1:], key=lambda row: row["partition_id"]
        )
    else:
        document["partitions"] = document["partitions"][:1]
        document["planning_state"] = "not_available"
        document["planning_failure_reason"] = "fewer_than_two_usable_labels"
    sealed = _seal(document, "receipt_digest")
    if kind == "reordered":
        # Exercise the driver's boundary against post-validation model copying;
        # the pure receipt's canonical order validator independently rejects JSON.
        with pytest.raises(ValidationError):
            ReferenceAttritionReceipt.model_validate_json(canonical_json_bytes(sealed))
        partitions = list(case.report.partitions)
        partitions[1], partitions[2] = partitions[2], partitions[1]
        report = case.report.model_copy(
            update={"partitions": tuple(partitions), "receipt_digest": sealed["receipt_digest"]}
        )
    else:
        report = ReferenceAttritionReceipt.model_validate_json(canonical_json_bytes(sealed))
    monkeypatch.setattr(driver, "audit_reference", lambda *_args, **_kwargs: report)
    with pytest.raises(driver.AttritionAuditError, match="original validation fold axis"):
        _run(case)
    assert not case.run_directory.exists()
    assert all(handle.closed for handle in case.guards)


@pytest.mark.parametrize(
    "field",
    [
        "profile_digest",
        "engine_semantic_digest",
        "feature_order_digest",
        "preflight_receipt_digest",
        "split_receipt_digest",
        "extraction_receipt_digest",
    ],
)
def test_foreign_manifest_context_rejects_before_source_replay(case, field):
    _manifest(case, change=lambda document: document.update({field: _hash("foreign context")}))
    with pytest.raises(driver.AttritionAuditError, match="approved preflight"):
        _run(case, run_directory=case.run_directory)
    assert case.extraction_calls == case.diagnostic_calls == []


@pytest.mark.parametrize("kind", ["preparation_features", "lineage_axis"])
def test_manifest_reconciliation_checks_counts_and_exact_lineages(case, kind):
    def change(document):
        fold_id = document["preparation_receipts"][0]["fold_id"]
        if kind == "preparation_features":
            document["preparation_receipts"][0]["selected_feature_count"] += 1
            for row in document["tasks"]:
                if row["fold_id"] == fold_id:
                    row["selected_feature_count"] += 1
        else:
            for row in document["tasks"]:
                if row["modeled_label"] == "NPC-like":
                    row["modeled_label"] = "OPC-like"

    _manifest(case, change=change)
    with pytest.raises(
        driver.AttritionAuditError, match=r"original fold preparation|scheduled lineage"
    ):
        _run(case, run_directory=case.run_directory)


def test_numerical_matrix_bindings_are_not_claimed_as_replayed_by_metadata_comparison(case):
    def change(document):
        for row in document["tasks"]:
            row["training_matrix_digest"] = _hash("opaque alternate numerical matrix")

    _manifest(case, change=change)
    bundle = _run(case, run_directory=case.run_directory)
    assert bundle.manifest_comparison.training_matrix_replay_performed is False
    assert bundle.manifest_comparison.hierarchy_results_inspected is False


@pytest.mark.parametrize("phase", ["extraction", "diagnostics", "bundle"])
def test_source_mutation_during_any_replay_phase_rejects_and_closes_guard(monkeypatch, case, phase):
    def change_source(result):
        case.source.write_bytes(b"changed synthetic source")
        return result

    if phase == "extraction":
        monkeypatch.setattr(
            driver,
            "extract_pinned_gbmap_reference",
            lambda *_args, **_kwargs: change_source(case.extraction),
        )
    elif phase == "diagnostics":
        monkeypatch.setattr(
            driver, "audit_reference", lambda *_args, **_kwargs: change_source(case.report)
        )
    else:
        original = driver._bundle
        monkeypatch.setattr(driver, "_bundle", lambda *args: change_source(original(*args)))
    with pytest.raises(
        driver.fit_driver.GbmapDevelopmentFitDriverError, match="identity or containment changed"
    ):
        _run(case)
    assert case.guards
    assert all(handle.closed for handle in case.guards)


@pytest.mark.parametrize("phase", ["extraction", "diagnostics", "bundle"])
def test_optional_manifest_must_stay_byte_identical_through_replay(monkeypatch, case, phase):
    _manifest(case)

    def change_manifest(result):
        def change(document):
            for row in document["tasks"]:
                row["training_matrix_digest"] = _hash("changed during audit")

        _manifest(case, change=change)
        return result

    if phase == "extraction":
        monkeypatch.setattr(
            driver,
            "extract_pinned_gbmap_reference",
            lambda *_args, **_kwargs: change_manifest(case.extraction),
        )
    elif phase == "diagnostics":
        monkeypatch.setattr(
            driver, "audit_reference", lambda *_args, **_kwargs: change_manifest(case.report)
        )
    else:
        original = driver._bundle
        monkeypatch.setattr(driver, "_bundle", lambda *args: change_manifest(original(*args)))
    with pytest.raises(driver.AttritionAuditError, match="manifest changed"):
        _run(case, run_directory=case.run_directory)
    assert case.guards
    assert all(handle.closed for handle in case.guards)


def _failed_report(report):
    document = report.model_dump(mode="json")
    partitions = []
    for partition in document["partitions"]:
        partition["selection_state"] = "failed"
        partition["selection_failure_reason"] = "selector_failed"
        partition["selector_union_feature_count"] = None
        if partition["kind"] != "full_source":
            partition.update(
                preparation_state="failed",
                preparation_reason="preparation_failed",
                prepared_eligible_lineage_count=None,
                prepared_feature_count=None,
            )
        for label in partition["labels"]:
            label["marker_state"] = "selection_failed"
            label["markers"] = None
            if partition["kind"] != "full_source":
                label["enters_prepared_fold"] = False
        partitions.append(_seal(partition, "partition_digest"))
    document["partitions"] = partitions
    return ReferenceAttritionReceipt.model_validate_json(
        canonical_json_bytes(_seal(document, "receipt_digest"))
    )


def test_unavailable_marker_measurements_remain_explicit_nulls_not_zero(monkeypatch, case):
    failed = _failed_report(case.report)
    monkeypatch.setattr(driver, "audit_reference", lambda *_args, **_kwargs: failed)
    bundle = _run(case)
    assert bundle.report == failed
    assert all(part.selector_union_feature_count is None for part in bundle.report.partitions)
    assert all(label.markers is None for part in bundle.report.partitions for label in part.labels)
    assert bundle.manifest_comparison is None
    assert all(part.selection_state == "failed" for part in bundle.report.partitions)


def test_computed_zero_markers_remain_available_zero_metrics(monkeypatch, case):
    original = case.extraction.reference
    equal_counts = original.records[0].gene_counts
    reference = AggregateReference(
        feature_ids=original.feature_ids,
        gene_symbols=original.gene_symbols,
        records=tuple(replace(row, gene_counts=equal_counts) for row in original.records),
        source_file_sha256=original.source_file_sha256,
        source_bytes=original.source_bytes,
        taxonomy_digest=original.taxonomy_digest,
        extraction_recipe_digest=original.extraction_recipe_digest,
    )
    extraction = GbmapExtractionResult(reference=reference, receipt=case.extraction.receipt)
    monkeypatch.setattr(
        driver, "extract_pinned_gbmap_reference", lambda *_args, **_kwargs: extraction
    )
    monkeypatch.setattr(driver, "audit_reference", audit_reference)
    full = _run(case).report.partitions[0]
    assert full.selection_state == "completed"
    assert full.selector_union_feature_count == 0
    present = tuple(label for label in full.labels if label.training_support.raw_record_count)
    assert len(present) == 2
    assert all(
        label.marker_state == "available" and label.markers.passing_gene_count == 0
        for label in present
    )


def test_saved_verification_is_current_method_integrity_only(tmp_path, case, monkeypatch):
    bundle = _run(case)
    output = tmp_path / "diagnostics.json"
    output.write_bytes(driver.canonical_bundle_bytes(bundle))
    monkeypatch.setattr(driver, "run_audit", _forbidden)
    monkeypatch.setattr(driver, "extract_pinned_gbmap_reference", _forbidden)
    assert driver.verify_saved(output) == {
        "verified": True,
        "verification_scope": "saved_integrity_not_source_replay",
        "bundle_digest": bundle.bundle_digest,
        "hierarchy_training_executed": False,
        "model_fitted": False,
        "runtime_mount_permitted": False,
    }


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_json",
        "indentation",
        "missing_newline",
        "seal",
        "method",
        "extra",
        "false_as_zero",
    ],
)
def test_saved_verification_rejects_noncanonical_tampered_or_stale_receipts(
    tmp_path, monkeypatch, case, kind
):
    bundle = _run(case)
    document = bundle.model_dump(mode="json")
    payload = driver.canonical_bundle_bytes(bundle)
    if kind == "duplicate_json":
        payload = payload.replace(
            b'"bundle_digest":',
            b'"bundle_digest":"' + _hash("wrong").encode() + b'","bundle_digest":',
            1,
        )
    elif kind == "indentation":
        payload = json.dumps(document, indent=2).encode() + b"\n"
    elif kind == "missing_newline":
        payload = payload[:-1]
    elif kind == "seal":
        document["bundle_digest"] = _hash("wrong seal")
        payload = canonical_json_bytes(document) + b"\n"
    elif kind == "method":
        monkeypatch.setattr(driver, "method_digest", lambda: _hash("new method"))
    else:
        if kind == "extra":
            document["private_source_path"] = "synthetic-private-material"
        else:
            document["report"]["model_fitting_performed"] = 0
            document["report"] = _seal(document["report"], "receipt_digest")
        payload = canonical_json_bytes(_seal(document, "bundle_digest")) + b"\n"
    output = tmp_path / "tampered.json"
    output.write_bytes(payload)
    with pytest.raises((driver.AttritionAuditError, ValidationError)):
        driver.verify_saved(output)


@pytest.mark.parametrize(
    "field",
    [
        "source_sha256",
        "source_bytes",
        "taxonomy_digest",
        "extraction_recipe_digest",
        "feature_order_digest",
        "profile_digest",
    ],
)
def test_closed_bundle_rejects_divergent_report_source_bindings(case, field):
    document = _run(case).model_dump(mode="json")
    document["source_replay"][field] = (
        document["source_replay"][field] + 1
        if field == "source_bytes"
        else _hash("foreign report binding")
    )
    with pytest.raises((driver.AttritionAuditError, ValidationError), match="source bindings"):
        driver.DiagnosticBundle.model_validate_json(
            canonical_json_bytes(_seal(document, "bundle_digest"))
        )


def test_manifest_comparison_permission_flags_require_exact_false(case):
    _manifest(case)
    document = _run(case, run_directory=case.run_directory).model_dump(mode="json")
    document["manifest_comparison"]["training_matrix_replay_performed"] = 0
    with pytest.raises(ValidationError, match="exact false"):
        driver.DiagnosticBundle.model_validate_json(
            canonical_json_bytes(_seal(document, "bundle_digest"))
        )


@pytest.mark.parametrize("field", ["compared_fold_count", "scheduled_task_count"])
def test_manifest_comparison_counts_must_conserve_actual_report_dimensions(case, field):
    _manifest(case)
    document = _run(case, run_directory=case.run_directory).model_dump(mode="json")
    document["manifest_comparison"][field] += 1
    with pytest.raises((driver.AttritionAuditError, ValidationError), match="dimensions"):
        driver.DiagnosticBundle.model_validate_json(
            canonical_json_bytes(_seal(document, "bundle_digest"))
        )


def test_bundle_fold_axis_digest_must_match_its_ordered_report(case):
    document = _run(case).model_dump(mode="json")
    document["source_replay"]["validation_fold_axis_digest"] = _hash("other fold axis")
    with pytest.raises((driver.AttritionAuditError, ValidationError), match="fold axis"):
        driver.DiagnosticBundle.model_validate_json(
            canonical_json_bytes(_seal(document, "bundle_digest"))
        )


@pytest.mark.parametrize("field", ["profile_digest", "engine_semantic_digest"])
def test_saved_verification_requires_the_current_profile_and_engine(
    tmp_path, monkeypatch, case, field
):
    bundle = _run(case)
    output = tmp_path / "diagnostics.json"
    output.write_bytes(driver.canonical_bundle_bytes(bundle))
    profile = driver.development_profile()
    monkeypatch.setattr(
        driver,
        "development_profile",
        lambda: profile.model_copy(update={field: _hash("changed current profile")}),
    )
    with pytest.raises(driver.AttritionAuditError, match="current method"):
        driver.verify_saved(output)


def test_canonical_export_revalidates_instances_and_retained_size_bound(monkeypatch, case):
    bundle = _run(case)
    forged = bundle.model_copy(update={"bundle_digest": _hash("wrong seal")})
    with pytest.raises((driver.AttritionAuditError, ValidationError)):
        driver.canonical_bundle_bytes(forged)
    monkeypatch.setattr(driver, "_MAX_BYTES", 1)
    with pytest.raises(driver.AttritionAuditError, match="output bound"):
        driver.canonical_bundle_bytes(bundle)


def test_method_digest_binds_profile_all_new_sources_and_boundary_tools_and_normalizes_crlf(
    tmp_path, monkeypatch
):
    for namespace_name in ("gbmap_development_diagnostics", "gbmap_development_reduction"):
        namespace = tmp_path / "src/glio_proteogen/research" / namespace_name
        namespace.mkdir(parents=True)
        for name in ("__init__.py", "audit.py", "contracts.py"):
            (namespace / name).write_bytes(b"placeholder")
    monkeypatch.setattr(driver, "_ROOT", tmp_path)
    monkeypatch.setattr(
        driver, "development_profile", lambda: SimpleNamespace(profile_digest=_hash("profile"))
    )
    current = [b"source-code\r\n"]
    paths = []

    def read(path, _maximum, _message):
        paths.append(path.relative_to(tmp_path).as_posix())
        return current[0]

    monkeypatch.setattr(tasks, "_read_regular_bytes", read)
    first = driver.method_digest()
    assert len(paths) == 11
    assert "tools/audit_gbmap_feature_attrition.py" in paths
    assert "tools/run_gbmap_hierarchy_tasks.py" in paths
    assert "tools/capture_gbmap_source_admission.py" in paths
    assert "src/glio_proteogen/research/gbmap_development_reduction/contracts.py" in paths
    current[0] = b"source-code\n"
    assert driver.method_digest() == first
    current[0] = b"changed-source\n"
    assert driver.method_digest() != first
    current[0] = b"source-code\n"
    monkeypatch.setattr(
        driver,
        "development_profile",
        lambda: SimpleNamespace(profile_digest=_hash("changed-profile")),
    )
    assert driver.method_digest() != first


def test_method_digest_refuses_an_unavailable_diagnostic_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_ROOT", tmp_path)
    with pytest.raises(driver.AttritionAuditError, match="method source is unavailable"):
        driver.method_digest()


def test_cli_run_and_verify_publish_idempotent_scoped_receipts(tmp_path, case, capsys):
    output = tmp_path / "diagnostics.json"
    arguments = _cli(case, "--output", str(output))
    assert driver.main(arguments) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.encode() == output.read_bytes()
    assert driver.main(arguments) == 0
    assert capsys.readouterr().out == captured.out
    assert driver.main(["verify", str(output)]) == 0
    assert (
        json.loads(capsys.readouterr().out)["verification_scope"]
        == "saved_integrity_not_source_replay"
    )


def test_cli_can_report_aggregate_diagnostics_on_stdout_without_an_output_file(case, capsys):
    assert driver.main(_cli(case)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["manifest_comparison"] is None
    assert not case.run_directory.exists()


@pytest.mark.parametrize("kind", ["inside_run", "repository", "existing", "source"])
def test_cli_rejects_unsafe_output_without_overwriting(case, tmp_path, capsys, kind):
    _manifest(case)
    existing = b"unchanged synthetic bytes"
    if kind == "inside_run":
        output = case.run_directory / "diagnostics.json"
    elif kind == "repository":
        output = driver._ROOT / "feature-audit-must-not-be-created.json"
        assert not output.exists()
    elif kind == "source":
        output = case.source
        existing = output.read_bytes()
    else:
        output = tmp_path / "existing.json"
        output.write_bytes(existing)
    assert (
        driver.main(_cli(case, "--run-directory", str(case.run_directory), "--output", str(output)))
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap feature diagnostics failed closed\n"
    if kind in {"existing", "source"}:
        assert output.read_bytes() == existing
    else:
        assert not output.exists()


@pytest.mark.parametrize("command", ["run", "verify"])
def test_cli_runtime_failures_never_echo_private_paths_or_nested_errors(
    monkeypatch, case, capsys, command
):
    sentinel = "SYNTHETIC_PRIVATE_PATH_OR_DATA"

    def fail(*_args, **_kwargs):
        raise OSError(sentinel)

    monkeypatch.setattr(driver, "run_audit" if command == "run" else "verify_saved", fail)
    assert driver.main(_cli(case) if command == "run" else ["verify", sentinel]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap feature diagnostics failed closed\n"
    assert sentinel not in captured.err


@pytest.mark.parametrize("phase", ["extraction", "diagnostics"])
def test_cli_inner_failures_close_source_guard_and_publish_no_partial_output(
    monkeypatch, case, tmp_path, capsys, phase
):
    sentinel = "SYNTHETIC_PRIVATE_INNER_FAILURE"

    def fail(*_args, **_kwargs):
        raise OSError(sentinel)

    monkeypatch.setattr(
        driver,
        "extract_pinned_gbmap_reference" if phase == "extraction" else "audit_reference",
        fail,
    )
    output = tmp_path / "must-not-be-published.json"
    assert driver.main(_cli(case, "--output", str(output))) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap feature diagnostics failed closed\n"
    assert sentinel not in captured.err
    assert not output.exists()
    assert case.guards
    assert all(handle.closed for handle in case.guards)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["SYNTHETIC_PRIVATE_COMMAND"],
        ["run", "SYNTHETIC_PRIVATE_PATH"],
        ["verify"],
        ["verify", "SYNTHETIC_PRIVATE_PATH", "--unknown-private-option"],
    ],
)
def test_cli_parse_failures_are_sanitized_and_never_reach_io(monkeypatch, capsys, arguments):
    monkeypatch.setattr(driver, "run_audit", _forbidden)
    monkeypatch.setattr(driver, "verify_saved", _forbidden)
    monkeypatch.setattr(tasks, "_read_regular_bytes", _forbidden)
    with pytest.raises(SystemExit) as failure:
        driver.main(arguments)
    captured = capsys.readouterr()
    assert failure.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: feature diagnostics arguments were not accepted\n"
    assert "SYNTHETIC_PRIVATE" not in captured.err


def test_cli_help_is_static_and_never_reaches_io(monkeypatch, capsys):
    monkeypatch.setattr(driver, "run_audit", _forbidden)
    monkeypatch.setattr(driver, "verify_saved", _forbidden)
    monkeypatch.setattr(tasks, "_read_regular_bytes", _forbidden)
    with pytest.raises(SystemExit) as failure:
        driver.main(["run", "--help", "SYNTHETIC_PRIVATE_PATH"])
    captured = capsys.readouterr()
    assert failure.value.code == 0
    assert captured.err == ""
    assert "usage:" in captured.out
    assert "SYNTHETIC_PRIVATE" not in captured.out
