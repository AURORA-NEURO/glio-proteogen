"""Independent replay and privacy oracles using genuine selected-candidate fits.

The complete selection fixture deliberately assigns legal failure checkpoints
to the three nonselected candidates. Its selected candidate's eighteen original
checkpoints and every successful recovery refit use the unchanged default solver.
This tests exact replay, not comparative numerical superiority of that candidate.
"""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
import pickle
import runpy
import sys
from contextlib import contextmanager
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    DonorLabelAggregate,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    build_validation_split_plan,
)
from glio_proteogen.research.gbmap_development_reduction import (
    ValidationCheckpoint,
    ValidationRunManifest,
    reduce_completed_validation,
)
from glio_proteogen.research.gbmap_held_mixture_truth import (
    CallerOwnedMixtureContext,
    build_held_mixture_truth,
)
from glio_proteogen.research.gbmap_selected_fold_replay import (
    SelectedFoldReplayError,
    SelectedFoldReplayReceipt,
    SelectedFoldReplayResult,
)
from glio_proteogen.research.gbmap_selected_fold_replay import model as replay_model
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tests.tooling import test_preflight_gbmap_development_candidate as source_fixture
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import replay_gbmap_selected_fold as replay
from tools import run_gbmap_hierarchy_tasks as tasks

_REVIEWED = source_fixture._REVIEWED_SHA256
_FAILURE = "GBmap selected-fold recovery failed closed"


@dataclass(frozen=True)
class _State:
    extraction: GbmapExtractionResult
    preflight: preflight_driver.GbmapDevelopmentPreflightReceipt
    manifest: tasks.GbmapHierarchyRunManifest
    runtime: tuple[tasks._RuntimeTask, ...]
    checkpoints: tuple[tasks.GbmapHierarchyCheckpoint, ...]


def _controlled_failure(manifest, task):
    """Explicit protocol-abstention fixture, never an invented successful fit."""
    evaluation = tasks._evaluation_output(
        state="abstained", reason="hierarchy_fit_failed", fit=None
    )
    body = tasks._checkpoint_body(manifest, task.spec, evaluation)
    return tasks.GbmapHierarchyCheckpoint.model_validate(
        {**body, "checkpoint_digest": sha256_digest(body), "evaluation": evaluation}
    )


@lru_cache(maxsize=1)
def _numerical_state() -> _State:
    """Four whole and five within folds; only index0 has genuine fitted results."""
    original = source_fixture._extraction()
    old = original.reference
    studies = sorted({row.study_key for row in old.records})
    records = []
    for study_index, study in enumerate(studies):
        first_donor = next(row.donor_key for row in old.records if row.study_key == study)
        prototypes = tuple(row for row in old.records if row.donor_key == first_donor)
        for donor_index in range(5):
            donor = f"synthetic-replay-{study_index}-{donor_index}"
            records.extend(replace(row, donor_key=donor) for row in prototypes)
    # This raw row is below both reference floors. It must survive held truth.
    counts = np.zeros(24, dtype=np.int64)
    counts[0], counts[12] = 9, 1
    records.append(
        DonorLabelAggregate(
            donor_key="synthetic-replay-0-0",
            study_key=studies[0],
            modeled_label="Neuron",
            source_labels=("Neuron",),
            cell_count=1,
            gene_counts=counts,
            detected_cell_counts=np.asarray(counts > 0, dtype=np.int32),
            total_umis=10,
        )
    )
    reference = replace(old, records=tuple(records))
    fields = original.receipt.model_dump(exclude={"receipt_digest"})
    fields["record_count"] = len(records)
    receipt = GbmapExtractionReceipt.model_validate(
        {**fields, "receipt_digest": sha256_digest(fields)}
    )
    extraction = GbmapExtractionResult(reference=reference, receipt=receipt)
    plan = build_validation_split_plan(reference)
    preflight = preflight_driver._build_receipt(extraction, plan, _REVIEWED)
    manifest, runtime = tasks._build_manifest_and_tasks(extraction, plan, preflight)
    checkpoints = tuple(
        tasks._execute_task(manifest, task)
        if task.spec.shrinkage_index == 0
        else _controlled_failure(manifest, task)
        for task in runtime
    )
    assert len(plan.folds) == 9
    assert all(fold.evaluable for fold in plan.folds)
    selected = [row for row in checkpoints if row.shrinkage_index == 0]
    assert len(selected) == 18
    assert all(row.evaluation.state == "evaluated" for row in selected)
    return _State(extraction, preflight, manifest, runtime, checkpoints)


