"""Synthetic complete-baseline admission, exact replay and tamper boundaries."""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import stat
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_census_execution import baseline as boundary
from glio_proteogen.research.cptac_gbm_census_execution.contracts import (
    EXECUTION_ARTIFACT_NAMES,
    ArtifactBinding,
    ExecutionBaselineError,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.identity import HGNC_LOCK
from glio_proteogen.research.cptac_gbm_external_admission.protein import ProteinPanelCoverage
from tests.research import test_cptac_source_fit_census_runner as inherited


def _lock(data):
    return SourceLock(
        len(data),
        hashlib.md5(data, usedforsecurity=False).hexdigest(),
        hashlib.sha256(data).hexdigest(),
    )


def _load(directory):
    return boundary.load_baseline_census(
        directory=directory,
        protocol_lock=_lock((directory / "protocol.json").read_bytes()),
        evaluation_lock=_lock((directory / "evaluation.json").read_bytes()),
    )


@pytest.fixture(scope="module")
def complete_baseline(tmp_path_factory):
    directory = tmp_path_factory.mktemp("synthetic-locked-census")
    with pytest.MonkeyPatch.context() as patch:
        harness = inherited.harness.__wrapped__(directory, patch)
        for name, protein in harness.proteins.items():
            coverage = []
            for symbol in PANEL:
                rows = [
                    index
                    for index, identity in enumerate(protein.identities)
                    if identity is not None and identity.symbol == symbol
                ]
                if not rows:
                    coverage.append(ProteinPanelCoverage(symbol, 0, None, None, None))
                else:
                    finite = int(np.isfinite(protein.values[rows[0]]).sum())
                    coverage.append(
                        ProteinPanelCoverage(
                            symbol,
                            1,
                            finite,
                            protein.values.shape[1] - finite,
                            protein.values.shape[1],
                        )
                    )
            harness.proteins[name] = replace(
                protein,
                receipt=replace(
                    protein.receipt,
                    panel_coverage=tuple(coverage),
                    protein_sha256=(
                        inherited.runner.discovery_module
                        if name == "source"
                        else inherited.runner.protein
                    ).PROTEIN_LOCK.sha256,
                    sample_map_sha256=(
                        inherited.runner.discovery_module
                        if name == "source"
                        else inherited.runner.protein
                    ).SAMPLE_MAP_LOCK.sha256,
                    hgnc_sha256=HGNC_LOCK.sha256,
                ),
            )
        harness.parent = harness.parent_document(harness.parent["protocol_digest"])
        parent_data = canonical_json_bytes(harness.parent)
        harness.parent_path.write_bytes(parent_data)
        harness.parent_lock = _lock(parent_data)
        harness.run(page_size=4)
        return harness.output


def test_genuine_complete_synthetic_baseline_preserves_every_inherited_artifact(complete_baseline):
    result = _load(complete_baseline)
    actual = {
        path.relative_to(complete_baseline).as_posix(): path.read_bytes()
        for path in complete_baseline.rglob("*")
        if path.is_file()
    }
    assert {item.relative_path for item in result.artifact_bindings} == set(actual)
    assert result.receipt.artifact_count == len(actual)
    assert result.receipt.feature_count > 16
    assert result.receipt.metadata_locks_authenticate_issuer is False
    assert result.receipt.baseline_selects_genes_by_outcome is False
    for binding in result.artifact_bindings:
        assert binding.bytes == len(actual[binding.relative_path])
        assert (
            binding.sha256 == "sha256:" + hashlib.sha256(actual[binding.relative_path]).hexdigest()
        )
        result.assert_artifact(binding.relative_path, actual[binding.relative_path])
    result.verify_source_phase(complete_baseline)
    result.verify_complete_output(complete_baseline)
    assert (
        result.numerical_protocol_digest == json.loads(actual["protocol.json"])["protocol_digest"]
    )
    assert result.receipt.artifact_inventory_digest == sha256_digest(
        tuple(asdict(item) for item in result.artifact_bindings)
    )


@pytest.fixture
def mutable_baseline(complete_baseline, tmp_path):
    target = tmp_path / "copied-census"
    shutil.copytree(complete_baseline, target)
    return target


def _document(directory, name):
    return json.loads((directory / name).read_bytes())


def _write(directory, name, document, digest=None):
    if digest is not None:
        document[digest] = sha256_digest(
            {key: value for key, value in document.items() if key != digest}
        )
    (directory / name).write_bytes(canonical_json_bytes(document))


def _source_document_change(directory, mutate):
    source = _document(directory, "source-catalog.json")
    mutate(source)
    source["catalog_digest"] = sha256_digest(source["source_catalog"])
    _write(directory, "source-catalog.json", source, "source_document_digest")
    checks = _document(directory, "source-checks.json")
    checks["source_document_digest"] = source["source_document_digest"]
    _write(directory, "source-checks.json", checks, "checks_digest")
    external = _document(directory, "external-coverage.json")
    external["source_document_digest"] = source["source_document_digest"]
    _write(directory, "external-coverage.json", external, "external_document_digest")
    report = _document(directory, "evaluation.json")
    report["source_document_digest"] = source["source_document_digest"]
    report["external_document_digest"] = external["external_document_digest"]
    _write(directory, "evaluation.json", report, "report_digest")


def test_baseline_authority_is_immutable_nonpickle_and_returns_defensive_documents(
    complete_baseline,
):
    result = _load(complete_baseline)
    protocol = result.protocol_document()
    protocol["feature_space_protocol"]["source_input_protocol"]["input_bindings"][
        "source_choices"
    ] = "changed"
    report = result.report_document()
    report["source_accepted_genes"] = -1
    assert result.protocol_document() == _document(complete_baseline, "protocol.json")
    assert result.report_document() == _document(complete_baseline, "evaluation.json")
    with pytest.raises(AttributeError, match="immutable"):
        result._bindings = ()
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)
    with pytest.raises(TypeError):
        asdict(result)
    assert "_predictors" not in repr(result)
    assert "source_accepted" not in repr(result)


