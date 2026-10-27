"""Synthetic runner integration at the exact source-reader boundaries."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.assays import AssayFormatError
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AdmissionPlanError,
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
)
from tests.research.test_cptac_external_coverage import (
    synthetic_assay,
    synthetic_bundle,
    synthetic_protein,
)
from tools import evaluate_cptac_gbm_confirmatory_admission as runner


def _plan():
    candidates = tuple(
        CandidateBinding(
            case_submitter_id=f"synthetic-case-{index:03d}",
            sample_submitter_id=f"synthetic-sample-{index:03d}",
            gdc_sample_uuid=str(UUID(int=1000 + index)),
            protein_aliquot_submitter_id=f"SYNTHETIC-PROTEIN-{55 - index:03d}",
            protein_aliquot_uuid=str(UUID(int=2000 + index)),
            rna_file_id=str(UUID(int=5000 - index)),
            cnv_file_id=str(UUID(int=7000 - index)),
        )
        for index in range(56)
    )
    files = {}
    lock = SourceLock(1, "1" * 32, "2" * 64)
    # The file-map and lexical file-ID orders intentionally differ from the
    # case-sorted authoritative candidate order.
    for candidate in reversed(candidates):
        for file_id, workflow in (
            (candidate.cnv_file_id, "AscatNGS"),
            (candidate.rna_file_id, "STAR - Counts"),
        ):
            files[file_id] = AssayInputBinding(file_id + ".bin", lock, workflow)
    receipt = ExternalAdmissionReceipt(
        profile_id="cptac-gbm-confirmatory-metadata-plan/1.0.0",
        choices_sha256="a" * 64,
        files_manifest_sha256="b" * 64,
        candidate_count=56,
        rna_file_count=56,
        cnv_file_count=56,
        paired_file_count=112,
        manifest_verified_bytes=112,
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=("Synthetic captured metadata; issuer is not authenticated by a digest.",),
    )
    return ExternalAdmissionPlan(candidates, files, receipt)


def _expected_paths(plan, inputs):
    paths = {}
    for index, candidate in enumerate(plan.candidates):
        for family, file_id in (("rna", candidate.rna_file_id), ("cnv", candidate.cnv_file_id)):
            binding = plan.files[file_id]
            paths[inputs["files_manifest_path"].parent / binding.relative_path] = (
                family,
                index,
                binding.lock,
            )
    return paths


def _reader_failure(state, stage, error_type):
    if state["failure"] == stage:
        raise error_type


@pytest.fixture
def harness(tmp_path, monkeypatch):
    plan = _plan()
    protein, rna, cnv = synthetic_bundle(("111", "100", "010", "001", *(("000",) * 52)))
    protein = replace(
        protein,
        candidate_digest=sha256_digest(plan.protein_aliquots),
        receipt=replace(
            protein.receipt,
            candidate_digest=sha256_digest(plan.protein_aliquots),
        ),
    )
    inputs = {
        "choices_path": tmp_path / "private-choices.json",
        "choices_sha256": "a" * 64,
        "files_manifest_path": tmp_path / "private-manifest.json",
        "files_manifest_sha256": "b" * 64,
        "protein_path": tmp_path / "private-protein.tsv",
        "sample_map_path": tmp_path / "private-sample-map.tsv",
        "hgnc_path": tmp_path / "private-reference.tsv",
    }
    state = {"protein": protein, "rna": rna, "cnv": cnv, "failure": None}
    calls = []
    events = []
    hgnc = object()
    state["hgnc"] = hgnc
    real_protocol = runner.frozen_protocol

    def load(**kwargs):
        assert kwargs == {
            key: inputs[key]
            for key in (
                "choices_path",
                "choices_sha256",
                "files_manifest_path",
                "files_manifest_sha256",
            )
        }
        assert not state["output_dir"].exists()
        events.append("plan")
        return plan

    def freeze(**kwargs):
        events.append("protocol")
        protocol = real_protocol(**kwargs)
        state["protocol"] = protocol
        return protocol

    def before_measurement(stage):
        saved = json.loads((state["output_dir"] / "protocol.json").read_text())
        assert saved["protocol_digest"] == state["protocol"]["protocol_digest"]
        assert saved["models_fitted"] is False
        events.append(stage)

    def reference(path):
        before_measurement("hgnc")
        assert path == inputs["hgnc_path"]
        _reader_failure(state, "hgnc", ValueError)
        return hgnc

    def protein_reader(**kwargs):
        before_measurement("protein")
        assert kwargs == {
            "protein_path": inputs["protein_path"],
            "sample_map_path": inputs["sample_map_path"],
            "hgnc_path": inputs["hgnc_path"],
            "candidate_aliquots": plan.protein_aliquots,
        }
        _reader_failure(state, "protein", ValueError)
        return state["protein"]

    paths = _expected_paths(plan, inputs)

    def assay_reader(path, *, lock, hgnc, family):
        before_measurement(family)
        assert hgnc is state["hgnc"]
        expected_family, index, expected_lock = paths[path]
        assert expected_family == family
        assert lock == expected_lock
        calls.append((family, index, path, lock))
        _reader_failure(state, (family, index), AssayFormatError)
        return state[family][index]

    monkeypatch.setattr(runner, "load_admission_plan", load)
    monkeypatch.setattr(runner, "frozen_protocol", freeze)
    monkeypatch.setattr(runner, "read_locked_hgnc", reference)
    monkeypatch.setattr(runner, "admit_confirmatory_protein", protein_reader)
    monkeypatch.setattr(
        runner,
        "parse_star_counts_v36",
        lambda path, *, lock, hgnc: assay_reader(path, lock=lock, hgnc=hgnc, family="rna"),
    )
    monkeypatch.setattr(
        runner,
        "parse_ascat_gene_cnv",
        lambda path, *, lock, hgnc: assay_reader(path, lock=lock, hgnc=hgnc, family="cnv"),
    )

    def execute(output_dir=None):
        output_dir = output_dir or tmp_path / "result"
        state["output_dir"] = output_dir
        return runner.evaluate(**inputs, output_dir=output_dir)

    return SimpleNamespace(
        plan=plan,
        inputs=inputs,
        state=state,
        calls=calls,
        events=events,
        run=execute,
        tmp_path=tmp_path,
        real_protocol=real_protocol,
    )


def test_every_declared_file_is_read_once_in_the_frozen_candidate_order(harness, capsys):
    result = harness.run()
    assert [(family, index) for family, index, _, _ in harness.calls] == [
        (family, index) for index in range(56) for family in ("rna", "cnv")
    ]
    assert len({path for _, _, path, _ in harness.calls}) == 112
    assert Counter(family for family, _, _, _ in harness.calls) == {"rna": 56, "cnv": 56}
    assert harness.events[:4] == ["plan", "protocol", "hgnc", "protein"]
    assert harness.plan.protein_aliquots != tuple(sorted(harness.plan.protein_aliquots))
    assert result["verified_assay_files"] == 112
    assert result["candidate_specimens"] == 56
    assert result["joint_complete_gene_specimen_pairs"] == 16
    assert result["legacy_fit_admitted"] is False
    assert result["independent_validation"] is False
    assert capsys.readouterr().out == ""


def test_protocol_binds_sources_metadata_and_code_before_first_measurement(harness):
    harness.run()
    protocol = json.loads((harness.state["output_dir"] / "protocol.json").read_text())
    digest = protocol.pop("protocol_digest")
    assert sha256_digest(protocol) == digest
    assert protocol["frozen_metadata_choices_sha256"] == "sha256:" + "a" * 64
    assert protocol["frozen_private_file_manifest_sha256"] == "sha256:" + "b" * 64
    assert tuple(protocol["panel"]) == PANEL
    assert set(protocol["source_modules"]) == set(runner.SOURCE_MODULES)
    assert all(
        value.startswith("sha256:") and len(value) == 71
        for value in protocol["source_modules"].values()
    )
    assert protocol["tool_source_digest"].startswith("sha256:")
    assert protocol["measurement_axes"]["rna"] == "STAR GENCODEv36 fpkm_uq_unstranded"
    assert protocol["models_fitted"] is False
    assert protocol["clinical_scope_or_assay_compatibility_admitted"] is False
    assert protocol["metadata_issuer_authenticated_by_hashes"] is False


def test_source_code_content_changes_the_frozen_protocol_binding(monkeypatch):
    content = {name: ("synthetic code for " + name).encode() for name in runner.SOURCE_MODULES}

    class Sources:
        def joinpath(self, name):
            return SimpleNamespace(read_bytes=lambda: content[name])

    def resources(package):
        assert package == "glio_proteogen.research.cptac_gbm_external_admission"
        return Sources()

    monkeypatch.setattr(runner, "files", resources)
    before = runner.frozen_protocol(choices_sha256="a" * 64, files_manifest_sha256="b" * 64)
    content["assays.py"] += b"\nchanged parser policy"
    after = runner.frozen_protocol(choices_sha256="a" * 64, files_manifest_sha256="b" * 64)
    assert before["protocol_digest"] != after["protocol_digest"]
    assert before["source_modules"]["assays.py"] != after["source_modules"]["assays.py"]
    assert all(
        before["source_modules"][name] == after["source_modules"][name]
        for name in runner.SOURCE_MODULES
        if name != "assays.py"
    )


def test_repeated_run_is_digest_bound_and_byte_identical(harness):
    first = harness.run(harness.tmp_path / "first")
    second = harness.run(harness.tmp_path / "second")
    assert first == second
    for name in ("protocol.json", "evaluation.json", "summary.csv"):
        assert (harness.tmp_path / "first" / name).read_bytes() == (
            harness.tmp_path / "second" / name
        ).read_bytes()
    report = json.loads((harness.tmp_path / "first" / "evaluation.json").read_text())
    digest = report.pop("report_digest")
    assert sha256_digest(report) == digest == first["report_digest"]
    changed_choices = harness.real_protocol(choices_sha256="c" * 64, files_manifest_sha256="b" * 64)
    changed_manifest = harness.real_protocol(
        choices_sha256="a" * 64, files_manifest_sha256="c" * 64
    )
    original = json.loads((harness.tmp_path / "first" / "protocol.json").read_text())
    assert changed_choices["protocol_digest"] != original["protocol_digest"]
    assert changed_manifest["protocol_digest"] != original["protocol_digest"]


def test_existing_output_directory_is_never_overwritten(harness, monkeypatch):
    output = harness.tmp_path / "existing"
    output.mkdir()
    original = output / "keep.txt"
    original.write_text("caller-owned")
    monkeypatch.setattr(runner, "load_admission_plan", lambda **kwargs: harness.plan)
    with pytest.raises(FileExistsError):
        harness.run(output)
    assert original.read_text() == "caller-owned"
    assert list(output.iterdir()) == [original]
    assert harness.calls == []
    assert "hgnc" not in harness.events


@pytest.mark.parametrize("failure", ["hgnc", "protein", ("rna", 0), ("cnv", 7)])
def test_reader_failure_leaves_only_frozen_protocol_without_partial_report(harness, failure):
    harness.state["failure"] = failure
    with pytest.raises(ValueError):
        harness.run()
    output = harness.state["output_dir"]
    assert {path.name for path in output.iterdir()} == {"protocol.json"}
    if failure == ("rna", 0):
        assert [(family, index) for family, index, _, _ in harness.calls] == [("rna", 0)]
    elif failure == ("cnv", 7):
        assert len(harness.calls) == 16
        assert harness.calls[-1][:2] == ("cnv", 7)
    else:
        assert harness.calls == []


def test_invalid_plan_checksum_fails_before_output_and_measurements(tmp_path, monkeypatch):
    choices = tmp_path / "private-capture.json"
    choices.write_text('{"private_source_identifier":"synthetic-secret"}')
    manifest = tmp_path / "private-files.json"
    manifest.write_text("{}")
    output = tmp_path / "never-created"

    def forbidden(*_args, **_kwargs):
        pytest.fail("measurement or protocol reader ran before plan admission")

    for name in (
        "frozen_protocol",
        "read_locked_hgnc",
        "admit_confirmatory_protein",
        "parse_star_counts_v36",
        "parse_ascat_gene_cnv",
    ):
        monkeypatch.setattr(runner, name, forbidden)
    with pytest.raises(AdmissionPlanError):
        runner.evaluate(
            choices_path=choices,
            choices_sha256="0" * 64,
            files_manifest_path=manifest,
            files_manifest_sha256="0" * 64,
            protein_path=tmp_path / "unused-protein",
            sample_map_path=tmp_path / "unused-map",
            hgnc_path=tmp_path / "unused-reference",
            output_dir=output,
        )
    assert not output.exists()


def test_absent_protein_null_and_true_zero_have_distinct_json_and_csv_semantics(harness):
    symbols = tuple(symbol for symbol in PANEL if symbol != "CDKN2B")
    values = np.ones((15, 56))
    values[symbols.index("CDKN2A")] = np.nan
    values[symbols.index("CDK4"), 0] = 0
    harness.state["protein"] = synthetic_protein(values, symbols=symbols)
    for family in ("rna", "cnv"):
        harness.state[family] = [
            synthetic_assay([0, *([1] * 15)] if index == 0 else [1] * 16, rna=family == "rna")
            for index in range(56)
        ]
    harness.run()
    output = harness.state["output_dir"]
    report = json.loads((output / "evaluation.json").read_text())
    protein = {row["gene"]: row for row in report["protein"]["panel_coverage"]}
    assert protein["CDKN2B"]["source_rows"] == 0
    assert protein["CDKN2B"]["unshared_finite"] is None
    assert protein["CDKN2B"]["unshared_missing"] is None
    assert protein["CDKN2A"]["source_rows"] == 1
    assert protein["CDKN2A"]["unshared_finite"] == 0
    assert protein["CDKN2A"]["unshared_missing"] == 56
    with (output / "summary.csv").open(newline="") as stream:
        rows = {row["gene"]: row for row in csv.DictReader(stream)}
    assert len(rows) == 16
    assert rows["CDKN2B"]["protein_feature_present"] == "False"
    assert rows["CDKN2A"]["protein_feature_present"] == "True"
    assert rows["CDKN2B"]["observed_protein"] == rows["CDKN2A"]["observed_protein"] == "0"
    assert rows["CDKN2B"]["zero_protein"] == rows["CDKN2A"]["zero_protein"] == "0"
    assert (
        rows["CDK4"]["zero_cnv"] == rows["CDK4"]["zero_rna"] == rows["CDK4"]["zero_protein"] == "1"
    )
    assert rows["CDK4"]["joint_complete"] == "56"
    assert rows["CDK4"]["legacy_common_oof_minimum"] == "60"
    assert rows["CDK4"]["legacy_common_oof_support_possible"] == "False"
    assert "nan" not in (output / "summary.csv").read_text().lower()


def test_outputs_contain_only_aggregate_counts_and_no_private_bindings(harness):
    harness.run()
    output = harness.state["output_dir"]
    assert {path.name for path in output.iterdir()} == {
        "protocol.json",
        "evaluation.json",
        "summary.csv",
    }
    text = "\n".join(path.read_text() for path in output.iterdir())
    for candidate in harness.plan.candidates:
        for value in (
            candidate.case_submitter_id,
            candidate.sample_submitter_id,
            candidate.gdc_sample_uuid,
            candidate.protein_aliquot_submitter_id,
            candidate.protein_aliquot_uuid,
            candidate.rna_file_id,
            candidate.cnv_file_id,
        ):
            assert value not in text
    assert "87654.123" not in text
    assert str(harness.tmp_path) not in text
    for filename in ("protocol.json", "evaluation.json"):
        runner._aggregate_only(json.loads((output / filename).read_text()))


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"nested": {"file_id": "synthetic-private-file"}}, ValueError),
        ({"sample_submitter_id": "synthetic-private-sample"}, ValueError),
        ({"nested": [{"values": [1, 2]}]}, ValueError),
        ({"participants": []}, ValueError),
        ({"candidate_rows": []}, ValueError),
        ({"predictions": [0]}, ValueError),
        ({"residuals": [0]}, ValueError),
        ({"unexpected": np.zeros(16)}, TypeError),
        ({"unexpected": [0] * 56}, ValueError),
        ({"nested": {"unexpected": (0,) * 112}}, ValueError),
    ],
)
def test_export_guard_rejects_individual_fields_vectors_and_arrays_before_writing(
    tmp_path, payload, error_type
):
    path = tmp_path / "never-created.json"
    with pytest.raises(error_type):
        runner._write_json(path, payload)
    assert not path.exists()


def test_aggregate_json_writer_never_overwrites(tmp_path):
    path = tmp_path / "caller-owned.json"
    path.write_bytes(b"caller-owned")
    with pytest.raises(FileExistsError):
        runner._write_json(path, {"gene": "TP53", "count": 0})
    assert path.read_bytes() == b"caller-owned"


def _cli_arguments(tmp_path):
    return [
        "confirmatory-admission",
        "--choices",
        str(tmp_path / "private-choices"),
        "--choices-sha256",
        "a" * 64,
        "--files-manifest",
        str(tmp_path / "private-manifest"),
        "--files-manifest-sha256",
        "b" * 64,
        "--protein",
        str(tmp_path / "private-protein"),
        "--sample-map",
        str(tmp_path / "private-map"),
        "--hgnc",
        str(tmp_path / "private-hgnc"),
        "--output-dir",
        str(tmp_path / "private-output"),
    ]


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError])
def test_main_errors_are_generic_without_private_paths_or_source_details(
    tmp_path, monkeypatch, capsys, error_type
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    tainted_message = f"{tmp_path}/private-tainted-source synthetic-private-specimen"

    def fail(**_kwargs):
        raise error_type(tainted_message)

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert (
        output.err
        == "Source admission failed; private inputs did not satisfy the declared contracts.\n"
    )
    assert str(tmp_path) not in output.err
    assert "private-tainted-source" not in output.err


def test_main_prints_only_the_aggregate_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    expected = {
        "candidate_specimens": 56,
        "verified_assay_files": 112,
        "legacy_fit_admitted": False,
    }
    monkeypatch.setattr(runner, "evaluate", lambda **kwargs: expected)
    assert runner.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected
    assert output.err == ""