@pytest.fixture(scope="module")
def numerical_state() -> _State:
    return _numerical_state()


def _write_inputs(tmp_path, monkeypatch, state):
    source = tmp_path / "source" / "scarches_core_GBmap.h5ad"
    source.parent.mkdir()
    source.write_bytes(b"synthetic source boundary; the test replaces extraction only")
    preflight = tmp_path / "preflight.json"
    preflight.write_bytes(preflight_driver.canonical_preflight_receipt_bytes(state.preflight))
    run = tmp_path / "run"
    checkpoint_directory = run / tasks.CHECKPOINT_DIRECTORY_NAME
    checkpoint_directory.mkdir(parents=True)
    (run / tasks.MANIFEST_NAME).write_bytes(tasks.canonical_manifest_bytes(state.manifest))
    for checkpoint in state.checkpoints:
        (checkpoint_directory / tasks._checkpoint_filename(checkpoint)).write_bytes(
            tasks.canonical_checkpoint_bytes(checkpoint)
        )
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: state.extraction
    )
    return source, preflight, run


def _recover(inputs, *, fold_id="whole-study-0001", **overrides):
    options = {
        "fold_id": fold_id,
        "development_only_acknowledged": True,
        "sha256_independently_reviewed": True,
        **overrides,
    }
    return replay.recover_selected_fold_context(
        inputs[0], _REVIEWED, inputs[1], inputs[2], **options
    )