@pytest.mark.parametrize(
    "defect", ["changed", "truncated", "bytearray", "foreign", "wrong_name_type"]
)
def test_exact_artifact_assertions_reject_mismatch_and_foreign_names(complete_baseline, defect):
    result = _load(complete_baseline)
    name = "evaluation.json"
    payload = (complete_baseline / name).read_bytes()
    if defect == "changed":
        payload = payload[:-1] + b"x"
    elif defect == "truncated":
        payload = payload[:-1]
    elif defect == "bytearray":
        payload = bytearray(payload)
    elif defect == "foreign":
        name = "synthetic-private-canary.private.json"
    else:
        name = None
    with pytest.raises(ExecutionBaselineError) as error:
        result.assert_artifact(name, payload)
    assert "synthetic-private-canary" not in str(error.value)


def test_source_gate_excludes_live_progress_and_requires_every_source_artifact(
    complete_baseline, mutable_baseline
):
    result = _load(complete_baseline)
    (mutable_baseline / "progress.json").write_bytes(b"synthetic live progress is not inspected")
    (mutable_baseline / "progress.json.tmp").write_bytes(b"synthetic pending progress")
    result.verify_source_phase(mutable_baseline)
    (mutable_baseline / "source-fit/pages/00000.json").unlink()
    with pytest.raises(ExecutionBaselineError, match="source phase"):
        result.verify_source_phase(mutable_baseline)


@pytest.mark.parametrize("name", ["evaluation.json", "external-score/pages/00000.json"])
def test_individual_file_checkpoint_uses_locked_bounded_snapshot(complete_baseline, name):
    _load(complete_baseline).verify_artifact_file(complete_baseline, name)


@pytest.mark.parametrize("name", [None, "../evaluation.json", "execution.json"])
def test_individual_file_checkpoint_rejects_foreign_names_before_access(
    complete_baseline, monkeypatch, name
):
    result = _load(complete_baseline)

    def forbidden(*_args, **_kwargs):
        pytest.fail("foreign checkpoint must not access the filesystem")

    monkeypatch.setattr(boundary, "_output_directory", forbidden)
    with pytest.raises(ExecutionBaselineError):
        result.verify_artifact_file(complete_baseline, name)


