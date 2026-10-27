"""Local CLI dispatch, private-error and no-inference boundaries."""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

from glio_proteogen.research.cptac_gbm_rna_purity_admission.contracts import AdmissionError
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import DiscoveryInputs
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service
from tools import evaluate_cptac_gbm_rna_purity_preflight as cli

_RAW_SHA = "a" * 64
_PROTOCOL = "sha256:" + "b" * 64
_PRIVATE = "SYNTHETIC_PRIVATE_SPECIMEN_937514"


@pytest.fixture(autouse=True)
def no_inference(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("input preflight invoked model loading, preprocessing or inference")

    for module, name in (
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "_input_vector"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
    ):
        monkeypatch.setattr(module, name, forbidden)


def _command(name, tmp_path):
    result = [name, "--inputs", str(tmp_path / (_PRIVATE + ".json")), "--inputs-sha256", _RAW_SHA]
    if name == "preflight":
        result.extend(
            [
                "--expected-protocol-digest",
                _PROTOCOL,
                "--output-dir",
                str(tmp_path / "fresh-output"),
            ]
        )
    return result


def _inputs(tmp_path):
    return DiscoveryInputs(
        choices_path=tmp_path / "choices.json",
        choices_sha256=_RAW_SHA,
        map_bindings_path=tmp_path / "map.json",
        map_bindings_sha256=_RAW_SHA,
        files_manifest_path=tmp_path / "files.json",
        files_manifest_sha256=_RAW_SHA,
        hgnc_path=tmp_path / "hgnc.tsv",
    )


def _forbid(*_args, **_kwargs):
    pytest.fail("CLI crossed an unrelated command boundary")


def test_real_profile_needs_no_private_inputs_or_model_calls(monkeypatch, capsys):
    for name in ("load_inputs", "frozen_protocol", "evaluate_preflight", "verify_preflight"):
        monkeypatch.setattr(cli, name, _forbid)
    assert cli.main(["profile"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert not captured.err
    assert result["profile_id"] == "cptac-gbm-native-star-purity-preflight/1.0.0"
    assert result["model_features"] == 5829
    assert result["minimum_recognized_features"] == 4664
    assert result["coverage_supported_features"] == 5771
    assert result["models_executed"] is result["inference_requests_constructed"] is False
    assert "source_bindings" in result
    assert "counts" not in result and "sample_id" not in result


def test_prepare_passes_exact_config_lock_without_reading_counts(monkeypatch, capsys, tmp_path):
    expected = _inputs(tmp_path)
    calls = []

    def load(path, *, sha256):
        calls.append(("load", path, sha256))
        return expected

    def prepare(inputs):
        assert inputs is expected
        calls.append(("prepare",))
        return {"protocol_digest": _PROTOCOL, "models_executed": False}

    monkeypatch.setattr(cli, "load_inputs", load)
    monkeypatch.setattr(cli, "frozen_protocol", prepare)
    monkeypatch.setattr(cli, "evaluate_preflight", _forbid)
    monkeypatch.setattr(cli, "verify_preflight", _forbid)
    assert cli.main(_command("prepare", tmp_path)) == 0
    assert calls == [("load", tmp_path / (_PRIVATE + ".json"), _RAW_SHA), ("prepare",)]
    result = json.loads(capsys.readouterr().out)
    assert result == {"protocol_digest": _PROTOCOL, "models_executed": False}


def test_preflight_passes_frozen_digest_and_fresh_output_without_preparing_again(
    monkeypatch, capsys, tmp_path
):
    expected = _inputs(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_inputs", lambda _path, *, sha256: expected)

    def evaluate(inputs, *, output_dir, expected_protocol_digest):
        assert inputs is expected
        calls.append((output_dir, expected_protocol_digest))
        return {"complete": True, "planned_files": 72, "models_executed": False}

    monkeypatch.setattr(cli, "evaluate_preflight", evaluate)
    monkeypatch.setattr(cli, "frozen_protocol", _forbid)
    assert cli.main(_command("preflight", tmp_path)) == 0
    assert calls == [(tmp_path / "fresh-output", _PROTOCOL)]
    assert json.loads(capsys.readouterr().out) == {
        "complete": True,
        "planned_files": 72,
        "models_executed": False,
    }


def test_verify_dispatch_reads_only_saved_aggregate_directory(monkeypatch, capsys, tmp_path):
    directory = tmp_path / "saved-aggregate"
    calls = []

    def verify(path):
        calls.append(path)
        return {
            "verified": True,
            "raw_sources_reparsed": False,
            "models_executed": False,
            "verification_scope": "saved_aggregate_integrity_and_conservation",
        }

    for name in ("load_inputs", "evaluate_preflight", "frozen_protocol"):
        monkeypatch.setattr(cli, name, _forbid)
    monkeypatch.setattr(cli, "verify_preflight", verify)
    assert cli.main(["verify", str(directory)]) == 0
    assert calls == [directory]
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] is True and result["raw_sources_reparsed"] is False
    assert result["verification_scope"] == "saved_aggregate_integrity_and_conservation"


@pytest.mark.parametrize("command", ["profile", "prepare", "preflight", "verify"])
@pytest.mark.parametrize(
    "error_type", [AdmissionError, FileNotFoundError, PermissionError, RuntimeError]
)
def test_all_operational_failures_hide_private_paths_rows_and_exception_messages(
    command, error_type, monkeypatch, capsys, tmp_path
):
    def fail(*_args, **_kwargs):
        raise error_type(str(tmp_path / _PRIVATE) + " PRIVATE_ROW_VALUE=937514")

    monkeypatch.setattr(cli, "profile", fail)
    monkeypatch.setattr(cli, "verify_preflight", fail)
    monkeypatch.setattr(cli, "load_inputs", lambda _path, *, sha256: _inputs(tmp_path))
    monkeypatch.setattr(cli, "frozen_protocol", fail)
    monkeypatch.setattr(cli, "evaluate_preflight", fail)
    arguments = (
        [command]
        if command == "profile"
        else (
            ["verify", str(tmp_path / _PRIVATE)]
            if command == "verify"
            else _command(command, tmp_path)
        )
    )
    assert cli.main(arguments) == 1
    captured = capsys.readouterr()
    assert _PRIVATE not in captured.out + captured.err
    assert str(tmp_path) not in captured.out + captured.err
    assert "PRIVATE_ROW_VALUE" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    result = json.loads(captured.out)
    assert result["complete"] is result["models_executed"] is False
    assert result["error_category"] == error_type.__name__


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        [_PRIVATE],
        ["profile", "--unrecognized", _PRIVATE],
        ["preflight", "--inputs", _PRIVATE],
        ["verify", _PRIVATE, "--predict", _PRIVATE],
        ["analyze", _PRIVATE],
        ["train", _PRIVATE],
        ["score", _PRIVATE],
    ],
)
def test_usage_errors_are_fixed_json_without_echoing_private_argv(arguments, capsys):
    with pytest.raises(SystemExit) as captured_exit:
        cli.main(arguments)
    assert captured_exit.value.code == 2
    captured = capsys.readouterr()
    assert _PRIVATE not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    result = json.loads(captured.err or captured.out)
    assert result["complete"] is result["models_executed"] is False
    assert result["error_category"] == "UsageError"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["profile", "--help"],
        ["prepare", "--help"],
        ["preflight", "--help"],
        ["verify", "--help"],
    ],
)
def test_help_remains_successful_without_loading_inputs(arguments, monkeypatch, capsys):
    for name in (
        "load_inputs",
        "profile",
        "frozen_protocol",
        "evaluate_preflight",
        "verify_preflight",
    ):
        monkeypatch.setattr(cli, name, _forbid)
    with pytest.raises(SystemExit) as captured_exit:
        cli.main(arguments)
    assert captured_exit.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_main_uses_standard_sys_argv_when_none_given(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["purity-preflight", "profile"])
    monkeypatch.setattr(cli, "profile", lambda: {"models_executed": False})
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out) == {"models_executed": False}


