# ruff: noqa: TRY003
"""Synthetic execution controls and complete inherited numerical byte replay."""

from __future__ import annotations

import errno
import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_census_execution import baseline, progress
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.identity import HGNC_LOCK
from glio_proteogen.research.cptac_gbm_external_admission.protein import ProteinPanelCoverage
from tests.research import test_cptac_source_fit_census_runner as census_fixtures
from tests.research.test_cptac_source_fit_census_runner import (
    _census_cli_arguments,
    _external_records,
    _json,
    _manual_digest,
    _source_records,
)
from tools import evaluate_cptac_gbm_census_execution as runner
from tools import evaluate_cptac_gbm_source_fit_census as numerical


def _lock(path):
    payload = path.read_bytes()
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _files(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class _ExecutionHarness:
    def __init__(self, inherited):
        self.inherited = inherited
        self.directory = inherited.directory
        # The earlier admission stub omitted optional panel receipt rows. Real
        # readers always emit the complete panel, required by the closed loader.
        for name, admitted in inherited.proteins.items():
            provider = numerical.discovery_module if name == "source" else numerical.protein
            by_symbol = {
                identity.symbol: index
                for index, identity in enumerate(admitted.identities)
                if identity is not None
            }
            panel = []
            for symbol in PANEL:
                index = by_symbol.get(symbol)
                observed = (
                    int(np.isfinite(admitted.values[index]).sum()) if index is not None else None
                )
                cases = admitted.values.shape[1]
                panel.append(
                    ProteinPanelCoverage(
                        symbol,
                        int(index is not None),
                        observed,
                        cases - observed if observed is not None else None,
                        cases if index is not None else None,
                    )
                )
            inherited.proteins[name] = replace(
                admitted,
                receipt=replace(
                    admitted.receipt,
                    panel_coverage=tuple(panel),
                    protein_sha256=provider.PROTEIN_LOCK.sha256,
                    sample_map_sha256=provider.SAMPLE_MAP_LOCK.sha256,
                    hgnc_sha256=HGNC_LOCK.sha256,
                ),
            )
        inherited.parent = inherited.parent_document(inherited.parent["protocol_digest"])
        inherited.parent_path.write_bytes(canonical_json_bytes(inherited.parent))
        inherited.parent_lock = _lock(inherited.parent_path)
        self.baseline_dir = self.directory / "baseline"
        inherited.run(self.baseline_dir)
        self.expected_score_requests = tuple(inherited.score_calls)
        self.baseline_files = _files(self.baseline_dir)
        self.protocol_lock = _lock(self.baseline_dir / "protocol.json")
        self.evaluation_lock = _lock(self.baseline_dir / "evaluation.json")
        self.output = self.directory / "execution"

    def run(self, output=None, *, page_size=4, cancel=None, **overrides):
        inherited = self.inherited
        self.output = output or self.output
        inherited.output = self.output
        for collection in (
            inherited.events,
            inherited.calls,
            inherited.matrices,
            inherited.fit_calls,
            inherited.score_calls,
        ):
            collection.clear()
        processing_bytes = canonical_json_bytes(inherited.processing)
        inherited.arguments["processing_evidence_path"].write_bytes(processing_bytes)
        arguments = {
            **inherited.arguments,
            "processing_evidence_sha256": hashlib.sha256(processing_bytes).hexdigest(),
            "parent_report_path": inherited.parent_path,
            "parent_report_lock": inherited.parent_lock,
            "baseline_dir": self.baseline_dir,
            "baseline_protocol_lock": self.protocol_lock,
            "baseline_evaluation_lock": self.evaluation_lock,
            "output_dir": self.output,
            "page_size": page_size,
            "cancel": cancel,
            **overrides,
        }
        return runner.evaluate(**arguments)


@pytest.fixture
def execution(tmp_path, monkeypatch):
    # Only source-admission seams are synthetic. The old baseline, new baseline
    # codec, source fitting, scoring, bootstrap and page storage execute normally.
    harness = census_fixtures.harness.__wrapped__(tmp_path, monkeypatch)
    admitted = _ExecutionHarness(harness)
    monkeypatch.setattr(runner, "read_locked_hgnc", harness.read_reference)
    monkeypatch.setattr(runner, "build_cohort_matrix", numerical.build_cohort_matrix)
    return admitted


def _assert_complete_parity(execution):
    actual = _files(execution.output)
    assert set(actual) == set(execution.baseline_files) | {
        "execution-protocol.json",
        "execution.json",
    }
    for name, payload in execution.baseline_files.items():
        assert actual[name] == payload
    assert _files(execution.baseline_dir) == execution.baseline_files
    assert execution.inherited.fit_calls == list(execution.inherited.universe.axis.hgnc_ids)
    assert tuple(execution.inherited.score_calls) == execution.expected_score_requests
    assert len(execution.inherited.calls) == 256
    assert _json(execution.output / "execution.json")["complete"] is True


def test_complete_actual_synthetic_recomputation_replays_every_inherited_file_and_numerical_result(
    execution,
):
    result = execution.run()
    _assert_complete_parity(execution)
    assert result["profile_id"] == "cptac-gbm-census-execution/1.0.0"
    assert result["evaluation_id"] == "cptac-gbm-real-census-execution/1.0.0"
    protocol = _json(execution.output / "execution-protocol.json")
    seal = _json(execution.output / "execution.json")
    old_protocol = _json(execution.baseline_dir / "protocol.json")
    assert protocol["execution_protocol_digest"] == _manual_digest(
        {key: value for key, value in protocol.items() if key != "execution_protocol_digest"}
    )
    assert seal["execution_digest"] == _manual_digest(
        {key: value for key, value in seal.items() if key != "execution_digest"}
    )
    assert seal["execution_protocol_digest"] == protocol["execution_protocol_digest"]
    assert seal["numerical_protocol_digest"] == old_protocol["protocol_digest"]
    assert seal["numerical_profile_id"] == "cptac-gbm-source-fit-census/1.0.0"
    assert seal["all_inherited_artifacts_byte_identical"] is True
    assert seal["source_fits_recomputed"] is True
    assert seal["baseline_predictors_reused"] is False
    assert seal["new_scientific_inference_lane"] is False
    assert protocol["progress_retry_policy"] == {
        "max_wait_seconds": 2.0,
        "max_attempts": 101,
        "retry_interval_seconds": 0.02,
    }
    assert protocol["maximum_progress_bytes"] == 64 * 1024
    assert protocol["retryable_windows_errors"] == [5, 32, 33]
    assert protocol["numerical_request_digest_uses_execution_protocol"] is False
    assert _external_records(execution.output) == _external_records(execution.baseline_dir)
    assert _source_records(execution.output) == _source_records(execution.baseline_dir)


def test_nonanchor_seeds_use_inherited_protocol_even_when_execution_provenance_changes(
    execution, monkeypatch
):
    original = runner.frozen_protocol

    def with_operational_marker(**kwargs):
        value = original(**kwargs)
        value["execution_method_document_digest"] = "sha256:" + "e" * 64
        value["execution_protocol_digest"] = _manual_digest(
            {key: child for key, child in value.items() if key != "execution_protocol_digest"}
        )
        return value

    monkeypatch.setattr(runner, "frozen_protocol", with_operational_marker)
    execution.run()
    _assert_complete_parity(execution)
    numerical_protocol = _json(execution.baseline_dir / "protocol.json")["protocol_digest"]
    execution_protocol = _json(execution.output / "execution-protocol.json")[
        "execution_protocol_digest"
    ]
    record = next(
        row
        for row in _external_records(execution.output)
        if row["identity"]["hgnc_id"] == "HGNC:21"
    )
    assert record["result"]["request_digest"] == _manual_digest(
        {
            "census_protocol_digest": numerical_protocol,
            "hgnc_id": "HGNC:21",
        }
    )
    assert record["result"]["request_digest"] != _manual_digest(
        {
            "census_protocol_digest": execution_protocol,
            "hgnc_id": "HGNC:21",
        }
    )


def test_baseline_validation_finishes_before_source_metadata_or_measurements(
    execution, monkeypatch
):
    inherited = execution.inherited
    original = runner.load_baseline_census
    calls = []

    def load(**kwargs):
        assert inherited.events == [] and inherited.calls == [] and inherited.fit_calls == []
        loaded = original(**kwargs)
        calls.append("closed baseline validated")
        return loaded

    original_reference = runner.read_locked_hgnc

    def reference(path):
        assert calls == ["closed baseline validated"]
        return original_reference(path)

    monkeypatch.setattr(runner, "load_baseline_census", load)
    monkeypatch.setattr(runner, "read_locked_hgnc", reference)
    execution.run()
    _assert_complete_parity(execution)


def test_complete_source_byte_parity_is_required_before_any_external_measurement(
    execution, monkeypatch
):
    inherited = execution.inherited
    original_verify = baseline.BaselineCensus.verify_source_phase
    original_boundary = inherited.boundary
    verified = []

    def verify(self, output):
        assert inherited.fit_calls == list(inherited.universe.axis.hgnc_ids)
        assert len(inherited.calls) == 144
        result = original_verify(self, output)
        verified.append(True)
        return result

    def boundary(name, stage):
        if name == "external":
            assert verified == [True]
        return original_boundary(name, stage)

    monkeypatch.setattr(baseline.BaselineCensus, "verify_source_phase", verify)
    monkeypatch.setattr(inherited, "boundary", boundary)
    execution.run()
    _assert_complete_parity(execution)


def test_changed_source_artifact_stops_before_external_values(execution, monkeypatch):
    original = baseline.BaselineCensus.verify_source_phase

    def corrupt(self, output):
        path = output / "source-fit/pages/00000.json"
        path.write_bytes(path.read_bytes() + b" ")
        return original(self, output)

    monkeypatch.setattr(baseline.BaselineCensus, "verify_source_phase", corrupt)
    with pytest.raises(ValueError):
        execution.run()
    assert execution.inherited.fit_calls == list(execution.inherited.universe.axis.hgnc_ids)
    assert len(execution.inherited.calls) == 144
    assert not (execution.output / "execution.json").exists()
    assert _files(execution.baseline_dir) == execution.baseline_files


@pytest.mark.parametrize(
    "name",
    [
        "protocol.json",
        "evaluation.json",
        "source-fit/pages/00000.json",
        "external-score/pages/00000.json",
        "summary.csv",
    ],
)
def test_changed_runtime_baseline_fails_before_metadata_or_assays(execution, name):
    path = execution.baseline_dir / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        execution.run()
    assert execution.inherited.events == []
    assert execution.inherited.calls == execution.inherited.fit_calls == []
    assert not execution.output.exists()


@pytest.mark.parametrize("relation", ["same", "descendant"])
def test_execution_output_cannot_mutate_baseline_inventory(execution, relation):
    output = (
        execution.baseline_dir if relation == "same" else execution.baseline_dir / "new-execution"
    )
    with pytest.raises(ValueError):
        execution.run(output)
    assert execution.inherited.events == [] and execution.inherited.calls == []
    assert _files(execution.baseline_dir) == execution.baseline_files
    if relation == "descendant":
        assert not output.exists()


def test_fresh_numerical_protocol_mismatch_rejects_before_assays(execution):
    with pytest.raises(ValueError, match="identical frozen numerical"):
        execution.run(page_size=3)
    assert execution.inherited.calls == execution.inherited.fit_calls == []
    assert not execution.output.exists()


def _retryable_error():
    error = PermissionError(errno.EACCES, "synthetic private replacement context")
    error.winerror = 32
    return error


def test_progress_replacement_recovery_never_repeats_fitting_scoring_or_payload(
    execution, monkeypatch
):
    original = Path.replace
    monkeypatch.setattr(progress, "_WINDOWS", True)
    pending = []
    numerical_calls = []

    def replace_pending(path, target):
        if path == execution.output / "progress.json.tmp":
            payload = path.read_bytes()
            state = json.loads(payload)
            if state["phase"] == "source_fitting" and state["source_attempted"] == 4:
                pending.append(payload)
                numerical_calls.append(
                    (tuple(execution.inherited.fit_calls), tuple(execution.inherited.score_calls))
                )
                if len(pending) <= 2:
                    raise _retryable_error()
        return original(path, target)

    monkeypatch.setattr(Path, "replace", replace_pending)
    execution.run()
    _assert_complete_parity(execution)
    assert len(pending) == 3 and pending[0] == pending[1] == pending[2]
    assert numerical_calls[0] == numerical_calls[1] == numerical_calls[2]
    assert not (execution.output / "progress.json.tmp").exists()


def test_exhausted_progress_retry_preserves_pending_bytes_and_incomplete_evidence(
    execution, monkeypatch
):
    original = Path.replace
    monkeypatch.setattr(progress, "_WINDOWS", True)
    attempts = []

    def blocked(path, target):
        if path == execution.output / "progress.json.tmp":
            state = json.loads(path.read_bytes())
            if state["phase"] == "source_fitting" and state["source_attempted"] == 4:
                attempts.append(path.read_bytes())
                raise _retryable_error()
        return original(path, target)

    monkeypatch.setattr(Path, "replace", blocked)
    with pytest.raises(progress.ProgressReplacementExhaustedError):
        execution.run()
    assert 1 <= len(attempts) <= 101 and len(set(attempts)) == 1
    assert len(execution.inherited.fit_calls) == 4
    assert len(execution.inherited.calls) == 144
    assert not (execution.output / "execution.json").exists()
    assert not (execution.output / "source-fit/source-census-manifest.json").exists()
    assert (execution.output / "progress.json.tmp").read_bytes() == attempts[-1]
    assert _json(execution.output / "progress.json")["complete"] is False
    assert _files(execution.baseline_dir) == execution.baseline_files


def test_unexpected_progress_error_propagates_without_any_retry(execution, monkeypatch):
    original = Path.replace
    attempts = []

    def fail(path, target):
        if path == execution.output / "progress.json.tmp":
            attempts.append(True)
            raise OSError(errno.ENOSPC, "synthetic private storage failure")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError) as error:
        execution.run()
    assert error.value.errno == errno.ENOSPC and attempts == [True]
    assert execution.inherited.calls == execution.inherited.fit_calls == []
    assert not (execution.output / "execution.json").exists()