def test_individual_file_checkpoint_rejects_growing_page_before_open(
    complete_baseline, mutable_baseline, monkeypatch
):
    result = _load(complete_baseline)
    target = mutable_baseline / "external-score/pages/00000.json"
    with target.open("ab") as stream:
        stream.write(b" ")

    def forbidden(*_args, **_kwargs):
        pytest.fail("a page exceeding its locked size must not be opened")

    monkeypatch.setattr(boundary.os, "open", forbidden)
    with pytest.raises(ExecutionBaselineError):
        result.verify_artifact_file(mutable_baseline, "external-score/pages/00000.json")


def test_individual_file_checkpoint_rejects_same_size_tamper_and_missing_page(
    complete_baseline, mutable_baseline
):
    result = _load(complete_baseline)
    name = "external-score/pages/00000.json"
    path = mutable_baseline / name
    payload = path.read_bytes()
    path.write_bytes(payload[:-1] + b"x")
    with pytest.raises(ExecutionBaselineError):
        result.verify_artifact_file(mutable_baseline, name)
    path.unlink()
    with pytest.raises(ExecutionBaselineError):
        result.verify_artifact_file(mutable_baseline, name)


def test_individual_file_checkpoint_rejects_descriptor_replacement_race(
    complete_baseline, monkeypatch
):
    result = _load(complete_baseline)
    original = boundary.os.fstat

    def replaced(descriptor):
        metadata = original(descriptor)
        fields = list(metadata)
        fields[1] += 1
        return boundary.os.stat_result(fields)

    monkeypatch.setattr(boundary.os, "fstat", replaced)
    with pytest.raises(ExecutionBaselineError):
        result.verify_artifact_file(complete_baseline, "external-score/pages/00000.json")


def test_preseal_and_postseal_exact_execution_envelopes_are_additive(
    complete_baseline, mutable_baseline
):
    result = _load(complete_baseline)
    (mutable_baseline / EXECUTION_ARTIFACT_NAMES[0]).write_bytes(b"{}")
    result.verify_complete_output(
        mutable_baseline, allowed_extra_names=EXECUTION_ARTIFACT_NAMES[:1]
    )
    (mutable_baseline / EXECUTION_ARTIFACT_NAMES[1]).write_bytes(b"{}")
    result.verify_complete_output(mutable_baseline)
    with pytest.raises(ExecutionBaselineError, match="artifact tree"):
        result.verify_complete_output(
            mutable_baseline, allowed_extra_names=EXECUTION_ARTIFACT_NAMES[:1]
        )


@pytest.mark.parametrize(
    "names",
    [
        (),
        ("private.json",),
        ("execution.json",),
        ("execution-protocol.json", "execution-protocol.json"),
        ["execution-protocol.json"],
    ],
)
def test_execution_extra_name_scope_cannot_be_broadened(complete_baseline, names):
    with pytest.raises(ExecutionBaselineError, match="envelope"):
        _load(complete_baseline).verify_complete_output(
            complete_baseline, allowed_extra_names=names
        )


@pytest.mark.parametrize(
    "name",
    [
        "protocol.json",
        "source-catalog.json",
        "source-checks.json",
        "source-fit/pages/00000.json",
        "source-fit/source-census-manifest.json",
        "external-coverage.json",
        "external-score/pages/00000.json",
        "external-score/manifest.json",
        "evaluation.json",
        "summary.csv",
        "progress.json",
    ],
)
def test_complete_replay_rejects_any_changed_inherited_bytes(
    complete_baseline, mutable_baseline, name
):
    result = _load(complete_baseline)
    path = mutable_baseline / name
    payload = path.read_bytes()
    path.write_bytes(payload[:-1] + (b"x" if payload[-1:] != b"x" else b"y"))
    with pytest.raises(ExecutionBaselineError):
        result.verify_complete_output(mutable_baseline)


