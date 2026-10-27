"""Private plan-routing boundaries plus one genuine refit/point-solver integration.

Controlled routing tests use explicitly synthetic private contexts and make no
source-recovery claim. The separate end-to-end test reuses genuine checkpoint
fixtures and delegates both phase1 refitting and point solving to real defaults.
"""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
import os
import runpy
import sys
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution import DEFAULT_TRAINING_CONFIGURATION
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixtureBenchmarkError,
    MixtureBenchmarkPlan,
    MixtureBenchmarkReceipt,
    MixturePointPolicy,
    score_replayed_fold,
)
from glio_proteogen.research.gbmap_mixture_benchmark import benchmark as point_engine
from glio_proteogen.research.gbmap_selected_fold_replay import SelectedFoldReplayResult
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tests.research import test_gbmap_mixture_benchmark as point_fixture
from tests.tooling import test_replay_gbmap_selected_fold as replay_fixture
from tools import benchmark_gbmap_selected_fold as benchmark
from tools import replay_gbmap_selected_fold as replay

_REVIEWED = replay_fixture._REVIEWED
_FAILURE = "GBmap selected-fold benchmark failed closed"


def _policy(**changes):
    return {
        "concentration": 100.0,
        "lambda_mass": 0.0,
        "lambda_shape": 0.1,
        "initial_unknown_mass": 0.05,
        **changes,
    }


def _plan(**changes):
    return {"policies": [_policy()], **changes}


def _write_plan(tmp_path, document=None, *, payload=None):
    path = tmp_path / "plan.json"
    path.write_bytes(
        json.dumps(_plan() if document is None else document, indent=2).encode()
        if payload is None
        else payload
    )
    return path


def _run(plan_path, **changes):
    return benchmark.run_selected_fold_benchmark(
        Path("synthetic-source.h5ad"),
        _REVIEWED,
        Path("synthetic-preflight.json"),
        Path("synthetic-run"),
        plan_path,
        **{
            "fold_id": "whole-study-0001",
            "development_only_acknowledged": True,
            "sha256_independently_reviewed": True,
            **changes,
        },
    )


