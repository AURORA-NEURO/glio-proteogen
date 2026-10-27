"""Local execution CLI dispatch, private errors and honest failure-status oracles."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    DiscoveryInputs,
    LockedInput,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution import execution
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import (
    ExecutionError,
    ExecutionPolicy,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import (
    CLINICAL_ROLES,
    ExecutionInputs,
)
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service
from tools import evaluate_cptac_gbm_rna_purity_execution as cli

_RAW_SHA = "a" * 64
_PROTOCOL = "sha256:" + "b" * 64
_PRIVATE = "SYNTHETIC_PRIVATE_SPECIMEN_937514"


@pytest.fixture(autouse=True)
def no_actual_inference(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("CLI dispatch test invoked a real model or private data source")

    for module, name in (
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "_input_vector"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
        (execution, "read_verified_source"),
    ):
        monkeypatch.setattr(module, name, forbidden)


def _inputs(tmp_path):
    lock = SourceLock(1, "c" * 32, "d" * 64)
    return ExecutionInputs(
        discovery=DiscoveryInputs(
            choices_path=tmp_path / "choices.json",
            choices_sha256=_RAW_SHA,
            map_bindings_path=tmp_path / "map.json",
            map_bindings_sha256=_RAW_SHA,
            files_manifest_path=tmp_path / "files.json",
            files_manifest_sha256=_RAW_SHA,
            hgnc_path=tmp_path / "hgnc.tsv",
        ),
        gencode_gtf_path=tmp_path / "reference/gencode.gz",
        gencode_hgnc_path=tmp_path / "reference/hgnc.gz",
        author_feature_path=tmp_path / "reference/author.csv",
        clinical_sources=tuple(LockedInput(tmp_path / role, lock) for role in CLINICAL_ROLES),
        processing_source=LockedInput(tmp_path / "processing.html", lock),
        policy=ExecutionPolicy(
            research_use_only=True,
            caller_authorizes_missing_gene_zero_fill=True,
            allow_limited_support=True,
        ),
    )


def _command(name, tmp_path):
    args = [name, "--inputs", str(tmp_path / (_PRIVATE + ".json")), "--inputs-sha256", _RAW_SHA]
    if name == "execute":
        args.extend(
            [
                "--expected-protocol-digest",
                _PROTOCOL,
                "--output-dir",
                str(tmp_path / "fresh-output"),
            ]
        )
    return args


def _forbid(*_args, **_kwargs):
    pytest.fail("CLI crossed an unrelated command boundary")


def _success(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_real_profile_needs_no_private_inputs_or_model_calls(monkeypatch, capsys):
    for name in ("load_inputs", "frozen_protocol", "evaluate_execution", "verify_execution"):
        monkeypatch.setattr(cli, name, _forbid)
    assert cli.main(["profile"]) == 0
    result = _success(capsys)
    assert result["profile_id"] == "cptac-gbm-native-star-purity-execution/1.0.0"
    assert result["model_profile_id"] == "gbm-rna-tumor-purity/1.0.0"
    assert result["model_features"] == 5829
    assert result["source_hold_precedes_assay_read"] is True
    assert result["individual_results_exported"] is False
    assert "source_bindings" in result
    assert "counts" not in result and "sample_id" not in result


def test_prepare_passes_exact_private_config_lock_and_owned_inputs(monkeypatch, capsys, tmp_path):
    expected = _inputs(tmp_path)
    calls = []

    def load(path, *, sha256):
        calls.append(("load", path, sha256))
        return expected

    def prepare(inputs):
        assert inputs is expected
        calls.append(("prepare",))
        return {"protocol_digest": _PROTOCOL}

    monkeypatch.setattr(cli, "load_inputs", load)
    monkeypatch.setattr(cli, "frozen_protocol", prepare)
    for name in ("profile", "evaluate_execution", "verify_execution"):
        monkeypatch.setattr(cli, name, _forbid)
    assert cli.main(_command("prepare", tmp_path)) == 0
    assert calls == [("load", tmp_path / (_PRIVATE + ".json"), _RAW_SHA), ("prepare",)]
    assert _success(capsys) == {"protocol_digest": _PROTOCOL}


def test_execute_passes_exact_protocol_and_output_after_one_config_load(
    monkeypatch, capsys, tmp_path
):
    expected = _inputs(tmp_path)
    calls = []

    def load(path, *, sha256):
        calls.append(("load", path, sha256))
        return expected

    def execute(inputs, *, output_dir, expected_protocol_digest):
        assert inputs is expected
        calls.append(("execute", output_dir, expected_protocol_digest))
        return {"complete": True, "planned_files": 72, "model_executions": 0}

    monkeypatch.setattr(cli, "load_inputs", load)
    monkeypatch.setattr(cli, "evaluate_execution", execute)
    for name in ("profile", "frozen_protocol", "verify_execution"):
        monkeypatch.setattr(cli, name, _forbid)
    assert cli.main(_command("execute", tmp_path)) == 0
    assert calls == [
        ("load", tmp_path / (_PRIVATE + ".json"), _RAW_SHA),
        ("execute", tmp_path / "fresh-output", _PROTOCOL),
    ]
    assert _success(capsys) == {"complete": True, "planned_files": 72, "model_executions": 0}


def test_verify_dispatches_only_saved_directory(monkeypatch, capsys, tmp_path):
    directory = tmp_path / "saved-aggregate"
    calls = []

    def verify(path):
        calls.append(path)
        return {
            "verified": True,
            "raw_sources_reparsed": False,
            "models_executed_by_verifier": False,
        }

    for name in ("profile", "load_inputs", "evaluate_execution", "frozen_protocol"):
        monkeypatch.setattr(cli, name, _forbid)
    monkeypatch.setattr(cli, "verify_execution", verify)
    assert cli.main(["verify", str(directory)]) == 0
    assert calls == [directory]
    assert _success(capsys) == {
        "verified": True,
        "raw_sources_reparsed": False,
        "models_executed_by_verifier": False,
    }


@pytest.mark.parametrize("command", ["profile", "prepare", "execute", "verify"])
@pytest.mark.parametrize(
    "error_type", [ExecutionError, FileNotFoundError, PermissionError, RuntimeError]
)
def test_operational_failure_hides_private_rows_paths_and_does_not_claim_zero_model_execution(
    command, error_type, monkeypatch, capsys, tmp_path
):
    def failure(*_args, **_kwargs):
        message = str(tmp_path / _PRIVATE) + " PRIVATE_ROW_VALUE=937514"
        raise error_type(message)

    monkeypatch.setattr(cli, "profile", failure)
    monkeypatch.setattr(cli, "verify_execution", failure)
    monkeypatch.setattr(cli, "load_inputs", lambda _path, *, sha256: _inputs(tmp_path))
    monkeypatch.setattr(cli, "frozen_protocol", failure)
    monkeypatch.setattr(cli, "evaluate_execution", failure)
    args = (
        [command]
        if command == "profile"
        else (
            ["verify", str(tmp_path / _PRIVATE)]
            if command == "verify"
            else _command(command, tmp_path)
        )
    )
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert _PRIVATE not in captured.out and str(tmp_path) not in captured.out
    assert "PRIVATE_ROW_VALUE" not in captured.out and "Traceback" not in captured.out
    result = json.loads(captured.out)
    assert result["complete"] is False
    assert result["error_category"] == error_type.__name__
    assert result["model_execution_status"] == "not_reported"
    assert "models_executed" not in result and "model_executions" not in result


def test_failure_after_execution_started_preserves_unreported_model_status(
    monkeypatch, capsys, tmp_path
):
    events = []
    monkeypatch.setattr(cli, "load_inputs", lambda _path, *, sha256: _inputs(tmp_path))

    def execute(_inputs, **_kwargs):
        events.append("synthetic_model_work_already_started")
        message = "synthetic later failure " + _PRIVATE
        raise RuntimeError(message)

    monkeypatch.setattr(cli, "evaluate_execution", execute)
    assert cli.main(_command("execute", tmp_path)) == 1
    assert events == ["synthetic_model_work_already_started"]
    result = _success(capsys)
    assert result["model_execution_status"] == "not_reported"
    assert "models_executed" not in result and "model_executions" not in result


@pytest.mark.parametrize("command", ["prepare", "execute"])
def test_config_loader_failure_precedes_prepare_or_execution_dispatch(
    command, monkeypatch, capsys, tmp_path
):
    def loader(*_args, **_kwargs):
        raise ExecutionError(_PRIVATE)

    monkeypatch.setattr(cli, "load_inputs", loader)
    monkeypatch.setattr(cli, "frozen_protocol", _forbid)
    monkeypatch.setattr(cli, "evaluate_execution", _forbid)
    assert cli.main(_command(command, tmp_path)) == 1
    result = _success(capsys)
    assert result["error_category"] == "ExecutionError"
    assert result["model_execution_status"] == "not_reported"


@pytest.mark.parametrize(
    "args",
    [
        [],
        [_PRIVATE],
        ["profile", "--unrecognized", _PRIVATE],
        ["execute", "--inputs", _PRIVATE],
        ["verify", _PRIVATE, "--predict", _PRIVATE],
        ["analyze", _PRIVATE],
        ["train", _PRIVATE],
        ["score", _PRIVATE],
    ],
)
def test_usage_errors_hide_private_argv_and_report_no_execution_status(args, capsys, monkeypatch):
    for name in (
        "profile",
        "load_inputs",
        "frozen_protocol",
        "evaluate_execution",
        "verify_execution",
    ):
        monkeypatch.setattr(cli, name, _forbid)
    with pytest.raises(SystemExit) as stopped:
        cli.main(args)
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == "" and _PRIVATE not in captured.out
    result = json.loads(captured.out)
    assert result["error_category"] == "UsageError" and result["complete"] is False
    assert result["model_execution_status"] == "not_reported"
    assert "models_executed" not in result


@pytest.mark.parametrize("command", [None, "profile", "prepare", "execute", "verify"])
def test_help_is_successful_and_does_not_load_inputs(command, monkeypatch, capsys):
    for name in (
        "profile",
        "load_inputs",
        "frozen_protocol",
        "evaluate_execution",
        "verify_execution",
    ):
        monkeypatch.setattr(cli, name, _forbid)
    with pytest.raises(SystemExit) as stopped:
        cli.main(([command] if command else []) + ["--help"])
    assert stopped.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_main_accepts_standard_sys_argv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["purity-execution", "profile"])
    monkeypatch.setattr(cli, "profile", lambda: {"synthetic_profile": True})
    assert cli.main() == 0
    assert _success(capsys) == {"synthetic_profile": True}


def test_script_entry_point_exits_with_main_status_without_actual_work(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["purity-execution", "profile"])
    monkeypatch.setattr(execution, "profile", lambda: {"synthetic_entry_point": True})
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(cli.__file__)), run_name="__main__")
    assert stopped.value.code == 0
    assert _success(capsys) == {"synthetic_entry_point": True}


def _config():
    source = {"path": "metadata/source.bin", "bytes": 1, "md5": "c" * 32, "sha256": "d" * 64}
    return {
        "schema_version": "cptac-gbm-rna-purity-execution-inputs/1.0.0",
        "discovery": {
            "choices_path": "metadata/choices.json",
            "choices_sha256": _RAW_SHA,
            "map_bindings_path": "metadata/map.json",
            "map_bindings_sha256": _RAW_SHA,
            "files_manifest_path": "metadata/files.json",
            "files_manifest_sha256": _RAW_SHA,
        },
        "hgnc_path": "reference/hgnc.tsv",
        "references": {
            "gencode_gtf": "reference/gencode.gz",
            "gencode_hgnc": "reference/hgnc.gz",
            "author_features": "reference/author.csv",
        },
        "clinical_sources": dict.fromkeys(CLINICAL_ROLES, source),
        "processing_source": source,
        "policy": {
            "research_use_only": True,
            "caller_authorizes_missing_gene_zero_fill": True,
            "allow_limited_support": True,
        },
    }


def test_real_private_config_hash_and_relative_paths_are_checked_before_prepare(
    tmp_path, monkeypatch, capsys
):
    payload = json.dumps(_config()).encode()
    path = tmp_path / (_PRIVATE + ".json")
    path.write_bytes(payload)
    calls = []

    def prepare(inputs):
        assert type(inputs) is ExecutionInputs
        assert inputs.discovery.choices_path == tmp_path / "metadata/choices.json"
        assert inputs.gencode_gtf_path == tmp_path / "reference/gencode.gz"
        assert inputs.policy.allow_limited_support is True
        calls.append(inputs)
        return {"protocol_digest": _PROTOCOL}

    monkeypatch.setattr(cli, "frozen_protocol", prepare)
    args = [
        "prepare",
        "--inputs",
        str(path),
        "--inputs-sha256",
        hashlib.sha256(payload).hexdigest(),
    ]
    assert cli.main(args) == 0 and len(calls) == 1
    assert _success(capsys) == {"protocol_digest": _PROTOCOL}
    args[-1] = "0" * 64
    assert cli.main(args) == 1 and len(calls) == 1
    result = _success(capsys)
    assert result["model_execution_status"] == "not_reported"
    assert _PRIVATE not in json.dumps(result)


def test_real_missing_config_failure_is_sanitized(tmp_path, capsys):
    assert cli.main(_command("prepare", tmp_path)) == 1
    captured = capsys.readouterr()
    assert str(tmp_path) not in captured.out + captured.err
    assert _PRIVATE not in captured.out + captured.err
    assert json.loads(captured.out)["model_execution_status"] == "not_reported"
