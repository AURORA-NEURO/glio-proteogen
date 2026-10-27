"""Synthetic review orchestration and CLI checks without assays or model execution."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import runpy
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    DiscoveryInputs,
    LockedInput,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution import execution, native_counts
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import (
    ExecutionError,
    ExecutionPolicy,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import (
    CLINICAL_ROLES,
    ExecutionInputs,
)
from glio_proteogen.research.cptac_gbm_rna_purity_resolution import review as r
from glio_proteogen.research.cptac_gbm_rna_purity_resolution.contracts import (
    ResolutionError,
    canonical_bytes,
    digest,
    seal_document,
)
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service
from tests.research.test_cptac_rna_purity_resolution_receipts import _source_document
from tools import evaluate_cptac_gbm_clinical_resolution as cli

_PRIVATE = "SYNTHETIC_PRIVATE_CLINICAL_CASE_826415"
_RAW_SHA = "a" * 64
_OTHER = "sha256:" + "f" * 64


def _forbidden(*_args, **_kwargs):
    pytest.fail("clinical review crossed an assay, model, or unrelated command boundary")


@pytest.fixture(autouse=True)
def no_assays_or_model(monkeypatch):
    for module, name in (
        (execution, "read_verified_source"),
        (native_counts, "project_native_star_counts"),
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "_input_vector"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
    ):
        monkeypatch.setattr(module, name, _forbidden)


def _baseline_inputs(tmp):
    lock = SourceLock(1, "1" * 32, "2" * 64)
    return ExecutionInputs(
        discovery=DiscoveryInputs(
            choices_path=tmp / "choices.json",
            choices_sha256="1" * 64,
            map_bindings_path=tmp / "mapping.json",
            map_bindings_sha256="2" * 64,
            files_manifest_path=tmp / "assays" / "files.json",
            files_manifest_sha256="3" * 64,
            hgnc_path=tmp / "hgnc.tsv",
        ),
        gencode_gtf_path=tmp / "gencode.gz",
        gencode_hgnc_path=tmp / "gencode-hgnc.gz",
        author_feature_path=tmp / "author-axis.csv",
        clinical_sources=tuple(LockedInput(tmp / role, lock) for role in CLINICAL_ROLES),
        processing_source=LockedInput(tmp / "workflow.html", lock),
        policy=ExecutionPolicy(
            research_use_only=True,
            caller_authorizes_missing_gene_zero_fill=True,
            allow_limited_support=False,
        ),
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    private_root = tmp_path / _PRIVATE
    private_root.mkdir()
    (private_root / "assays").mkdir()
    source_path = private_root / "author-source.xlsx"
    source_path.write_bytes(b"x" * r.SOURCE_LOCK.bytes)
    inputs = r.ResolutionInputs(
        baseline=_baseline_inputs(private_root), source=LockedInput(source_path, r.SOURCE_LOCK)
    )
    files = {
        f"synthetic-{kind}-{index}": SimpleNamespace(
            relative_path=f"{kind}-{index}.tsv",
            lock=SourceLock(1, "0" * 32, hashlib.sha256(f"{kind}-{index}".encode()).hexdigest()),
        )
        for index in range(72)
        for kind in ("rna", "cnv")
    }
    plan = SimpleNamespace(files=files)
    baseline_profile = execution.profile()
    baseline = SimpleNamespace(
        clinical=SimpleNamespace(
            receipt=SimpleNamespace(
                receipt_digest=digest("synthetic-baseline-clinical"),
                ordered_axis_digest=digest("synthetic-complete-case-axis"),
            )
        ),
        protocol=SimpleNamespace(protocol_digest=digest("synthetic-baseline-protocol")),
        profile_document=baseline_profile,
    )
    stats = _source_document()
    stats.pop("source_receipt_digest")
    stats.update(
        resolution_evidence_digest=digest("synthetic-private-reviewed-rows"),
        ordered_target_bindings_digest=digest("synthetic-target-lineage"),
    )
    calls = []

    def prepare(baseline_inputs):
        assert baseline_inputs == inputs.baseline
        calls.append("baseline")
        return baseline

    def reader(path, lock, *, max_bytes):
        assert path == inputs.source.path
        assert lock == r.SOURCE_LOCK and max_bytes >= lock.bytes
        calls.append("clinical-source")
        return b"synthetic-reviewed-clinical-bytes"

    def review_source(clinical, payload):
        assert clinical is baseline.clinical
        assert payload == b"synthetic-reviewed-clinical-bytes"
        calls.append("source-review")
        return SimpleNamespace(aggregate_bytes=canonical_bytes(stats))

    monkeypatch.setattr(r, "load_discovery_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(r, "_prepare", prepare)
    monkeypatch.setattr(r, "read_verified_source", reader)
    monkeypatch.setattr(r, "review_source", review_source)
    return SimpleNamespace(
        inputs=inputs, baseline=baseline, stats=stats, plan=plan, calls=calls, tmp=tmp_path
    )


def _run(setup, name="review"):
    protocol = r.prepare_review(setup.inputs)
    output = setup.tmp / name
    result = r.evaluate_review(
        setup.inputs, output_dir=output, expected_protocol_digest=protocol["receipt_digest"]
    )
    return output, result


def _rewrite(path, changes, seal=None):
    document = json.loads(path.read_bytes())
    document.update(changes)
    if seal:
        document = seal_document(document, seal)
    path.write_bytes(canonical_bytes(document) + b"\n")


def test_prepare_is_metadata_only_and_wrong_freeze_creates_no_output(setup):
    protocol = r.prepare_review(setup.inputs)
    assert setup.calls == ["baseline", "clinical-source", "source-review"]
    assert protocol["baseline_protocol_digest"] == setup.baseline.protocol.protocol_digest
    assert protocol["baseline_profile_digest"] == setup.baseline.profile_document["profile_digest"]
    assert (
        protocol["baseline_clinical_receipt_digest"]
        == setup.baseline.clinical.receipt.receipt_digest
    )
    with pytest.raises(ResolutionError, match="changed"):
        r.evaluate_review(
            setup.inputs, output_dir=setup.tmp / "not-created", expected_protocol_digest=_OTHER
        )
    assert not (setup.tmp / "not-created").exists()


def test_review_repeats_deterministically_and_exports_only_complete_aggregate_proof(setup):
    first, result = _run(setup, "first")
    second, repeated = _run(setup, "second")
    assert result == repeated == r.verify_review(first)
    assert result["verification_kind"] == "saved_aggregate_integrity"
    assert result["complete"] is True and result["source_qualified_cases"] == 0
    assert result["rna_read"] is result["model_executed"] is False
    assert result["individual_results_exported"] is False
    assert {path.name for path in first.iterdir()} == r._ARTIFACTS
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
        assert _PRIVATE.encode() not in path.read_bytes()
        assert b"synthetic-private" not in path.read_bytes()
    monkeypatch_free_verify = setup.calls.copy()
    r.verify_review(first)
    assert setup.calls == monkeypatch_free_verify


@pytest.mark.parametrize("which", ["baseline", "rna", "cnv"])
def test_source_path_role_alias_is_rejected_before_baseline_or_new_source_read(setup, which):
    if which == "baseline":
        target = setup.inputs.baseline.discovery.hgnc_path
    else:
        target = setup.inputs.baseline.discovery.files_manifest_path.parent / f"{which}-0.tsv"
    target.write_bytes(b"x" * r.SOURCE_LOCK.bytes)
    inputs = replace(setup.inputs, source=LockedInput(target, r.SOURCE_LOCK))
    with pytest.raises(ResolutionError, match="overlaps"):
        r.prepare_review(inputs)
    assert setup.calls == []


def test_all_assay_hashes_are_protected_independently_from_paths(setup):
    binding = setup.plan.files["synthetic-cnv-71"]
    binding.lock = r.SOURCE_LOCK
    with pytest.raises(ResolutionError, match="overlaps"):
        r.prepare_review(setup.inputs)
    assert setup.calls == []


def test_hardlinked_source_role_is_rejected_before_payload_read(setup):
    target = setup.inputs.baseline.discovery.hgnc_path
    target.write_bytes(b"x" * r.SOURCE_LOCK.bytes)
    setup.inputs.source.path.unlink()
    os.link(target, setup.inputs.source.path)
    with pytest.raises(ResolutionError, match="overlaps"):
        r.prepare_review(setup.inputs)
    assert setup.calls == []


def test_wrong_source_size_fails_before_baseline_and_payload_read(setup):
    setup.inputs.source.path.write_bytes(b"invalid")
    with pytest.raises(ResolutionError, match="size"):
        r.prepare_review(setup.inputs)
    assert setup.calls == []


def test_inputs_are_private_closed_and_revalidate_corrupted_source_lock(setup):
    assert _PRIVATE not in repr(setup.inputs)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(setup.inputs)
    with pytest.raises(ResolutionError):
        r.ResolutionInputs(object(), setup.inputs.source)
    with pytest.raises(ResolutionError):
        r.ResolutionInputs(setup.inputs.baseline, object())
    with pytest.raises(ResolutionError, match="lock"):
        replace(
            setup.inputs,
            source=LockedInput(setup.inputs.source.path, SourceLock(1, "a" * 32, "b" * 64)),
        )
    with pytest.raises(ResolutionError):
        r.prepare_review(object())
    object.__setattr__(setup.inputs.source, "lock", SourceLock(1, "a" * 32, "b" * 64))
    with pytest.raises(ResolutionError):
        r.prepare_review(setup.inputs)
    assert setup.calls == []


def test_source_error_stops_before_output(setup, monkeypatch):
    def fail(*_args, **_kwargs):
        raise ExecutionError("rejected")

    monkeypatch.setattr(r, "review_source", fail)
    with pytest.raises(ExecutionError):
        r.evaluate_review(
            setup.inputs, output_dir=setup.tmp / "not-created", expected_protocol_digest=_OTHER
        )
    assert not (setup.tmp / "not-created").exists()


def test_existing_or_measurement_output_is_rejected(setup):
    protocol = r.prepare_review(setup.inputs)
    for output in (
        setup.tmp,
        setup.inputs.baseline.discovery.files_manifest_path.parent / "review",
    ):
        with pytest.raises(ExecutionError):
            r.evaluate_review(
                setup.inputs, output_dir=output, expected_protocol_digest=protocol["receipt_digest"]
            )


def test_write_failure_leaves_no_complete_saved_review(setup, monkeypatch):
    protocol = r.prepare_review(setup.inputs)
    original = r._write

    def fail_last(path, document):
        if path.name == "resolution.json":
            raise OSError("write")
        original(path, document)

    monkeypatch.setattr(r, "_write", fail_last)
    output = setup.tmp / "interrupted"
    with pytest.raises(OSError):
        r.evaluate_review(
            setup.inputs, output_dir=output, expected_protocol_digest=protocol["receipt_digest"]
        )
    assert not (output / "resolution.json").exists()
    with pytest.raises((ResolutionError, ExecutionError, ValueError)):
        r.verify_review(output)


@pytest.mark.parametrize(
    ("name", "field", "seal"),
    [
        ("source.json", "source_qualified_cases", "source_receipt_digest"),
        ("resolution.json", "eligibility_admitted", "receipt_digest"),
        ("protocol.json", "source_receipt_digest", "receipt_digest"),
        ("protocol.json", "resolution_receipt_digest", "receipt_digest"),
        ("protocol.json", "baseline_clinical_receipt_digest", "receipt_digest"),
        ("resolution.json", "source_receipt_digest", "receipt_digest"),
    ],
)
def test_resealed_invalid_claims_and_cross_receipts_are_rejected(setup, name, field, seal):
    output, _ = _run(setup)
    value = (
        1
        if field == "source_qualified_cases"
        else True
        if field == "eligibility_admitted"
        else _OTHER
    )
    _rewrite(output / name, {field: value}, seal)
    with pytest.raises(ResolutionError):
        r.verify_review(output)


def test_profile_scalar_alias_cannot_preserve_a_stale_method_seal(setup):
    output, _ = _run(setup)
    _rewrite(output / "profile.json", {"rna_read": 0})
    with pytest.raises(ResolutionError):
        r.verify_review(output)


def test_inherited_baseline_method_binding_is_checked_when_saved_review_is_verified(setup):
    output, _ = _run(setup)
    _rewrite(output / "protocol.json", {"baseline_profile_digest": _OTHER}, "receipt_digest")
    with pytest.raises(ResolutionError):
        r.verify_review(output)


@pytest.mark.parametrize("change", ["format", "extra", "missing", "seal"])
def test_saved_directory_and_canonical_artifact_requirements(setup, change):
    output, _ = _run(setup)
    path = output / "source.json"
    if change == "format":
        path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2))
    elif change == "extra":
        (output / "private-rows.json").write_text("[]")
    elif change == "missing":
        path.unlink()
    else:
        _rewrite(path, {"source_receipt_digest": _OTHER})
    with pytest.raises((ResolutionError, ExecutionError, ValueError)):
        r.verify_review(output)


def _config(setup):
    return {
        "schema_version": "cptac-gbm-clinical-gap-review-inputs/1.0.0",
        "baseline_inputs": {"path": "baseline.json", "sha256": _RAW_SHA},
        "clinical_source": {
            "path": str(setup.inputs.source.path),
            "bytes": r.SOURCE_LOCK.bytes,
            "md5": r.SOURCE_LOCK.md5,
            "sha256": r.SOURCE_LOCK.sha256,
        },
    }


def test_private_config_passes_exact_nested_digest_and_resolved_paths(setup, monkeypatch):
    calls = []

    def loader(path, *, sha256):
        calls.append((path, sha256))
        return setup.inputs.baseline

    monkeypatch.setattr(r, "load_baseline_inputs", loader)
    path = setup.tmp / "private-config.json"
    payload = canonical_bytes(_config(setup))
    path.write_bytes(payload)
    result = r.load_inputs(path, sha256=hashlib.sha256(payload).hexdigest())
    assert result == setup.inputs
    assert calls == [(setup.tmp / "baseline.json", _RAW_SHA)]
    assert setup.calls == []


@pytest.mark.parametrize("change", ["extra", "version", "nested-extra", "escape", "url", "lock"])
def test_private_config_rejects_schema_and_path_role_changes(setup, monkeypatch, change):
    monkeypatch.setattr(r, "load_baseline_inputs", lambda *_args, **_kwargs: setup.inputs.baseline)
    document = _config(setup)
    if change == "extra":
        document["individual_cases"] = [_PRIVATE]
    elif change == "version":
        document["schema_version"] = "other"
    elif change == "nested-extra":
        document["baseline_inputs"]["extra"] = _PRIVATE
    elif change == "escape":
        document["baseline_inputs"]["path"] = "../outside.json"
    elif change == "url":
        document["clinical_source"]["path"] = "https://example.invalid/private"
    else:
        document["clinical_source"]["bytes"] = 1
    path = setup.tmp / "config.json"
    payload = canonical_bytes(document)
    path.write_bytes(payload)
    with pytest.raises(ResolutionError) as error:
        r.load_inputs(path, sha256=hashlib.sha256(payload).hexdigest())
    assert _PRIVATE not in str(error.value)


def test_config_is_hash_verified_and_nested_failure_is_sanitized(setup, monkeypatch):
    path = setup.tmp / "config.json"
    payload = canonical_bytes(_config(setup))
    path.write_bytes(payload)
    with pytest.raises(ResolutionError):
        r.load_inputs(path, sha256="0" * 64)

    def fail(*_args, **_kwargs):
        raise ValueError(_PRIVATE)

    monkeypatch.setattr(r, "load_baseline_inputs", fail)
    with pytest.raises(ResolutionError) as error:
        r.load_inputs(path, sha256=hashlib.sha256(payload).hexdigest())
    assert _PRIVATE not in str(error.value)


def _command(name, tmp):
    args = [name, "--inputs", str(tmp / (_PRIVATE + ".json")), "--inputs-sha256", _RAW_SHA]
    if name == "review":
        args.extend(["--output-dir", str(tmp / "output"), "--expected-protocol-digest", _OTHER])
    return args


@pytest.mark.parametrize("command", ["profile", "prepare", "review", "verify"])
def test_cli_dispatch_preserves_exact_private_arguments(command, tmp_path, monkeypatch, capsys):
    expected_inputs = object()
    calls = []
    result = {"synthetic_aggregate": True}
    for name in ("profile", "prepare_review", "evaluate_review", "verify_review", "load_inputs"):
        monkeypatch.setattr(cli, name, _forbidden)

    def load(path, *, sha256):
        calls.append(("load", path, sha256))
        return expected_inputs

    if command == "profile":
        args = [command]
        monkeypatch.setattr(cli, "profile", lambda: result)
    elif command == "verify":
        args = [command, str(tmp_path / _PRIVATE)]
        monkeypatch.setattr(
            cli, "verify_review", lambda path: calls.append(("verify", path)) or result
        )
    else:
        args = _command(command, tmp_path)
        monkeypatch.setattr(cli, "load_inputs", load)
        if command == "prepare":

            def prepare(inputs):
                assert inputs is expected_inputs
                calls.append(("prepare",))
                return result

            monkeypatch.setattr(cli, "prepare_review", prepare)
        else:

            def evaluate(inputs, *, output_dir, expected_protocol_digest):
                assert inputs is expected_inputs
                calls.append(("review", output_dir, expected_protocol_digest))
                return result

            monkeypatch.setattr(cli, "evaluate_review", evaluate)
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and json.loads(captured.out) == result
    if command in ("prepare", "review"):
        assert calls[0] == ("load", tmp_path / (_PRIVATE + ".json"), _RAW_SHA)
        assert calls[1] == (
            ("prepare",) if command == "prepare" else ("review", tmp_path / "output", _OTHER)
        )
    elif command == "verify":
        assert calls == [("verify", tmp_path / _PRIVATE)]
    else:
        assert calls == []


@pytest.mark.parametrize("command", ["profile", "prepare", "review", "verify"])
def test_cli_failure_sanitizes_private_details_and_does_not_claim_execution_status(
    command, tmp_path, monkeypatch, capsys
):
    def fail(*_args, **_kwargs):
        raise ValueError(_PRIVATE)

    monkeypatch.setattr(cli, "load_inputs", lambda *_args, **_kwargs: object())
    names = {
        "profile": "profile",
        "prepare": "prepare_review",
        "review": "evaluate_review",
        "verify": "verify_review",
    }
    monkeypatch.setattr(cli, names[command], fail)
    args = (
        ["profile"]
        if command == "profile"
        else ["verify", str(tmp_path / _PRIVATE)]
        if command == "verify"
        else _command(command, tmp_path)
    )
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert captured.err == "" and _PRIVATE not in captured.out
    assert result["complete"] is False and result["model_execution_status"] == "not_reported"
    assert "model_executed" not in result and "rna_read" not in result


@pytest.mark.parametrize(
    "args",
    [[], ["invalid"], ["prepare", "--inputs", _PRIVATE], ["verify", _PRIVATE, "--extra", _PRIVATE]],
)
def test_cli_usage_errors_are_private_json(args, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == "" and _PRIVATE not in captured.out
    assert json.loads(captured.out)["error_category"] == "UsageError"


def test_cli_module_entrypoint_exits_successfully_without_private_inputs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(Path(cli.__file__)), "profile"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(cli.__file__)), run_name="__main__")
    assert error.value.code == 0
    assert (
        json.loads(capsys.readouterr().out)["profile_id"] == "cptac-gbm-clinical-gap-review/1.0.0"
    )