@pytest.mark.parametrize(
    "name",
    [
        "private.private.json",
        "source-fit/pages/99999.json",
        "external-score/pages/99999.json",
        "progress.json.tmp",
    ],
)
def test_extra_baseline_or_replay_files_are_rejected(complete_baseline, mutable_baseline, name):
    result = _load(complete_baseline)
    (mutable_baseline / name).write_bytes(b"{}")
    with pytest.raises(ExecutionBaselineError):
        result.verify_complete_output(mutable_baseline)
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    "name",
    [
        "../secret.json",
        "/protocol.json",
        "C:/protocol.json",
        "source-fit\\pages\\00000.json",
        "source-fit/pages/0.json",
        "source-fit/pages/00000.json/extra",
        "source-fit/pages/../00000.json",
        "source-fit/pages/00000.private.json",
        "execution.json",
        "protocol.json\n",
    ],
)
def test_artifact_contract_rejects_paths_outside_closed_inherited_namespace(name):
    with pytest.raises(ExecutionBaselineError):
        ArtifactBinding(name, 1, "sha256:" + "1" * 64)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bytes", True),
        ("bytes", 0),
        ("bytes", 2**30),
        ("sha256", "1" * 64),
        ("sha256", "sha256:" + "A" * 64),
        ("relative_path", None),
    ],
)
def test_artifact_contract_rejects_wrong_scalar_types_and_bounds(field, value):
    values = {"relative_path": "protocol.json", "bytes": 1, "sha256": "sha256:" + "1" * 64}
    values[field] = value
    with pytest.raises(ExecutionBaselineError):
        ArtifactBinding(**values)


@pytest.mark.parametrize("defect", ["hash", "size", "type", "bound"])
def test_runtime_protocol_lock_is_enforced_before_parsing(complete_baseline, defect):
    protocol = _lock((complete_baseline / "protocol.json").read_bytes())
    report = _lock((complete_baseline / "evaluation.json").read_bytes())
    if defect == "hash":
        protocol = replace(protocol, sha256="0" * 64)
    elif defect == "size":
        protocol = replace(protocol, bytes=protocol.bytes + 1)
    elif defect == "type":
        protocol = asdict(protocol)
    else:
        protocol = replace(protocol, bytes=boundary.MAX_BASELINE_DOCUMENT_BYTES + 1)
    with pytest.raises(ExecutionBaselineError):
        boundary.load_baseline_census(
            directory=complete_baseline, protocol_lock=protocol, evaluation_lock=report
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"[]",
        b"null",
        b'{"duplicate":1,"duplicate":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{ "space": 1 }',
    ],
)
def test_runtime_locked_documents_still_require_canonical_closed_json(mutable_baseline, payload):
    # Empty input is rejected by SourceLock; all other bytes are freshly locked
    # so failures establish parsing/schema checks independent of checksums.
    (mutable_baseline / "protocol.json").write_bytes(payload)
    with pytest.raises((ExecutionBaselineError, ValueError)):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "other/1.0.0"),
        ("workers", True),
        ("workers", 2),
        ("maximum_page_bytes", 1),
        ("fitting_magnitude_bound", 1e20),
        ("default_source_page_size", 0),
        ("default_source_page_size", 65),
        ("anchor_request_digest", "synthetic-private-canary"),
        ("nonanchor_request_digest", "synthetic-private-canary"),
        ("source_receipts_sealed_before_external_measurement_reads", False),
        ("private_predictors_persisted", True),
        ("hydration_refits_source_models", True),
    ],
)
def test_rehashed_protocol_cannot_change_frozen_policy(mutable_baseline, field, value):
    protocol = _document(mutable_baseline, "protocol.json")
    protocol[field] = value
    _write(mutable_baseline, "protocol.json", protocol, "protocol_digest")
    with pytest.raises(ExecutionBaselineError) as error:
        _load(mutable_baseline)
    assert "synthetic-private-canary" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "other/1.0.0"),
        ("all_genes_attempted", False),
        ("all_genes_retained", 1),
        ("source_accepted_genes", True),
        ("source_feature_count", 20_001),
        ("source_case_count", 59),
        ("external_case_count", 0),
        ("source_input_domain_rejected_genes", 20_000),
        ("default_promotion", True),
        ("association_tested", True),
        ("source_manifest_sealed_before_external_measurement_reads", False),
        ("redistribution_status", "public"),
    ],
)
def test_rehashed_report_cannot_change_completion_counts_or_scientific_scope(
    mutable_baseline, field, value
):
    report = _document(mutable_baseline, "evaluation.json")
    report[field] = value
    _write(mutable_baseline, "evaluation.json", report, "report_digest")
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