def test_tampered_new_execution_protocol_cannot_receive_a_completion_seal(execution, monkeypatch):
    original = runner._execution_seal

    def changed(output, **kwargs):
        path = output / "execution-protocol.json"
        path.write_bytes(path.read_bytes() + b" ")
        return original(output, **kwargs)

    monkeypatch.setattr(runner, "_execution_seal", changed)
    with pytest.raises(ValueError):
        execution.run()
    assert (execution.output / "evaluation.json").exists()
    assert _json(execution.output / "progress.json")["complete"] is True
    assert not (execution.output / "execution.json").exists()


def test_final_numerical_mismatch_does_not_get_hidden_by_legacy_completion(execution, monkeypatch):
    original = runner._execution_seal

    def changed(output, **kwargs):
        path = output / "summary.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        return original(output, **kwargs)

    monkeypatch.setattr(runner, "_execution_seal", changed)
    with pytest.raises(ValueError):
        execution.run()
    assert _json(execution.output / "progress.json")["complete"] is True
    assert not (execution.output / "execution.json").exists()


def test_external_page_checkpoint_rejects_changed_bytes_before_the_next_page(
    execution, monkeypatch
):
    original = numerical._write_external_page
    written = []

    def changed(output, records, **kwargs):
        page = original(output, records, **kwargs)
        path = output / page["file_name"]
        path.write_bytes(path.read_bytes() + b" ")
        written.append(page)
        return page

    monkeypatch.setattr(numerical, "_write_external_page", changed)
    with pytest.raises(ValueError):
        execution.run()
    assert len(written) == 1
    assert execution.inherited.fit_calls == list(execution.inherited.universe.axis.hgnc_ids)
    assert len(execution.inherited.score_calls) <= 4
    assert (execution.output / "source-checks.json").exists()
    assert not (execution.output / "external-score/external-score-manifest.json").exists()
    assert not (execution.output / "execution.json").exists()
    assert _files(execution.baseline_dir) == execution.baseline_files