def _forbid_recovery(monkeypatch):
    calls = []

    def recover(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("invalid plan reached heavy source recovery")

    monkeypatch.setattr(benchmark, "recover_selected_fold_context", recover)
    return calls


@lru_cache(maxsize=1)
def _controlled_point_context():
    """A synthetic internal-builder context, explicitly not source replay."""
    return point_fixture._context((point_fixture._case(),))


@lru_cache(maxsize=1)
def _controlled_point_receipt():
    return score_replayed_fold(_controlled_point_context(), (MixturePointPolicy(**_policy()),))


def _controlled_route(monkeypatch, *, receipt=None):
    context = _controlled_point_context()
    output = _controlled_point_receipt() if receipt is None else receipt
    calls = []

    def recover(*args, **kwargs):
        calls.append(("recover", args, kwargs))
        return context

    def score(*args, **kwargs):
        calls.append(("score", args, kwargs))
        return output

    monkeypatch.setattr(benchmark, "recover_selected_fold_context", recover)
    monkeypatch.setattr(benchmark, "score_replayed_fold", score)
    return context, output, calls


def test_valid_human_json_plan_routes_once_in_order_with_every_explicit_value(
    tmp_path, monkeypatch
):
    declaration = _plan(
        policies=[_policy(concentration=200.0), _policy()],
        omissions=[["Oligodendrocyte"], ["Mural cell"]],
    )
    path = _write_plan(tmp_path, declaration)
    context, expected, calls = _controlled_route(monkeypatch)
    loaded = []
    original = benchmark._load_plan

    def load(plan_path):
        loaded.append(plan_path)
        assert calls == []
        return original(plan_path)

    monkeypatch.setattr(benchmark, "_load_plan", load)
    assert _run(path) is expected
    assert loaded == [path]
    assert [event[0] for event in calls] == ["recover", "score"]
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
    assert calls[1][1][0] is context
    assert tuple(policy.concentration for policy in calls[1][1][1]) == (200.0, 100.0)
    assert calls[1][2] == {"omissions": (("Oligodendrocyte",), ("Mural cell",))}


def test_controlled_recovery_with_real_point_solver_canonicalizes_unique_outer_orders(
    tmp_path, monkeypatch
):
    context = _controlled_point_context()
    monkeypatch.setattr(benchmark, "recover_selected_fold_context", lambda *_a, **_kw: context)
    declaration = _plan(
        policies=[_policy(concentration=200.0), _policy()],
        omissions=[["Oligodendrocyte"], ["Mural cell"]],
    )
    path = _write_plan(tmp_path, declaration)
    first = _run(path)
    declaration["policies"].reverse()
    declaration["omissions"].reverse()
    path.write_text(json.dumps(declaration), encoding="utf-8")
    second = _run(path)
    assert benchmark.canonical_receipt_bytes(first) == benchmark.canonical_receipt_bytes(second)
    assert tuple(policy.concentration for policy in first.policies) == (100.0, 200.0)
    assert first.omissions == (("Mural cell",), ("Oligodendrocyte",))
    assert len(first.results) == 6
    assert first.policy_selection_performed is first.calibration_performed is False


def test_genuine_checkpoint_recovery_and_actual_point_solver_integration(tmp_path, monkeypatch):
    state = replay_fixture._numerical_state()
    inputs = replay_fixture._write_inputs(tmp_path, monkeypatch, state)
    path = _write_plan(tmp_path)
    fit_calls = []
    recover_calls = []
    solver_calls = []
    original_fit = replay._fit_label
    original_recover = benchmark.recover_selected_fold_context
    original_solver = point_engine.solve_reference_mixture

    def fit(*args, **kwargs):
        assert kwargs["configuration"] is DEFAULT_TRAINING_CONFIGURATION.hierarchy
        fit_calls.append(kwargs["label"])
        return original_fit(*args, **kwargs)

    def recover(*args, **kwargs):
        recover_calls.append(True)
        return original_recover(*args, **kwargs)

    def solve(*args, **kwargs):
        solution = original_solver(*args, **kwargs)
        solver_calls.append(solution)
        return solution

    monkeypatch.setattr(replay, "_fit_label", fit)
    monkeypatch.setattr(benchmark, "recover_selected_fold_context", recover)
    monkeypatch.setattr(point_engine, "solve_reference_mixture", solve)
    before = replay_fixture._inventory(tmp_path)
    receipt = benchmark.run_selected_fold_benchmark(
        inputs[0],
        _REVIEWED,
        inputs[1],
        inputs[2],
        path,
        fold_id="whole-study-0001",
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    assert recover_calls == [True]
    assert fit_calls == list(receipt.context_receipt.known_labels) == ["MES-like", "NPC-like"]
    assert len(solver_calls) == receipt.context_receipt.held_truth.held_unit_count == 5
    result = receipt.results[0]
    assert result.offered_case_count == 5
    assert result.scored_case_count > 0
    assert result.offered_case_count == result.scored_case_count + sum(
        row.count for row in result.terminal_counts
    )
    assert receipt.context_receipt.held_truth.held_raw_record_count == 11
    assert receipt.context_receipt.held_truth.held_reference_eligible_record_count == 10
    assert receipt.policy_selection_performed is receipt.calibration_performed is False
    assert receipt.unbiased_performance_established is False
    assert replay_fixture._inventory(tmp_path) == before


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b" ",
        b"[]",
        b"null",
        b"{}",
        b"{",
        b"\xff\xfeinvalid",
        b'{"policies":[],"private-path":"synthetic-private"}',
    ],
)
def test_malformed_or_nonobject_plans_stop_before_source_recovery(tmp_path, monkeypatch, payload):
    path = _write_plan(tmp_path, payload=payload)
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE) as caught:
        _run(path)
    assert calls == []
    assert caught.value.__context__ is None
    assert "synthetic-private" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        (
            '{"policies":['
            + json.dumps(_policy())
            + '],"policies":['
            + json.dumps(_policy(concentration=200.0))
            + "]}"
        ).encode(),
        b'{"policies":[{"concentration":100.0,"concentration":200.0,"lambda_mass":0.0,"lambda_shape":0.1,"initial_unknown_mass":0.05}]}',
    ],
)
def test_duplicate_json_keys_at_every_object_depth_stop_before_recovery(
    tmp_path, monkeypatch, payload
):
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(_write_plan(tmp_path, payload=payload))
    assert calls == []


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_nonfinite_json_numbers_never_reach_recovery(tmp_path, monkeypatch, literal):
    payload = json.dumps(_plan()).replace("100.0", literal).encode()
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(_write_plan(tmp_path, payload=payload))
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("concentration", 100),
        ("lambda_mass", True),
        ("lambda_shape", "0.1"),
        ("initial_unknown_mass", None),
        ("concentration", 0.0),
        ("lambda_mass", -0.1),
        ("lambda_shape", -0.1),
        ("initial_unknown_mass", 0.0),
        ("initial_unknown_mass", 1.0),
    ],
)
def test_policy_domain_and_native_float_types_are_validated_before_recovery(
    tmp_path, monkeypatch, field, value
):
    path = _write_plan(tmp_path, _plan(policies=[_policy(**{field: value})]))
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert calls == []