def _set_path(value, path, replacement):
    for name in path[:-1]:
        value = value[name]
    value[path[-1]] = replacement


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profile_id",), "foreign/1.0.0"),
        (("genes",), []),
        (("source_case_count",), True),
        (("measurement_matrix_bytes",), 0),
        (("availability_matrix_bytes",), 0),
        (("count_supported_genes",), 0),
        (("state_order",), []),
        (("assay_order",), []),
        (("variation_is_a_gate",), True),
        (("fit_eligibility_established",), True),
        (("selection_uses_external_values",), True),
        (("model_fits_performed",), True),
        (("genes", 0, "coverage", "observed_cnv"), True),
        (("genes", 0, "coverage", "observed_cnv"), 10_000),
        (("genes", 0, "coverage", "zero_cnv"), 10_000),
        (("genes", 0, "coverage", "candidate_specimens"), 0),
        (("genes", 0, "coverage", "protein_feature_present"), 1),
        (("genes", 0, "coverage", "cnv_state_counts"), [72]),
        (("genes", 0, "coverage", "cnv_state_counts"), [0.0, 0, 0, 0, 0, 0]),
        (("genes", 0, "coverage", "cnv_state_counts"), [0, 0, 0, 0, 0, 0]),
        (("genes", 0, "coverage", "pattern_counts_cnv_rna_protein"), [0] * 8),
        (("genes", 0, "coverage", "rna_protein_complete"), 10_000),
        (("genes", 0, "coverage", "identity", "hgnc_id"), "private-canary"),
        (("genes", 0, "coverage", "identity", "entrez_id"), 1),
        (("genes", 0, "count_capacity", "fold_joint_counts"), [0] * 5),
        (("genes", 0, "count_capacity", "fold_joint_counts"), [0] * 6),
        (("genes", 0, "count_capacity", "minimum_outer_training_joint"), 0),
        (("genes", 0, "count_capacity", "all_five_fold_count_support_possible"), 1),
        (("genes", 0, "training_variation", "training_contexts"), 25),
        (("genes", 0, "training_variation", "cnv_contexts_with_variation"), 27),
    ],
)
def test_rehashed_source_catalog_cannot_invent_coverage_capacity_or_identity(
    mutable_baseline, path, value
):
    _source_document_change(
        mutable_baseline, lambda document: _set_path(document["source_catalog"], path, value)
    )
    with pytest.raises(ExecutionBaselineError) as error:
        _load(mutable_baseline)
    assert "private-canary" not in str(error.value)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profile_id",), "foreign/1.0.0"),
        (("candidate_specimens",), 1),
        (("verified_rna_files",), 0),
        (("protein_rows_outside_source_axis",), -1),
        (("source_protein_receipt", "profile_id"), "foreign/1.0.0"),
        (("source_protein_receipt", "candidate_count"), 0),
        (("source_protein_receipt", "biological_feature_rows"), 0),
        (("source_protein_receipt", "protein_sha256"), "sha256:" + "1" * 64),
        (("source_protein_receipt", "sample_map_sha256"), "1" * 64),
        (("source_protein_receipt", "finite_unshared_cells"), 0),
        (("source_protein_receipt", "finite_zero_unshared_cells"), 10_000_000),
        (("source_protein_receipt", "panel_coverage"), []),
        (("source_protein_receipt", "panel_coverage", 0, "source_rows"), 2),
        (("source_protein_receipt", "panel_coverage", 0, "unshared_finite"), None),
        (("schema_summaries",), []),
        (("schema_summaries", 0, "axis"), "protein"),
        (("schema_summaries", 0, "verified_input_bytes"), 0),
        (("schema_summaries", 0, "state_totals"), [0] * 6),
        (("schema_summaries", 0, "histograms"), []),
        (("schema_summaries", 0, "histograms", 0, "bins"), []),
        (("schema_summaries", 0, "histograms", 0, "bins", 0, "files"), 0),
    ],
)
def test_rehashed_cohort_receipt_requires_closed_source_and_schema_coherence(
    mutable_baseline, path, value
):
    _source_document_change(
        mutable_baseline, lambda document: _set_path(document["source_build_receipt"], path, value)
    )
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("feature_count", 0),
        ("approved_source_protein_genes", 0),
        ("literature_anchor_only_count", 0),
        ("source_protein_rows", 0),
        ("source_protein_receipt_digest", "sha256:" + "1" * 64),
        ("selection_uses_external_values", True),
    ],
)
def test_rehashed_source_universe_cannot_expand_or_reselect_axis(mutable_baseline, field, value):
    _source_document_change(
        mutable_baseline,
        lambda document: document["source_universe_receipt"].__setitem__(field, value),
    )
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("feature_count", True),
        ("source_case_count", 59),
        ("external_case_count", 0),
        ("source_page_count", 0),
        ("artifact_count", 0),
        ("metadata_locks_authenticate_issuer", True),
        ("baseline_selects_genes_by_outcome", True),
        ("numerical_profile_id", boundary.PROFILE_ID),
        ("profile_id", boundary.BASELINE_PROFILE_ID),
        ("numerical_protocol_digest", "1" * 64),
    ],
)
def test_frozen_baseline_receipt_rejects_type_scope_and_inventory_misrepresentation(
    complete_baseline, field, value
):
    with pytest.raises(ExecutionBaselineError):
        replace(_load(complete_baseline).receipt, **{field: value})


