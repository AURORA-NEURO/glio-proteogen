"""Private orchestration boundaries and one genuine synthetic replay integration.

Controlled routing uses an explicitly synthetic internal context and does not
authenticate source recovery. The integration test separately reproduces
genuine selected-candidate checkpoints with real default refits and point
solves; inherited nonselected-candidate fixtures are legal controlled failures.
"""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
import runpy
import sys
from functools import lru_cache
from io import BytesIO, TextIOWrapper
from pathlib import Path

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution import DEFAULT_TRAINING_CONFIGURATION
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixtureBenchmarkPlan,
    MixturePointPolicy,
    score_replayed_fold,
)
from glio_proteogen.research.gbmap_mixture_benchmark import benchmark as point_engine
from glio_proteogen.research.gbmap_policy_sensitivity import (
    MatchedPolicySensitivityReceipt,
    PolicySensitivityError,
    score_matched_policy_sensitivity,
)
from glio_proteogen.research.gbmap_selected_fold_replay import SelectedFoldReplayResult
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tests.research import test_gbmap_mixture_benchmark as point_fixture
from tests.tooling import test_replay_gbmap_selected_fold as replay_fixture
from tools import benchmark_gbmap_selected_fold as benchmark_driver
from tools import compare_gbmap_policy_sensitivity as driver
from tools import replay_gbmap_selected_fold as replay

_FAILURE = "GBmap policy sensitivity failed closed"
_REVIEWED = replay_fixture._REVIEWED


def _policy(**changes):
    return {
        "concentration": 100.0,
        "lambda_mass": 0.0,
        "lambda_shape": 0.1,
        "initial_unknown_mass": 0.05,
        **changes,
    }


def _document():
    return {"policies": [_policy(lambda_mass=0.01), _policy()]}


def _write_plan(tmp_path, *, document=None, payload=None):
    path = tmp_path / "plan.json"
    path.write_bytes(
        json.dumps(_document() if document is None else document, indent=2).encode()
        if payload is None
        else payload
    )
    return path


def _run(path, **changes):
    return driver.run_policy_sensitivity(
        Path("synthetic-source.h5ad"),
        _REVIEWED,
        Path("synthetic-preflight.json"),
        Path("synthetic-run"),
        path,
        **{
            "fold_id": "whole-study-0001",
            "development_only_acknowledged": True,
            "sha256_independently_reviewed": True,
            **changes,
        },
    )


@lru_cache(maxsize=1)
def _comparison_fixture():
    """Toy internal builder data; never evidence of actual source recovery."""
    context = point_fixture._context((point_fixture._case(),))
    plan = MixtureBenchmarkPlan(
        policies=(MixturePointPolicy(**_policy(lambda_mass=0.01)), MixturePointPolicy(**_policy()))
    )
    parent = score_replayed_fold(context, plan.policies, omissions=plan.omissions)
    receipt = score_matched_policy_sensitivity(context, plan, parent_benchmark=parent)
    return context, plan, parent, receipt


def _controlled_route(monkeypatch):
    context, _plan, parent, receipt = _comparison_fixture()
    calls = []

    def recover(*args, **kwargs):
        calls.append(("recover", args, kwargs))
        return context

    def score(supplied, policies, *, omissions):
        assert supplied is context
        calls.append(("parent", policies, omissions))
        return parent

    def compare(supplied, plan, *, parent_benchmark):
        assert supplied is context
        assert parent_benchmark is parent
        calls.append(("matched", plan, parent_benchmark))
        return receipt

    monkeypatch.setattr(driver, "recover_selected_fold_context", recover)
    monkeypatch.setattr(driver, "score_replayed_fold", score)
    monkeypatch.setattr(driver, "score_matched_policy_sensitivity", compare)
    return context, parent, receipt, calls


def _forbidden(*_args, **_kwargs):
    raise AssertionError("a rejected request reached source recovery or point solving")


def test_existing_plan_loader_is_reused_without_duplicated_policy_defaults():
    assert driver._load_plan is benchmark_driver._load_plan