@pytest.mark.parametrize(
    "field", ["concentration", "lambda_mass", "lambda_shape", "initial_unknown_mass"]
)
def test_every_policy_coordinate_is_explicit_with_no_hidden_numeric_default(
    tmp_path, monkeypatch, field
):
    policy = _policy()
    del policy[field]
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(_write_plan(tmp_path, _plan(policies=[policy])))
    assert calls == []


@pytest.mark.parametrize(
    "declaration",
    [
        _plan(policies=[]),
        _plan(policies=[_policy(), _policy()]),
        _plan(omissions=[[], ["Mural cell"]]),
        _plan(omissions=[["Mural cell"], ["Mural cell"]]),
        _plan(omissions=[["Oligodendrocyte", "Mural cell"]]),
        _plan(omissions=[["Mural cell", "Mural cell"]]),
        _plan(omissions=[["synthetic-private-label"]]),
        _plan(plan_version="gbmap-mixture-sensitivity-plan/2.0.0"),
        _plan(unknown_field=True),
    ],
)
def test_closed_unique_canonical_member_plan_constraints_are_early(
    tmp_path, monkeypatch, declaration
):
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(_write_plan(tmp_path, declaration))
    assert calls == []


def test_plan_defaults_and_maximum_policy_omission_bounds_are_explicit(tmp_path):
    path = _write_plan(tmp_path)
    defaulted = benchmark._load_plan(path)
    assert defaulted.plan_version == "gbmap-mixture-sensitivity-plan/1.0.0"
    assert defaulted.omissions == ()
    assert len(defaulted.policies) == 1
    declaration = _plan(
        policies=[_policy(concentration=float(index + 1)) for index in range(64)],
        omissions=[[label] for label in PRODUCTION_SOURCE_LABELS],
    )
    path.write_text(json.dumps(declaration), encoding="utf-8")
    loaded = benchmark._load_plan(path)
    assert len(loaded.policies) == 64
    assert len(loaded.omissions) == 20
    assert MixtureBenchmarkPlan.model_validate_json(loaded.model_dump_json()) == loaded


@pytest.mark.parametrize("excess", ["policies", "omissions"])
def test_plan_work_product_bounds_are_enforced_before_recovery(tmp_path, monkeypatch, excess):
    declaration = _plan()
    if excess == "policies":
        declaration["policies"] = [_policy(concentration=float(index + 1)) for index in range(65)]
    else:
        declaration["omissions"] = [[label] for label in PRODUCTION_SOURCE_LABELS] + [
            list(PRODUCTION_SOURCE_LABELS[:2])
        ]
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(_write_plan(tmp_path, declaration))
    assert calls == []


def test_plan_read_is_bounded_and_oversized_file_rejected_before_recovery(tmp_path, monkeypatch):
    path = _write_plan(tmp_path, payload=b" " * (benchmark.MAX_PLAN_BYTES + 1))
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert calls == []


@pytest.mark.parametrize(
    "kind", ["missing", "directory", "text", "reparse", "ancestor_file", "ancestor_reparse"]
)
def test_plan_path_roles_reject_missing_nonregular_or_reparse_before_recovery(
    tmp_path, monkeypatch, kind
):
    path = _write_plan(tmp_path)
    if kind == "missing":
        path.unlink()
    elif kind == "directory":
        path = tmp_path
    elif kind == "text":
        path = str(path)
    elif kind == "ancestor_file":
        path = path / "nested.json"
    else:
        inode = (path if kind == "reparse" else path.parent).stat().st_ino
        original = benchmark.fit_driver._is_link_or_reparse
        monkeypatch.setattr(
            benchmark.fit_driver,
            "_is_link_or_reparse",
            lambda info: info.st_ino == inode or original(info),
        )
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert calls == []