def _inventory(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _no_fit(monkeypatch):
    calls = []

    def unexpected(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("a rejected replay must not refit")

    monkeypatch.setattr(replay, "_fit_label", unexpected)
    return calls


def _replace_checkpoint(run, old, new):
    directory = run / tasks.CHECKPOINT_DIRECTORY_NAME
    (directory / tasks._checkpoint_filename(old)).unlink()
    (directory / tasks._checkpoint_filename(new)).write_bytes(tasks.canonical_checkpoint_bytes(new))


def _resealed_evaluation(checkpoint, **changes):
    body = checkpoint.model_dump(mode="json", exclude={"checkpoint_digest"})
    evaluation = body["evaluation"]
    evaluation.update(changes)
    evaluation_body = {k: v for k, v in evaluation.items() if k != "evaluation_output_digest"}
    evaluation["evaluation_output_digest"] = sha256_digest(
        {"schema": tasks.EVALUATION_OUTPUT_SCHEMA, **evaluation_body}
    )
    return tasks.GbmapHierarchyCheckpoint.model_validate(
        {**body, "checkpoint_digest": sha256_digest(body)}
    )


def test_fixture_has_complete_gate_inventory_and_only_genuine_selected_successes(numerical_state):
    state = numerical_state
    selection = reduce_completed_validation(
        ValidationRunManifest.model_validate(state.manifest.model_dump(mode="python")),
        tuple(
            ValidationCheckpoint.model_validate(row.model_dump(mode="python"))
            for row in state.checkpoints
        ),
    )
    assert selection.selected_shrinkage_index == 0
    assert selection.selected_shrinkage == 0.1
    assert (
        sum(
            row.kind == "whole_study" and row.state == "evaluated"
            for row in selection.candidates[0].folds
        )
        == 4
    )
    assert (
        sum(
            row.kind == "within_study_donor" and row.state == "evaluated"
            for row in selection.candidates[0].folds
        )
        == 5
    )
    for checkpoint in state.checkpoints:
        if checkpoint.shrinkage_index == 0:
            assert checkpoint.evaluation.hierarchy_fit_digest is not None
            assert checkpoint.evaluation.hierarchy_trace_digest is not None
            assert checkpoint.evaluation.hierarchy_converged is True
        else:
            assert checkpoint.evaluation.abstention_reason == "hierarchy_fit_failed"
            assert checkpoint.evaluation.hierarchy_fit_digest is None
            assert checkpoint.evaluation.mean_per_count_nll is None


@pytest.mark.parametrize("fold_id", ["whole-study-0001", "within-study-donor-0001"])
def test_success_exactly_k_real_default_refits_and_no_saved_or_source_changes(
    tmp_path, monkeypatch, numerical_state, fold_id
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    before = _inventory(tmp_path)
    extracted = []
    fitted = []
    original_fit = replay._fit_label

    def extract(*_args, **_kwargs):
        extracted.append(True)
        return numerical_state.extraction

    def fit(*args, **kwargs):
        assert kwargs["configuration"] is DEFAULT_TRAINING_CONFIGURATION.hierarchy
        assert kwargs["shrinkage"] == 0.1
        value = original_fit(*args, **kwargs)
        fitted.append((args, kwargs, value))
        return value

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", extract)
    monkeypatch.setattr(replay, "_fit_label", fit)
    result = _recover(inputs, fold_id=fold_id)
    assert extracted == [True]
    assert len(fitted) == result.receipt.replayed_checkpoint_count == len(result.known_labels) == 2
    assert tuple(kwargs["label"] for _, kwargs, _ in fitted) == result.known_labels
    assert result.known_labels == ("MES-like", "NPC-like")
    assert result.receipt.manifest_digest == numerical_state.manifest.manifest_digest
    assert result.receipt.feature_order_digest == numerical_state.manifest.feature_order_digest
    assert result.receipt.selected_feature_axis_digest == sha256_digest(
        {
            "schema": "gbmap-selected-feature-axis/1.0.0",
            "feature_order_digest": result.receipt.feature_order_digest,
            "feature_indices": list(result.feature_indices),
        }
    )
    expected = next(
        task.prepared for task in numerical_state.runtime if task.spec.fold_id == fold_id
    )
    assert result.feature_indices == expected.feature_indices
    assert all(row not in expected.held_records for args, _, _ in fitted for row in args[0])
    for index, (_, _, value) in enumerate(fitted):
        np.testing.assert_array_equal(result.signatures[:, index], value.global_signature)
    np.testing.assert_array_equal(result.background, expected.background)
    assert result.hierarchy_concentrations == tuple(value.concentration for _, _, value in fitted)
    np.testing.assert_allclose(np.sum(result.signatures, axis=0), (1.0, 1.0), rtol=0, atol=1e-12)
    assert all(value > 0 for value in result.hierarchy_concentrations)
    assert _inventory(tmp_path) == before


def test_held_truth_keeps_below_floor_counts_and_uses_all_raw_rows(
    tmp_path, monkeypatch, numerical_state
):
    result = _recover(_write_inputs(tmp_path, monkeypatch, numerical_state))
    receipt = result.held_truth.receipt
    assert receipt.held_raw_record_count == 11
    assert receipt.held_reference_eligible_record_count == 10
    neuron = next(row for row in receipt.labels if row.modeled_label == "Neuron")
    assert neuron.held_record_count == 1
    assert neuron.held_reference_eligible_record_count == 0
    case = next(case for case in result.held_truth.cases if case.source_total_count_mass == 40_010)
    view = case.reclassify()
    assert view.source_unknown_count_mass == 10
    assert view.source_unknown_fraction == Fraction(1, 4001)
    assert view.selected_counts is case.selected_counts
    omitted = case.reclassify(("MES-like",))
    assert omitted.source_unknown_count_mass == 20_010
    np.testing.assert_array_equal(omitted.selected_counts, case.selected_counts)


@pytest.mark.parametrize(
    "problem",
    [
        "manifest_missing",
        "checkpoint_missing",
        "extra_entry",
        "duplicate_checkpoint",
        "bad_filename",
        "noncanonical",
        "bad_digest",
    ],
)
def test_incomplete_or_tampered_inventory_is_rejected_before_extraction_and_refits(
    tmp_path, monkeypatch, numerical_state, problem
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    run = inputs[2]
    checkpoint = next((run / tasks.CHECKPOINT_DIRECTORY_NAME).iterdir())
    if problem == "manifest_missing":
        (run / tasks.MANIFEST_NAME).unlink()
    elif problem == "checkpoint_missing":
        checkpoint.unlink()
    elif problem == "extra_entry":
        (checkpoint.parent / "unexpected.json").write_bytes(b"{}")
    elif problem == "duplicate_checkpoint":
        (checkpoint.parent / ("b" * 64 + "." + "c" * 64 + ".json")).write_bytes(
            checkpoint.read_bytes()
        )
    elif problem == "bad_filename":
        checkpoint.rename(checkpoint.with_name("d" * 64 + "." + "e" * 64 + ".json"))
    elif problem == "noncanonical":
        checkpoint.write_bytes(json.dumps(json.loads(checkpoint.read_bytes()), indent=2).encode())
    else:
        document = json.loads(checkpoint.read_bytes())
        document["checkpoint_digest"] = "sha256:" + "f" * 64
        checkpoint.write_bytes(canonical_json_bytes(document) + b"\n")
    extracted = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: extracted.append(True)
    )
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert extracted == calls == []


@pytest.mark.parametrize("part", ["run", "checkpoints"])
def test_missing_run_directories_are_never_recreated(tmp_path, monkeypatch, numerical_state, part):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    target = inputs[2] if part == "run" else inputs[2] / tasks.CHECKPOINT_DIRECTORY_NAME
    for path in sorted(target.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    target.rmdir()
    mkdir_calls = []

    def no_mkdir(*_a, **_kw):
        mkdir_calls.append(True)
        raise AssertionError("read-only recovery cannot create directories")

    monkeypatch.setattr(Path, "mkdir", no_mkdir)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert mkdir_calls == []
    assert not target.exists()


@pytest.mark.parametrize(
    "fold_id",
    ["", "whole-study-1", "whole-study-0000/../0001", "within-study-donor-0001\n", 1, True],
)
def test_fold_identifier_is_exact_and_checked_before_extraction(
    tmp_path, monkeypatch, numerical_state, fold_id
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    called = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: called.append(True)
    )
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs, fold_id=fold_id)
    assert called == []


@pytest.mark.parametrize(
    "field", ["development_only_acknowledged", "sha256_independently_reviewed"]
)
@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_acknowledgements_are_exact_before_any_source_extraction(
    tmp_path, monkeypatch, numerical_state, field, value
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    called = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: called.append(True)
    )
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs, **{field: value})
    assert called == []


def test_preflight_reviewed_digest_mismatch_is_rejected_before_source(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    fields = numerical_state.preflight.model_dump(mode="json", exclude={"receipt_digest"})
    fields["reviewed_sha256"] = "sha256:" + "b" * 64
    inputs[1].write_bytes(
        canonical_json_bytes({**fields, "receipt_digest": sha256_digest(fields)}) + b"\n"
    )
    called = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: called.append(True)
    )
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert called == []


def test_no_candidate_is_not_replaced_by_a_convenient_default(
    tmp_path, monkeypatch, numerical_state
):
    state = replace(
        numerical_state,
        checkpoints=tuple(
            _controlled_failure(numerical_state.manifest, task) for task in numerical_state.runtime
        ),
    )
    inputs = _write_inputs(tmp_path, monkeypatch, state)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_selected_candidate_can_remain_selected_but_requested_abstained_fold_is_rejected(
    tmp_path, monkeypatch, numerical_state
):
    task = next(
        task
        for task in numerical_state.runtime
        if task.spec.fold_id == "whole-study-0001" and task.spec.shrinkage_index == 0
    )
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    old = next(
        row for row in numerical_state.checkpoints if row.task_digest == task.spec.task_digest
    )
    _replace_checkpoint(inputs[2], old, _controlled_failure(numerical_state.manifest, task))
    # The other three whole-study folds and five within-study folds still pass.
    selection = replay._complete_selection(replay._snapshot_run(inputs[2]))
    assert selection.selected_shrinkage_index == 0
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hierarchy_fit_digest", "sha256:" + "b" * 64),
        ("hierarchy_trace_digest", "sha256:" + "c" * 64),
        ("mean_per_count_nll", 0.123),
    ],
)
def test_resealed_saved_numerical_evidence_must_match_real_reproduction(
    tmp_path, monkeypatch, numerical_state, field, value
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    checkpoint = next(
        row
        for row in numerical_state.checkpoints
        if row.fold_id == "whole-study-0001" and row.shrinkage_index == 0
    )
    forged = _resealed_evaluation(checkpoint, **{field: value})
    _replace_checkpoint(inputs[2], checkpoint, forged)
    fitted = []
    original = replay._fit_label

    def fit(*args, **kwargs):
        fitted.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(replay, "_fit_label", fit)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert fitted == [True]


def test_trace_verification_failure_does_not_return_partial_parameters(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    calls = []
    original = replay._fit_label

    def fit(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(replay, "_fit_label", fit)
    monkeypatch.setattr(replay, "verify_hierarchy_trace", lambda _fit: False)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == [True]


def test_run_mutation_during_extraction_is_detected_before_any_refit(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)

    def extract(*_a, **_kw):
        next((inputs[2] / tasks.CHECKPOINT_DIRECTORY_NAME).iterdir()).unlink()
        return numerical_state.extraction

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", extract)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_source_mutation_during_extraction_is_rejected_before_refit(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)

    def extract(*_a, **_kw):
        inputs[0].write_bytes(b"the synthetic source identity changed")
        return numerical_state.extraction

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", extract)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_manifest_source_replay_mismatch_is_rejected_without_fitting(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    original = numerical_state.extraction
    changed = replace(original.reference, records=original.reference.records[:-1])
    monkeypatch.setattr(
        replay,
        "extract_pinned_gbmap_reference",
        lambda *_a, **_kw: replace(original, reference=changed),
    )
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


@pytest.mark.parametrize(
    "error",
    [ValueError("synthetic-private-path-and-donor"), OSError("synthetic-private-path-and-donor")],
)
def test_private_internal_errors_have_no_message_or_exception_context(
    tmp_path, monkeypatch, numerical_state, error
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)

    def fail(*_a, **_kw):
        raise error

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", fail)
    with pytest.raises(SelectedFoldReplayError) as caught:
        _recover(inputs)
    assert str(caught.value) == _FAILURE
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert "synthetic-private" not in repr(caught.value)


def test_cancellation_is_not_converted_to_an_ordinary_replay_failure(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    cancellation = InferenceCancelledError("synthetic cooperative cancellation")

    def cancel(*_a, **_kw):
        raise cancellation

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", cancel)
    with pytest.raises(InferenceCancelledError) as caught:
        _recover(inputs)
    assert caught.value is cancellation


@lru_cache(maxsize=1)
def _private_wrapper_inputs():
    """Only wrapper contracts: caller construction does not authenticate a fit."""
    state = _numerical_state()
    task = state.runtime[0]
    prepared = task.prepared
    truth = build_held_mixture_truth(
        state.extraction.reference,
        build_validation_split_plan(state.extraction.reference),
        fold_id=task.spec.fold_id,
        context=CallerOwnedMixtureContext(
            feature_indices=prepared.feature_indices,
            known_labels=prepared.labels,
            feature_order_digest=state.manifest.feature_order_digest,
        ),
    )
    receipt = SelectedFoldReplayReceipt(
        fold_id=task.spec.fold_id,
        kind=task.spec.kind,
        selected_shrinkage_index=0,
        selected_shrinkage=0.1,
        selected_feature_count=len(prepared.feature_indices),
        known_labels=prepared.labels,
        manifest_digest=state.manifest.manifest_digest,
        selection_receipt_digest="sha256:" + "1" * 64,
        checkpoint_set_digest="sha256:" + "2" * 64,
        reviewed_sha256=_REVIEWED,
        feature_order_digest=state.manifest.feature_order_digest,
        selected_feature_axis_digest=task.spec.selected_feature_axis_digest,
        profile_digest=state.manifest.profile_digest,
        engine_semantic_digest=state.manifest.engine_semantic_digest,
        training_configuration_digest=state.manifest.training_configuration_digest,
        replayed_checkpoint_count=len(prepared.labels),
        held_truth=truth.receipt,
    )
    return {
        "receipt": receipt,
        "feature_indices": prepared.feature_indices,
        "signatures": np.full(
            (len(prepared.feature_indices), 2), 1 / len(prepared.feature_indices)
        ),
        "background": prepared.background,
        "hierarchy_concentrations": (12.0, 24.0),
        "held_truth": truth,
    }


def test_private_wrapper_snapshots_arrays_and_blocks_serialization_and_mutation():
    arguments = _private_wrapper_inputs().copy()
    signatures = arguments["signatures"].copy()
    background = arguments["background"].copy()
    arguments.update(signatures=signatures, background=background)
    result = replay_model._build_result(**arguments)
    signatures[:] = 0
    background[:] = 0
    assert np.all(result.signatures > 0)
    assert np.all(result.background > 0)
    assert "private reproduced fold context" in repr(result)
    assert "synthetic-replay" not in repr(result)
    for array in (result.signatures, result.background):
        with pytest.raises(ValueError, match="WRITEABLE"):
            array.setflags(write=True)
    with pytest.raises(AttributeError):
        result._receipt = arguments["receipt"]
    with pytest.raises(AttributeError):
        del result._background
    for operation in (
        pickle.dumps,
        json.dumps,
        lambda value: value.__getstate__(),
        lambda value: value.__reduce__(),
    ):
        with pytest.raises(TypeError):
            operation(result)
    with pytest.raises(TypeError):
        SelectedFoldReplayResult()


def test_selected_axis_permutation_is_not_accepted_by_matching_cardinality():
    arguments = _private_wrapper_inputs().copy()
    arguments["feature_indices"] = tuple(reversed(arguments["feature_indices"]))
    with pytest.raises(SelectedFoldReplayError, match="declared axes"):
        replay_model._build_result(**arguments)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hierarchy_concentrations", (True, 2.0)),
        ("hierarchy_concentrations", (0.0, 2.0)),
        ("hierarchy_concentrations", (float("nan"), 2.0)),
        ("hierarchy_concentrations", (2.0,)),
        ("feature_indices", (0, 0)),
        ("feature_indices", [0, 1]),
        ("feature_indices", (True, 1)),
    ],
)
def test_private_axes_and_concentrations_are_strict(field, value):
    arguments = _private_wrapper_inputs().copy()
    arguments[field] = value
    with pytest.raises(SelectedFoldReplayError):
        replay_model._build_result(**arguments)


@pytest.mark.parametrize(
    "kind", ["masked", "boolean", "wrong_shape", "zero", "negative", "nan", "not_simplex"]
)
def test_private_probabilities_cannot_discard_coordinates_or_change_simplex(kind):
    arguments = _private_wrapper_inputs().copy()
    values = arguments["signatures"].copy()
    if kind == "masked":
        values = np.ma.array(values, mask=False)
    elif kind == "boolean":
        values = values.astype(bool)
    elif kind == "wrong_shape":
        values = values[:-1]
    elif kind == "zero":
        values[0, 0] = 0
    elif kind == "negative":
        values[0, 0] = -0.1
    elif kind == "nan":
        values[0, 0] = float("nan")
    else:
        values[:, 0] *= 2
    arguments["signatures"] = values
    with pytest.raises(SelectedFoldReplayError):
        replay_model._build_result(**arguments)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_shrinkage", 1),
        ("selected_shrinkage", 1.0),
        ("replayed_checkpoint_count", True),
        ("replayed_checkpoint_count", 3),
        ("kind", "within_study_donor"),
        ("known_labels", ("NPC-like", "MES-like")),
        ("known_labels", ("MES-like", "synthetic-private-label")),
        ("selected_feature_count", 2),
        ("production_artifact_permitted", 0),
        ("production_artifact_permitted", True),
        ("mixture_accuracy_established", 0),
        ("unbiased_performance_established", True),
    ],
)
def test_receipt_cannot_claim_a_different_fold_axis_or_broader_admission(field, value):
    document = _private_wrapper_inputs()["receipt"].model_dump(mode="python")
    document[field] = value
    with pytest.raises(ValidationError):
        SelectedFoldReplayReceipt.model_validate(document)