def test_output_directories_and_readonly_authority_require_public_loader(complete_baseline):
    result = _load(complete_baseline)
    with pytest.raises(ExecutionBaselineError):
        result.verify_complete_output(str(complete_baseline))
    with pytest.raises(ExecutionBaselineError):
        result.verify_source_phase(complete_baseline / "missing")
    with pytest.raises(ExecutionBaselineError):
        boundary.BaselineCensus(
            object(), bindings=(), protocol=b"{}", report=b"{}", receipt=result.receipt
        )


def test_leaf_reparse_or_link_is_rejected_before_locked_contents(monkeypatch, mutable_baseline):
    target = mutable_baseline / "protocol.json"
    original = Path.lstat

    def link(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK)
        return original(path, *args, **kwargs)

    protocol_lock = _lock(target.read_bytes())
    evaluation_lock = _lock((mutable_baseline / "evaluation.json").read_bytes())
    monkeypatch.setattr(Path, "lstat", link)
    with pytest.raises(ExecutionBaselineError):
        boundary.load_baseline_census(
            directory=mutable_baseline, protocol_lock=protocol_lock, evaluation_lock=evaluation_lock
        )


def _external_manifest_change(directory, mutate):
    manifest = _document(directory, "external-score/manifest.json")
    mutate(manifest)
    _write(directory, "external-score/manifest.json", manifest, "manifest_digest")
    report = _document(directory, "evaluation.json")
    report["external_manifest_digest"] = manifest["manifest_digest"]
    _write(directory, "evaluation.json", report, "report_digest")