def test_changed_plan_after_bounded_read_does_not_reach_recovery(tmp_path, monkeypatch):
    path = _write_plan(tmp_path)
    original = benchmark.tasks._read_regular_bytes

    def read(source, *args):
        payload = original(source, *args)
        source.write_bytes(b"the plan changed after the bounded snapshot")
        return payload

    monkeypatch.setattr(benchmark.tasks, "_read_regular_bytes", read)
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert calls == []


def test_changed_plan_ancestor_is_detected_even_if_file_identity_is_preserved(
    tmp_path, monkeypatch
):
    directory = tmp_path / "plan-directory"
    directory.mkdir()
    path = _write_plan(directory)
    file_identity = benchmark.fit_driver._file_identity(path.stat())
    original = benchmark.tasks._read_regular_bytes
    retained = tmp_path / "retained-plan-directory"

    def read(source, *args):
        payload = original(source, *args)
        directory.rename(retained)
        directory.mkdir()
        os.link(retained / source.name, source)
        return payload

    monkeypatch.setattr(benchmark.tasks, "_read_regular_bytes", read)
    calls = _forbid_recovery(monkeypatch)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert calls == []
    assert path.stat().st_ino == (retained / path.name).stat().st_ino
    assert benchmark.fit_driver._file_identity(path.stat()) == file_identity


@pytest.mark.parametrize(
    "field", ["development_only_acknowledged", "sha256_independently_reviewed"]
)
@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_exact_acknowledgements_precede_plan_or_source_reads(tmp_path, monkeypatch, field, value):
    calls = []

    def load(*_args):
        calls.append(True)
        raise AssertionError("invalid acknowledgement reached plan payload")

    monkeypatch.setattr(benchmark, "_load_plan", load)
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(tmp_path / "unread-plan.json", **{field: value})
    assert calls == []


@pytest.mark.parametrize("phase", ["recovery", "scoring"])
def test_cooperative_cancellation_propagates_from_both_phases(tmp_path, monkeypatch, phase):
    path = _write_plan(tmp_path)
    _controlled_route(monkeypatch)
    cancellation = InferenceCancelledError("synthetic cooperative cancellation")

    def cancel(*_args, **_kwargs):
        raise cancellation

    monkeypatch.setattr(
        benchmark,
        "recover_selected_fold_context" if phase == "recovery" else "score_replayed_fold",
        cancel,
    )
    with pytest.raises(InferenceCancelledError) as caught:
        _run(path)
    assert caught.value is cancellation


@pytest.mark.parametrize("phase", ["recovery", "scoring", "output"])
def test_ordinary_failures_drop_messages_context_and_private_recovered_frame_locals(
    tmp_path, monkeypatch, phase
):
    path = _write_plan(tmp_path)
    context, _receipt, calls = _controlled_route(monkeypatch)

    def fail(*_args, **_kwargs):
        raise ValueError("synthetic-private-case-and-source-path")

    target = {
        "recovery": "recover_selected_fold_context",
        "scoring": "score_replayed_fold",
        "output": "canonical_receipt_bytes",
    }[phase]
    monkeypatch.setattr(benchmark, target, fail)
    with pytest.raises(MixtureBenchmarkError) as caught:
        _run(path)
    assert str(caught.value) == _FAILURE
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert "synthetic-private" not in repr(caught.value)
    traceback = caught.value.__traceback__
    public_frames = []
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_code.co_name == "run_selected_fold_benchmark":
            public_frames.append(frame)
            assert all(value is not context for value in frame.f_locals.values())
            assert not any(
                type(value) is SelectedFoldReplayResult for value in frame.f_locals.values()
            )
        traceback = traceback.tb_next
    assert len(public_frames) == 1
    assert sum(call[0] == "recover" for call in calls) == (0 if phase == "recovery" else 1)