def test_saved_receipt_is_closed_canonical_and_contains_no_private_arrays():
    receipt = _private_wrapper_inputs()["receipt"]
    payload = replay.canonical_receipt_bytes(receipt)
    assert payload == canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n"
    assert SelectedFoldReplayReceipt.model_validate_json(payload) == receipt
    document = json.loads(payload)
    for forbidden in (
        "signatures",
        "background",
        "hierarchy_concentrations",
        "feature_indices",
        "cases",
        "selected_counts",
        "source_total_count_mass",
        "synthetic-replay",
        "study_keys",
        "source_path",
    ):
        assert forbidden.encode() not in payload
    document["signatures"] = [[0.5, 0.5]]
    with pytest.raises(ValidationError):
        SelectedFoldReplayReceipt.model_validate_json(json.dumps(document))


def test_cli_success_prints_receipt_only_and_sanitizes_failures(monkeypatch, capsys):
    result = replay_model._build_result(**_private_wrapper_inputs())
    monkeypatch.setattr(replay, "recover_selected_fold_context", lambda *_a, **_kw: result)
    arguments = [
        "synthetic.h5ad",
        "--reviewed-sha256",
        _REVIEWED,
        "--preflight",
        "synthetic-preflight.json",
        "--run-directory",
        "synthetic-run",
        "--fold-id",
        "whole-study-0001",
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
    ]
    assert replay.main(arguments) == 0
    captured = capsys.readouterr()
    assert captured.out.encode() == replay.canonical_receipt_bytes(result.receipt)
    assert captured.err == ""

    def fail(*_a, **_kw):
        raise ValueError("synthetic-private-path")

    monkeypatch.setattr(replay, "recover_selected_fold_context", fail)
    assert replay.main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap selected-fold replay failed closed\n"