def _external_page_change(directory, mutate, *, accepted_result=False):
    manifest = _document(directory, "external-score/manifest.json")
    for binding in manifest["pages"]:
        page = _document(directory, binding["file_name"])
        records = [
            record
            for record in page["genes"]
            if not accepted_result
            or (record["result"] is not None and record["result"]["accepted"])
        ]
        if records:
            mutate(page, records[0])
            _write(directory, binding["file_name"], page, "page_digest")
            payload = (directory / binding["file_name"]).read_bytes()
            binding.update(
                bytes=len(payload),
                sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                page_digest=page["page_digest"],
            )
            _external_manifest_change(
                directory, lambda document: document.__setitem__("pages", manifest["pages"])
            )
            return
    pytest.fail("the genuine synthetic fixture must contain an accepted external result")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profile_id",), "foreign/1.0.0"),
        (("complete",), False),
        (("total_genes",), True),
        (("all_sixteen_original_results_replayed",), False),
        (("pages",), []),
        (("pages", 0, "file_name"), "external-score/pages/00001.json"),
        (("pages", 0, "page_number"), 1),
        (("pages", 0, "page_digest"), "sha256:" + "1" * 64),
        (("pages", 0, "first_hgnc_id"), "HGNC:999999"),
        (("pages", 0, "last_hgnc_id"), "HGNC:999999"),
        (("pages", 0, "gene_count"), 1),
        (("stage_counts", "external_result_accepted"), 0),
    ],
)
def test_resealed_external_manifest_requires_exact_order_bindings_and_conserved_counts(
    mutable_baseline, path, value
):
    _external_manifest_change(mutable_baseline, lambda manifest: _set_path(manifest, path, value))
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profile_id",), "foreign/1.0.0"),
        (("page_number",), 1),
        (("genes",), []),
        (("feature_axis_digest",), "sha256:" + "1" * 64),
        (("redistribution_status",), "public"),
    ],
)
def test_resealed_external_pages_preserve_axis_context_and_partition(mutable_baseline, path, value):
    _external_page_change(mutable_baseline, lambda page, _record: _set_path(page, path, value))
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_record_digest", "sha256:" + "1" * 64),
        ("source_accepted", None),
        ("external_complete_count", 0),
        ("external_evaluator_attempted", False),
        ("external_input_domain_rejection", "synthetic-private-canary"),
        ("point_scores_available", False),
        ("conditional_intervals_available", False),
    ],
)
def test_resealed_external_records_cannot_relabel_support_or_source_provenance(
    mutable_baseline, field, value
):
    _external_page_change(
        mutable_baseline,
        lambda _page, record: record.__setitem__(field, value),
        accepted_result=True,
    )
    with pytest.raises(ExecutionBaselineError) as error:
        _load(mutable_baseline)
    assert "synthetic-private-canary" not in str(error.value)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profile_id",), "foreign/1.0.0"),
        (("request_digest",), "sha256:" + "1" * 64),
        (("clinical_validation",), True),
        (("point_metrics", 0, "candidate"), "full"),
        (("point_metrics", 0, "observed_count"), 1),
        (("point_metrics", 0, "mae"), -1.0),
        (("accepted",), False),
        (("uncertainty", "seed"), 0),
        (("uncertainty", "replicates_requested"), 127),
        (("uncertainty", "replicates_successful"), 102),
        (("uncertainty", "training_refitted"), True),
        (("uncertainty", "metrics", 0, "candidate"), "full"),
        (("uncertainty", "primary_full_minus_cnv_mae", "confidence_level"), 0.95),
        (("uncertainty", "primary_full_minus_cnv_mae", "replicates"), 102),
        (("uncertainty", "primary_full_minus_cnv_mae", "lower"), 1e12),
    ],
)
def test_resealed_external_results_preserve_numerical_request_and_conditional_interval_contract(
    mutable_baseline, path, value
):
    _external_page_change(
        mutable_baseline,
        lambda _page, record: _set_path(record["result"], path, value),
        accepted_result=True,
    )
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("training_candidates", 1),
        ("test_candidates", 1),
        ("checked_identifier_namespaces", []),
        ("case_submitter_overlaps", 1),
        ("sample_submitter_overlaps", 1),
        ("gdc_sample_uuid_overlaps", 1),
        ("protein_aliquot_submitter_overlaps", 1),
        ("protein_aliquot_uuid_overlaps", 1),
        ("assay_file_overlaps", 1),
        ("donor_independence_admitted", True),
    ],
)
def test_resealed_report_requires_cohort_separation_scope_and_population_counts(
    mutable_baseline, field, value
):
    report = _document(mutable_baseline, "evaluation.json")
    report["metadata_separation"][field] = value
    _write(mutable_baseline, "evaluation.json", report, "report_digest")
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)


def test_external_joint_capacity_count_is_conserved_across_the_source_axis(mutable_baseline):
    external = _document(mutable_baseline, "external-coverage.json")
    external["external_catalog"]["source_and_external_count_sufficient_genes"] += 1
    external["external_catalog_digest"] = sha256_digest(external["external_catalog"])
    _write(mutable_baseline, "external-coverage.json", external, "external_document_digest")
    report = _document(mutable_baseline, "evaluation.json")
    report["external_document_digest"] = external["external_document_digest"]
    _write(mutable_baseline, "evaluation.json", report, "report_digest")
    with pytest.raises(ExecutionBaselineError):
        _load(mutable_baseline)