def test_receipt_encoder_requires_closed_current_summary_and_exact_output_bound(monkeypatch):
    receipt = _controlled_point_receipt()
    payload = benchmark.canonical_receipt_bytes(receipt)
    assert payload == canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n"
    assert MixtureBenchmarkReceipt.model_validate_json(payload) == receipt
    with pytest.raises(MixtureBenchmarkError):
        benchmark.canonical_receipt_bytes(receipt.model_dump(mode="json"))
    monkeypatch.setattr(benchmark, "MAX_OUTPUT_BYTES", len(payload))
    assert benchmark.canonical_receipt_bytes(receipt) == payload
    monkeypatch.setattr(benchmark, "MAX_OUTPUT_BYTES", len(payload) - 1)
    with pytest.raises(MixtureBenchmarkError, match="output bound"):
        benchmark.canonical_receipt_bytes(receipt)


def test_api_rejects_oversized_output_instead_of_returning_unpublishable_receipt(
    tmp_path, monkeypatch
):
    path = _write_plan(tmp_path)
    _context, receipt, calls = _controlled_route(monkeypatch)
    monkeypatch.setattr(
        benchmark, "MAX_OUTPUT_BYTES", len(benchmark.canonical_receipt_bytes(receipt)) - 1
    )
    with pytest.raises(MixtureBenchmarkError, match=_FAILURE):
        _run(path)
    assert [call[0] for call in calls] == ["recover", "score"]


def test_aggregate_output_has_no_case_parameters_predictions_or_private_identity_fields():
    payload = benchmark.canonical_receipt_bytes(_controlled_point_receipt())
    for name in (
        "signatures",
        "background",
        "hierarchy_concentrations",
        "feature_indices",
        "selected_counts",
        "cases",
        "donor_key",
        "source_path",
        "known_rna_weights",
        "predictions",
        "source_label_count_mass",
    ):
        assert (b'"' + name.encode() + b'"') not in payload
    document = json.loads(payload)
    assert document["policy_selection_performed"] is False
    assert document["calibration_performed"] is False
    assert document["unbiased_performance_established"] is False
    document["predictions"] = []
    with pytest.raises(ValidationError):
        MixtureBenchmarkReceipt.model_validate_json(json.dumps(document))


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


def test_cli_success_dispatches_exact_paths_and_prints_only_canonical_aggregate(
    monkeypatch, capsys
):
    calls = []
    receipt = _controlled_point_receipt()

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return receipt

    monkeypatch.setattr(benchmark, "run_selected_fold_benchmark", run)
    assert benchmark.main(_arguments()) == 0
    captured = capsys.readouterr()
    assert captured.out.encode() == benchmark.canonical_receipt_bytes(receipt)
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


@pytest.mark.parametrize(
    "error",
    [
        MixtureBenchmarkError("synthetic-private"),
        OSError("synthetic-private"),
        ValueError("synthetic-private"),
    ],
)
def test_cli_failure_is_generic_and_has_no_partial_stdout(monkeypatch, capsys, error):
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(benchmark, "run_selected_fold_benchmark", fail)
    assert benchmark.main(_arguments()) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap selected-fold benchmark failed closed\n"


def test_cli_output_bound_failure_writes_no_partial_json(monkeypatch, capsys):
    receipt = _controlled_point_receipt()
    monkeypatch.setattr(benchmark, "run_selected_fold_benchmark", lambda *_a, **_kw: receipt)
    monkeypatch.setattr(benchmark, "MAX_OUTPUT_BYTES", 1)
    assert benchmark.main(_arguments()) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GBmap selected-fold benchmark failed closed\n"


def test_cli_cooperative_cancellation_is_not_mislabeled_as_ordinary_failure(monkeypatch):
    def cancel(*_args, **_kwargs):
        raise InferenceCancelledError("synthetic cooperative cancellation")

    monkeypatch.setattr(benchmark, "run_selected_fold_benchmark", cancel)
    with pytest.raises(InferenceCancelledError):
        benchmark.main(_arguments())


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["synthetic-private", "--private-token"],
        [*_arguments(), "--output", "synthetic-private"],
        [value for value in _arguments() if value != "--acknowledge-development-only"],
    ],
)
def test_cli_usage_errors_do_not_echo_private_paths_or_accept_extra_output_modes(capsys, arguments):
    with pytest.raises(SystemExit) as caught:
        benchmark.main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: selected-fold benchmark arguments were not accepted\n"


def test_direct_script_help_has_no_input_or_fitting_side_effect(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["benchmark-gbmap-selected-fold", "--help"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(benchmark.__file__, run_name="__main__")
    assert caught.value.code == 0
    captured = capsys.readouterr()
    assert "--plan" in captured.out
    assert "--output" not in captured.out
    assert captured.err == ""