def test_cli_usage_does_not_echo_a_private_token(capsys):
    with pytest.raises(SystemExit) as caught:
        replay.main(["synthetic-private-path", "--unknown-private-token"])
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-token" not in captured.err


@pytest.mark.parametrize("directory", ["text", "repository", "ordinary_file", "reparse"])
def test_run_directory_type_containment_and_ancestor_guards(
    tmp_path, monkeypatch, numerical_state, directory
):
    inputs = list(_write_inputs(tmp_path, monkeypatch, numerical_state))
    if directory == "text":
        inputs[2] = str(inputs[2])
    elif directory == "repository":
        inputs[2] = replay.fit_driver._REPOSITORY_ROOT
    elif directory == "ordinary_file":
        inputs[2] = inputs[2] / tasks.MANIFEST_NAME
    else:
        inode = inputs[2].stat().st_ino
        original = replay.fit_driver._is_link_or_reparse
        monkeypatch.setattr(
            replay.fit_driver,
            "_is_link_or_reparse",
            lambda info: info.st_ino == inode or original(info),
        )
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_directory_replacement_during_ancestor_identity_walk_is_rejected(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    target = inputs[2]
    original = Path.lstat
    inspections = []

    def lstat(path, *args, **kwargs):
        if path == target:
            inspections.append(True)
            if len(inspections) == 2:
                target.rename(tmp_path / "retained-original-run")
                target.mkdir()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert len(inspections) == 2
    assert (tmp_path / "retained-original-run" / tasks.MANIFEST_NAME).is_file()
    assert tuple(target.iterdir()) == ()


@pytest.mark.parametrize("part", ["run", "checkpoints"])
def test_directory_replacement_during_checkpoint_read_cannot_pass_the_snapshot(
    tmp_path, monkeypatch, numerical_state, part
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    target = inputs[2] if part == "run" else inputs[2] / tasks.CHECKPOINT_DIRECTORY_NAME
    original = replay._read_checkpoints

    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        target.rename(tmp_path / "retained-directory")
        target.mkdir()
        return result

    monkeypatch.setattr(replay, "_read_checkpoints", read)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []
    assert tuple(target.iterdir()) == ()


def test_raced_removed_checkpoint_directory_is_not_recreated(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    directory = inputs[2] / tasks.CHECKPOINT_DIRECTORY_NAME

    def extract(*_args, **_kwargs):
        directory.rename(tmp_path / "retained-checkpoints")
        return numerical_state.extraction

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", extract)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []
    assert not directory.exists()


@pytest.mark.parametrize("field", ["task_digest", "duplicate_task"])
def test_exact_sized_inventory_cannot_substitute_an_unknown_or_duplicate_task(
    tmp_path, monkeypatch, numerical_state, field
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    original = numerical_state.checkpoints[0]
    if field == "task_digest":
        body = original.model_dump(mode="json", exclude={"checkpoint_digest"})
        body["task_digest"] = "sha256:" + "f" * 64
        forged = tasks.GbmapHierarchyCheckpoint.model_validate(
            {**body, "checkpoint_digest": sha256_digest(body)}
        )
        _replace_checkpoint(inputs[2], original, forged)
    else:
        other = numerical_state.checkpoints[1]
        forged = _resealed_evaluation(original, mean_per_count_nll=0.456)
        _replace_checkpoint(inputs[2], other, forged)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_checkpoint_bytes_are_bounded_before_decoding(tmp_path, monkeypatch, numerical_state):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    monkeypatch.setattr(tasks, "MAX_CHECKPOINT_BYTES", 16)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_source_inside_the_run_is_rejected_without_extraction(
    tmp_path, monkeypatch, numerical_state
):
    inputs = list(_write_inputs(tmp_path, monkeypatch, numerical_state))
    inside = inputs[2] / "synthetic-source.h5ad"
    inside.write_bytes(inputs[0].read_bytes())
    inputs[0] = inside
    called = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: called.append(True)
    )
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert called == []


def test_valid_preflight_must_equal_the_caller_reviewed_digest(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    called = []
    monkeypatch.setattr(
        replay, "extract_pinned_gbmap_reference", lambda *_a, **_kw: called.append(True)
    )
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        replay.recover_selected_fold_context(
            inputs[0],
            "sha256:" + "b" * 64,
            inputs[1],
            inputs[2],
            fold_id="whole-study-0001",
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called == []


def test_resealed_manifest_and_all_checkpoints_still_require_actual_source_replay(
    tmp_path, monkeypatch, numerical_state
):
    fields = numerical_state.manifest.model_dump(mode="python", exclude={"manifest_digest"})
    fields["extraction_receipt_digest"] = "sha256:" + "b" * 64
    manifest = tasks.GbmapHierarchyRunManifest.model_validate(
        {**fields, "manifest_digest": sha256_digest(fields)}
    )
    checkpoints = []
    for row in numerical_state.checkpoints:
        fields = row.model_dump(mode="json", exclude={"checkpoint_digest"})
        fields["manifest_digest"] = manifest.manifest_digest
        checkpoints.append(
            tasks.GbmapHierarchyCheckpoint.model_validate(
                {**fields, "checkpoint_digest": sha256_digest(fields)}
            )
        )
    state = replace(numerical_state, manifest=manifest, checkpoints=tuple(checkpoints))
    inputs = _write_inputs(tmp_path, monkeypatch, state)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_valid_resealed_checkpoint_replacement_after_snapshot_is_also_a_mutation(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    original = numerical_state.checkpoints[0]
    changed = _resealed_evaluation(original, mean_per_count_nll=0.456)

    def extract(*_a, **_kw):
        _replace_checkpoint(inputs[2], original, changed)
        return numerical_state.extraction

    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", extract)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []


def test_source_guard_is_closed_after_a_private_extraction_failure(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    handles = []
    original_guard = replay.fit_driver._open_source_guard

    def guard(snapshot):
        handle = original_guard(snapshot)
        handles.append(handle)
        return handle

    def fail(*_args, **_kwargs):
        raise ValueError("synthetic-private-path")

    monkeypatch.setattr(replay.fit_driver, "_open_source_guard", guard)
    monkeypatch.setattr(replay, "extract_pinned_gbmap_reference", fail)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert len(handles) == 1
    assert handles[0].closed


@pytest.mark.parametrize("field", ["receipt", "held_truth"])
def test_private_builder_requires_the_exact_closed_evidence_types(field):
    arguments = _private_wrapper_inputs().copy()
    arguments[field] = {}
    with pytest.raises(SelectedFoldReplayError, match="internal evidence types"):
        replay_model._build_result(**arguments)


def test_cli_cooperative_cancellation_propagates(monkeypatch):
    def cancel(*_args, **_kwargs):
        raise InferenceCancelledError("synthetic cooperative cancellation")

    monkeypatch.setattr(replay, "recover_selected_fold_context", cancel)
    arguments = [
        "synthetic.h5ad",
        "--reviewed-sha256",
        _REVIEWED,
        "--preflight",
        "synthetic-preflight.json",
        "--run-directory",
        "synthetic-run",
        "--fold-id",
        "whole-study-0001",
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
    ]
    with pytest.raises(InferenceCancelledError):
        replay.main(arguments)


def test_direct_script_help_uses_the_real_entry_point_without_reading_inputs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["replay-gbmap-selected-fold", "--help"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(replay.__file__, run_name="__main__")
    assert caught.value.code == 0
    output = capsys.readouterr()
    assert "--fold-id" in output.out
    assert output.err == ""


def test_excess_checkpoint_inventory_stops_before_unbounded_directory_exhaustion(
    tmp_path, monkeypatch, numerical_state
):
    inputs = _write_inputs(tmp_path, monkeypatch, numerical_state)
    directory = inputs[2] / tasks.CHECKPOINT_DIRECTORY_NAME
    original = replay.os.scandir
    original_iterdir = Path.iterdir
    with original(directory) as scan:
        expected = tuple(scan)
    visited = []
    exhausted_unbounded_tail = []
    closed = []

    @contextmanager
    def entries(path):
        if path != directory:
            with original(path) as scan:
                yield scan
            return

        def bounded_oracle():
            for entry in expected:
                visited.append(entry)
                yield entry
            visited.append(SimpleNamespace(path=str(directory / "first-excess-entry.json")))
            yield visited[-1]
            exhausted_unbounded_tail.append(True)
            raise AssertionError("inventory reader exhausted an unbounded extra tail")

        try:
            yield bounded_oracle()
        finally:
            closed.append(True)

    def no_eager_iterdir(path):
        if path == directory:
            raise AssertionError("Python3.12 Path.iterdir allocates an eager os.listdir")
        return original_iterdir(path)

    monkeypatch.setattr(replay.os, "scandir", entries)
    monkeypatch.setattr(Path, "iterdir", no_eager_iterdir)
    calls = _no_fit(monkeypatch)
    with pytest.raises(SelectedFoldReplayError, match=_FAILURE):
        _recover(inputs)
    assert calls == []
    assert len(visited) == numerical_state.manifest.task_count + 1
    assert exhausted_unbounded_tail == []
    assert closed == [True]