@pytest.mark.parametrize("omissions", [[], [["Oligodendrocyte"], ["Mural cell"]]])
def test_one_recovery_then_parent_then_matched_use_the_same_context_and_explicit_plan(
    tmp_path, monkeypatch, omissions
):
    path = _write_plan(tmp_path, document={**_document(), "omissions": omissions})
    _context, parent, receipt, calls = _controlled_route(monkeypatch)
    loaded = []
    original = driver._load_plan

    def load(plan_path):
        value = original(plan_path)
        loaded.append(value)
        return value

    monkeypatch.setattr(driver, "_load_plan", load)
    assert _run(path) == receipt
    assert [call[0] for call in calls] == ["recover", "parent", "matched"]
    assert len(loaded) == 1
    assert calls[1][1] == loaded[0].policies
    assert calls[1][2] == loaded[0].omissions
    assert loaded[0].omissions == tuple(tuple(row) for row in omissions)
    assert calls[2][1] is loaded[0]
    assert calls[2][2] is parent
    assert calls[0][1] == (
        Path("synthetic-source.h5ad"),
        _REVIEWED,
        Path("synthetic-preflight.json"),
        Path("synthetic-run"),
    )
    assert calls[0][2] == {
        "fold_id": "whole-study-0001",
        "development_only_acknowledged": True,
        "sha256_independently_reviewed": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"null",
        b"[]",
        b"{}",
        b'{"policies":[],"policies":[]}',
        b'{"policies":[{"concentration":NaN}]}',
        json.dumps({"policies": [_policy(concentration=100)]}).encode(),
        json.dumps({"policies": [_policy(), _policy()]}).encode(),
        json.dumps({"policies": [_policy()], "omissions": [["not-a-public-label"]]}).encode(),
        json.dumps({"policies": [_policy()], "omissions": [["Neuron", "Neuron"]]}).encode(),
    ],
)
def test_invalid_plan_is_rejected_before_recovery_or_either_point_pass(
    tmp_path, monkeypatch, payload
):
    path = _write_plan(tmp_path, payload=payload)
    monkeypatch.setattr(driver, "recover_selected_fold_context", _forbidden)
    monkeypatch.setattr(driver, "score_replayed_fold", _forbidden)
    monkeypatch.setattr(driver, "score_matched_policy_sensitivity", _forbidden)
    with pytest.raises(PolicySensitivityError, match=_FAILURE) as caught:
        _run(path)
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize(
    "field",
    ["development_only_acknowledged", "sha256_independently_reviewed"],
)
@pytest.mark.parametrize("value", [False, 1])
def test_acknowledgements_are_checked_before_plan_io(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(driver, "_load_plan", _forbidden)
    monkeypatch.setattr(driver, "recover_selected_fold_context", _forbidden)
    with pytest.raises(PolicySensitivityError, match=_FAILURE):
        _run(tmp_path / "unread-plan.json", **{field: value})


@pytest.mark.parametrize("kind", ["missing", "directory", "empty", "oversized"])
def test_reused_file_boundary_fails_before_heavy_recovery(tmp_path, monkeypatch, kind):
    path = tmp_path / "plan.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "empty":
        path.write_bytes(b"")
    elif kind == "oversized":
        path.write_bytes(b" " * (benchmark_driver.MAX_PLAN_BYTES + 1))
    monkeypatch.setattr(driver, "recover_selected_fold_context", _forbidden)
    with pytest.raises(PolicySensitivityError, match=_FAILURE):
        _run(path)


@pytest.mark.parametrize(
    "phase",
    [
        "_load_plan",
        "recover_selected_fold_context",
        "score_replayed_fold",
        "score_matched_policy_sensitivity",
        "canonical_receipt_bytes",
    ],
)
def test_private_stage_errors_are_sanitized_without_retaining_a_recovered_context(
    tmp_path, monkeypatch, phase
):
    path = _write_plan(tmp_path)
    context, _parent, _receipt, _calls = _controlled_route(monkeypatch)

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-private-case-and-parameters")

    monkeypatch.setattr(driver, phase, fail)
    with pytest.raises(PolicySensitivityError) as caught:
        _run(path)
    assert str(caught.value) == _FAILURE
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert "synthetic-private" not in repr(caught.value)
    traceback = caught.value.__traceback__
    public_frames = []
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_code.co_name == "run_policy_sensitivity":
            public_frames.append(frame)
            assert all(value is not context for value in frame.f_locals.values())
            assert not any(
                type(value) is SelectedFoldReplayResult for value in frame.f_locals.values()
            )
        traceback = traceback.tb_next
    assert len(public_frames) == 1


@pytest.mark.parametrize(
    "phase",
    [
        "_load_plan",
        "recover_selected_fold_context",
        "score_replayed_fold",
        "score_matched_policy_sensitivity",
        "canonical_receipt_bytes",
    ],
)
def test_cooperative_cancellation_propagates(tmp_path, monkeypatch, phase):
    path = _write_plan(tmp_path)
    _controlled_route(monkeypatch)
    cancellation = InferenceCancelledError("synthetic cooperative cancellation")

    def cancel(*_args, **_kwargs):
        raise cancellation

    monkeypatch.setattr(driver, phase, cancel)
    with pytest.raises(InferenceCancelledError) as caught:
        _run(path)
    assert caught.value is cancellation


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_process_interrupts_are_not_converted_to_ordinary_failures(
    tmp_path, monkeypatch, exception
):
    path = _write_plan(tmp_path)

    def interrupt(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(driver, "recover_selected_fold_context", interrupt)
    with pytest.raises(exception):
        _run(path)


def test_missing_inner_result_cannot_be_returned_as_a_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_run_policy_sensitivity", lambda *_a, **_kw: None)
    with pytest.raises(PolicySensitivityError, match=_FAILURE):
        _run(tmp_path / "unused-plan.json")


def test_encoder_requires_closed_receipt_and_exact_output_bound(monkeypatch):
    receipt = _comparison_fixture()[3]
    payload = driver.canonical_receipt_bytes(receipt)
    assert payload == canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n"
    assert MatchedPolicySensitivityReceipt.model_validate_json(payload) == receipt
    with pytest.raises(PolicySensitivityError, match="exact closed"):
        driver.canonical_receipt_bytes(receipt.model_dump(mode="json"))
    monkeypatch.setattr(driver, "MAX_OUTPUT_BYTES", len(payload))
    assert driver.canonical_receipt_bytes(receipt) == payload
    monkeypatch.setattr(driver, "MAX_OUTPUT_BYTES", len(payload) - 1)
    with pytest.raises(PolicySensitivityError, match="output bound"):
        driver.canonical_receipt_bytes(receipt)


def test_api_rejects_unpublishable_oversized_output(tmp_path, monkeypatch):
    path = _write_plan(tmp_path)
    _context, _parent, receipt, calls = _controlled_route(monkeypatch)
    monkeypatch.setattr(
        driver, "MAX_OUTPUT_BYTES", len(driver.canonical_receipt_bytes(receipt)) - 1
    )
    with pytest.raises(PolicySensitivityError, match=_FAILURE):
        _run(path)
    assert [call[0] for call in calls] == ["recover", "parent", "matched"]


def test_aggregate_contract_has_no_per_case_parameters_or_identity_records():
    receipt = _comparison_fixture()[3]
    payload = driver.canonical_receipt_bytes(receipt)
    for field in (
        "signatures",
        "background",
        "hierarchy_concentrations",
        "feature_indices",
        "cases",
        "selected_counts",
        "donor_key",
        "study_key",
        "source_path",
        "predictions",
        "known_rna_weights",
    ):
        assert (b'"' + field.encode() + b'"') not in payload
    document = json.loads(payload)
    for field in (
        "policy_selection_performed",
        "calibration_performed",
        "empirical_unit_independence_established",
        "clinical_validity_established",
    ):
        assert document[field] is False
    document["predictions"] = []
    with pytest.raises(ValidationError):
        MatchedPolicySensitivityReceipt.model_validate_json(json.dumps(document))


def _arguments():
    return [
        "synthetic-source.h5ad",
        "--reviewed-sha256",
        _REVIEWED,
        "--preflight",
        "synthetic-preflight.json",
        "--run-directory",
        "synthetic-run",
        "--fold-id",
        "whole-study-0001",
        "--plan",
        "synthetic-plan.json",
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
    ]


def test_cli_dispatches_exact_paths_and_prints_only_canonical_aggregate(monkeypatch, capsys):
    receipt = _comparison_fixture()[3]
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return receipt

    monkeypatch.setattr(driver, "run_policy_sensitivity", run)
    assert driver.main(_arguments()) == 0
    captured = capsys.readouterr()
    assert captured.out.encode() == driver.canonical_receipt_bytes(receipt)
    assert captured.err == ""
    assert calls == [
        (
            (
                Path("synthetic-source.h5ad"),
                _REVIEWED,
                Path("synthetic-preflight.json"),
                Path("synthetic-run"),
                Path("synthetic-plan.json"),
            ),
            {
                "fold_id": "whole-study-0001",
                "development_only_acknowledged": True,
                "sha256_independently_reviewed": True,
            },
        )
    ]


def test_cli_uses_binary_stdout_without_text_encoding_or_newline_rewrites(monkeypatch):
    receipt = _comparison_fixture()[3]
    monkeypatch.setattr(driver, "run_policy_sensitivity", lambda *_args, **_kwargs: receipt)
    binary = BytesIO()
    # Reproduce Windows CRLF translation, and a non-UTF-8 text encoding,
    # independently of the host running this synthetic transport regression.
    with TextIOWrapper(binary, encoding="utf-16", newline="\r\n", write_through=True) as stream:
        monkeypatch.setattr(sys, "stdout", stream)
        assert driver.main(_arguments()) == 0
        stream.flush()
        assert binary.getvalue() == driver.canonical_receipt_bytes(receipt)


def test_cli_failure_hides_private_exception(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise ValueError("synthetic-private-source-and-scores")

    monkeypatch.setattr(driver, "run_policy_sensitivity", fail)
    assert driver.main(_arguments()) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap policy sensitivity failed closed\n"


def test_cli_cooperative_cancellation_propagates(monkeypatch):
    def cancel(*_args, **_kwargs):
        raise InferenceCancelledError("synthetic cancellation")

    monkeypatch.setattr(driver, "run_policy_sensitivity", cancel)
    with pytest.raises(InferenceCancelledError):
        driver.main(_arguments())


@pytest.mark.parametrize(
    "arguments",
    [[], ["--unknown", "synthetic-private"], [*_arguments(), "--output", "synthetic-private"]],
)
def test_invalid_cli_arguments_do_not_echo_values_or_call_io(monkeypatch, capsys, arguments):
    monkeypatch.setattr(driver, "run_policy_sensitivity", _forbidden)
    monkeypatch.setattr(driver, "_load_plan", _forbidden)
    with pytest.raises(SystemExit) as caught:
        driver.main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: policy-sensitivity arguments were not accepted\n"


def test_help_and_direct_script_entrypoint_read_no_inputs(monkeypatch, capsys):
    monkeypatch.setattr(driver, "run_policy_sensitivity", _forbidden)
    with pytest.raises(SystemExit) as caught:
        driver.main(["--help"])
    assert caught.value.code == 0
    assert "--plan" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["compare-gbmap-policy-sensitivity", "--help"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    with pytest.raises(SystemExit) as direct:
        runpy.run_path(driver.__file__, run_name="__main__")
    assert direct.value.code == 0
    assert "--plan" in capsys.readouterr().out


def test_genuine_recovery_is_once_while_parent_and_matched_rerun_actual_point_solves(
    tmp_path, monkeypatch
):
    state = replay_fixture._numerical_state()
    inputs = replay_fixture._write_inputs(tmp_path, monkeypatch, state)
    path = _write_plan(tmp_path)
    fits = []
    recoveries = []
    solves = []
    original_fit = replay._fit_label
    original_recover = driver.recover_selected_fold_context
    original_solve = point_engine.solve_reference_mixture

    def fit(*args, **kwargs):
        assert kwargs["configuration"] is DEFAULT_TRAINING_CONFIGURATION.hierarchy
        fits.append(kwargs["label"])
        return original_fit(*args, **kwargs)

    def recover(*args, **kwargs):
        recoveries.append(True)
        return original_recover(*args, **kwargs)

    def solve(*args, **kwargs):
        solution = original_solve(*args, **kwargs)
        solves.append(True)
        return solution

    monkeypatch.setattr(replay, "_fit_label", fit)
    monkeypatch.setattr(driver, "recover_selected_fold_context", recover)
    monkeypatch.setattr(point_engine, "solve_reference_mixture", solve)
    before = replay_fixture._inventory(tmp_path)
    receipt = driver.run_policy_sensitivity(
        inputs[0],
        _REVIEWED,
        inputs[1],
        inputs[2],
        path,
        fold_id="whole-study-0001",
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    parent = receipt.parent_benchmark
    assert recoveries == [True]
    assert fits == list(parent.context_receipt.known_labels) == ["MES-like", "NPC-like"]
    assert (
        len(solves) == 2 * len(parent.policies) * parent.context_receipt.held_truth.held_unit_count
    )
    assert len(solves) == 20
    assert any(row.scored_case_count > 0 for row in parent.results)
    assert all(
        row.offered_case_count
        == row.scored_case_count + sum(terminal.count for terminal in row.terminal_counts)
        for row in parent.results
    )
    assert receipt.policy_selection_performed is receipt.calibration_performed is False
    assert receipt.empirical_unit_independence_established is False
    assert receipt.clinical_validity_established is False
    assert replay_fixture._inventory(tmp_path) == before