@pytest.mark.parametrize("when", ["before_baseline", "during_source", "during_external"])
def test_cancellation_propagates_without_completing_or_reusing_predictors(execution, when):
    def cancel():
        if (
            when == "before_baseline"
            or (when == "during_source" and execution.inherited.fit_calls)
            or (when == "during_external" and execution.inherited.score_calls)
        ):
            raise RuntimeError("synthetic cancellation")

    with pytest.raises(RuntimeError, match="cancellation"):
        execution.run(cancel=cancel)
    assert not (execution.output / "execution.json").exists()
    if when == "during_external":
        assert execution.inherited.fit_calls == list(execution.inherited.universe.axis.hgnc_ids)
        assert len(execution.inherited.calls) == 256
        assert len(execution.inherited.score_calls) == 1
    else:
        assert all(name == "source" for name, *_ in execution.inherited.calls)
        assert len(execution.inherited.fit_calls) <= 1


def test_quiet_repeated_execution_is_deterministic_and_contains_no_private_tokens(execution):
    first, second = (
        execution.directory / "first-execution",
        execution.directory / "second-execution",
    )
    execution.run(first)
    execution.run(second)
    assert _files(first) == _files(second)
    tokens = {str(execution.directory)}
    for plan in execution.inherited.plans.values():
        for candidate in plan.candidates:
            tokens.update(asdict(candidate).values())
    for payload in _files(second).values():
        assert not any(token.encode() in payload for token in tokens)
        assert b'"_predictors"' not in payload and b'"patient_indices"' not in payload