def test_real_missing_input_config_failure_is_sanitized(tmp_path, capsys):
    assert cli.main(_command("prepare", tmp_path)) == 1
    captured = capsys.readouterr()
    assert (
        _PRIVATE not in captured.out + captured.err
        and str(tmp_path) not in captured.out + captured.err
    )
    assert json.loads(captured.out)["models_executed"] is False


def test_real_config_loader_validates_hash_and_paths_before_prepare_dispatch(
    tmp_path, monkeypatch, capsys
):
    document = {
        "schema_version": "cptac-gbm-rna-purity-inputs/1.0.0",
        "discovery": {
            "choices_path": "metadata/choices.json",
            "choices_sha256": _RAW_SHA,
            "map_bindings_path": "metadata/map.json",
            "map_bindings_sha256": _RAW_SHA,
            "files_manifest_path": "metadata/files.json",
            "files_manifest_sha256": _RAW_SHA,
        },
        "hgnc_path": "reference/hgnc.tsv",
        "context_evidence": None,
        "context_sources": [],
    }
    payload = json.dumps(document).encode()
    path = tmp_path / (_PRIVATE + ".json")
    path.write_bytes(payload)
    calls = []

    def prepared(inputs):
        calls.append(inputs)
        assert type(inputs) is DiscoveryInputs
        assert inputs.choices_path == tmp_path / "metadata/choices.json"
        assert inputs.hgnc_path == tmp_path / "reference/hgnc.tsv"
        return {"protocol_digest": _PROTOCOL, "models_executed": False}

    monkeypatch.setattr(cli, "frozen_protocol", prepared)
    arguments = [
        "prepare",
        "--inputs",
        str(path),
        "--inputs-sha256",
        hashlib.sha256(payload).hexdigest(),
    ]
    assert cli.main(arguments) == 0 and len(calls) == 1
    assert _PRIVATE not in capsys.readouterr().out
    arguments[-1] = "0" * 64
    assert cli.main(arguments) == 1 and len(calls) == 1
    assert _PRIVATE not in capsys.readouterr().out