def _cli_arguments(directory):
    arguments = _census_cli_arguments(directory)
    return [
        *arguments,
        "--baseline-dir",
        str(directory / "synthetic-baseline"),
        "--baseline-protocol-bytes",
        "123",
        "--baseline-protocol-md5",
        "a" * 32,
        "--baseline-protocol-sha256",
        "b" * 64,
        "--baseline-evaluation-bytes",
        "456",
        "--baseline-evaluation-md5",
        "c" * 32,
        "--baseline-evaluation-sha256",
        "d" * 64,
    ]


@pytest.mark.parametrize("error_type", [OSError, ValueError, RuntimeError])
def test_cli_errors_suppress_private_paths_and_traceback_context(
    tmp_path, monkeypatch, capsys, error_type
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))

    def fail(**_kwargs):
        raise error_type(f"{tmp_path} synthetic private specimen")

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2 and error.value.__suppress_context__ is True
    output = capsys.readouterr()
    assert output.out == "" and output.err == (
        "Census execution did not complete; retain incomplete local evidence "
        "without treating it as a finished result.\n"
    )


def test_cli_keeps_runtime_baseline_locks_distinct_and_prints_new_execution_identity(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    expected = {"profile_id": "cptac-gbm-census-execution/1.0.0", "complete": True}

    def evaluate(**kwargs):
        assert kwargs["baseline_dir"] == tmp_path / "synthetic-baseline"
        assert kwargs["baseline_protocol_lock"] == SourceLock(123, "a" * 32, "b" * 64)
        assert kwargs["baseline_evaluation_lock"] == SourceLock(456, "c" * 32, "d" * 64)
        assert kwargs["parent_report_lock"] == SourceLock(123, "b" * 32, "c" * 64)
        assert kwargs["output_dir"] == tmp_path / "private-output-dir"
        assert kwargs["page_size"] == 3
        return expected

    monkeypatch.setattr(runner, "evaluate", evaluate)
    assert runner.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected and output.err == ""
