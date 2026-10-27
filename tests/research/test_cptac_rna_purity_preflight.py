"""Synthetic whole-axis production admission, fatal boundaries and saved seals."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceVerificationError
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission import (
    context,
    identity,
    native_counts,
    preflight,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission.contracts import (
    AdmissionError,
    canonical_bytes,
    digest,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    DiscoveryInputs,
    LockedInput,
)
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service
from tests.research import test_cptac_rna_purity_native_counts as native_oracles


def _make_harness(root, patch, *, payload=None, reference=None):
    root.mkdir(parents=True, exist_ok=True)
    sources = root / "sources"
    measurements = sources / "measurements"
    measurements.mkdir(parents=True)
    names, _ = identity._released_metadata()
    genes = tuple(native_oracles._gene(index, names[index - 1]) for index in range(1, 4))
    if reference is None:
        reference = native_oracles._reference(*genes)
    if payload is None:
        payload = native_oracles._payload(
            [
                native_oracles._row(genes[0], "7"),
                native_oracles._row(genes[1], "0"),
            ]
        )
    candidates, bindings = [], {}
    for index in range(72):
        rna, cnv = str(UUID(int=1000 + index)), str(UUID(int=2000 + index))
        candidates.append(
            CandidateBinding(
                f"synthetic-private-case-{index}",
                f"synthetic-private-sample-{index}",
                str(UUID(int=3000 + index)),
                f"synthetic-private-aliquot-{index}",
                str(UUID(int=4000 + index)),
                rna,
                cnv,
            )
        )
        relative = rna + ".bin"
        (measurements / relative).write_bytes(payload)
        bindings[rna] = AssayInputBinding(relative, native_oracles._lock(payload), "STAR - Counts")
        bindings[cnv] = AssayInputBinding(cnv + ".bin", native_oracles._lock(payload), "AscatNGS")
    for name in ("choices.private.json", "map.private.json", "hgnc.tsv"):
        (sources / name).write_bytes(b"{}")
    manifest = measurements / "manifest.private.json"
    manifest.write_bytes(b"{}")
    checksum = hashlib.sha256(b"{}").hexdigest()
    inputs = DiscoveryInputs(
        sources / "choices.private.json",
        checksum,
        sources / "map.private.json",
        checksum,
        manifest,
        checksum,
        sources / "hgnc.tsv",
    )
    receipt = ExternalAdmissionReceipt(
        profile_id="cptac-gbm-discovery-metadata-plan/1.0.0",
        choices_sha256=checksum,
        files_manifest_sha256=checksum,
        candidate_count=72,
        rna_file_count=72,
        cnv_file_count=72,
        paired_file_count=144,
        manifest_verified_bytes=len(payload) * 144,
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=("Synthetic metadata seam; no actual specimen or measurement admission.",),
    )
    harness = SimpleNamespace(
        root=root,
        measurements=measurements,
        inputs=inputs,
        plan=ExternalAdmissionPlan(tuple(candidates), bindings, receipt),
        reference=reference,
        genes=genes,
        payload=payload,
        output=root / "output",
    )
    patch.setattr(preflight, "load_discovery_plan", lambda **_kwargs: harness.plan)
    patch.setattr(preflight, "read_locked_hgnc", lambda _path: harness.reference)
    # Code metadata is held constant inside each synthetic test, independently of
    # other agents formatting source while the uncommitted implementation evolves.
    frozen_profile = preflight.profile()
    patch.setattr(preflight, "profile", lambda: copy.deepcopy(frozen_profile))
    return harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    return _make_harness(tmp_path / "synthetic", monkeypatch)


def _run(harness, *, output=None, expected=None):
    protocol = preflight.frozen_protocol(harness.inputs)
    return preflight.evaluate_preflight(
        harness.inputs,
        output_dir=harness.output if output is None else output,
        expected_protocol_digest=protocol["protocol_digest"] if expected is None else expected,
    )


def _no_model(patch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("count-only admission invoked model, preprocessing or service inference")

    for name in ("_input_vector", "_forward", "analyze_gbm_rna_purity"):
        patch.setattr(engine, name, forbidden)
    patch.setattr(service, "analyze_gbm_rna_purity", forbidden)
    patch.setattr(catalog, "gbm_rna_purity_catalog", forbidden)


def test_genuine_72_file_production_reader_preserves_unknowns_zero_absent_and_full_axis(
    harness, monkeypatch
):
    _no_model(monkeypatch)
    observed = []
    original = preflight.read_verified_source

    def source(path, lock, *, max_bytes):
        assert (harness.output / "profile.json").is_file()
        assert (harness.output / "protocol.json").is_file()
        assert not (harness.output / "preflight.json").exists()
        observed.append(Path(path))
        return original(path, lock, max_bytes=max_bytes)

    monkeypatch.setattr(preflight, "read_verified_source", source)
    protocol = preflight.frozen_protocol(harness.inputs)
    assert observed == []
    report = preflight.evaluate_preflight(
        harness.inputs,
        output_dir=harness.output,
        expected_protocol_digest=protocol["protocol_digest"],
    )
    assert len(observed) == len(set(observed)) == 72
    assert all(path.parent == harness.measurements for path in observed)
    assert report["planned_files"] == report["context"]["state_counts"]["unknown"] == 72
    assert report["outcomes"] == {
        "ready": 0,
        "below_coverage_gate": 72,
        "zero_recognized_sum": 0,
        "schema_rejected": 0,
        "domain_rejected": 0,
    }
    assert report["feature_state_totals"] == {
        "observed_positive": 72,
        "observed_zero": 72,
        "absent_feature": 72,
        "unresolved_reference": 5826 * 72,
        "ambiguous_identity": 0,
        "symbol_disagreement": 0,
    }
    assert report["recognized_raw_count_sum"] == 7 * 72
    assert report["schema_totals"]["gene_rows"] == 2 * 72
    assert report["schema_totals"]["summary_rows"] == 4 * 72
    assert report["verified_rna_bytes"] == report["planned_rna_bytes"] == len(harness.payload) * 72
    assert report["coverage_histogram"][0]["files"] == 72
    assert report["models_executed"] is report["inference_requests_constructed"] is False
    assert {path.name for path in harness.output.iterdir()} == {
        "profile.json",
        "protocol.json",
        "preflight.json",
    }
    verification = preflight.verify_preflight(harness.output)
    assert verification["verified"] and not verification["raw_sources_reparsed"]
    exported = b"".join(path.read_bytes() for path in harness.output.iterdir())
    for candidate in harness.plan.candidates:
        for secret in asdict(candidate).values():
            assert secret.encode() not in exported


def test_protocol_mismatch_stops_before_any_rna_read_or_output(harness, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("RNA was opened before expected-protocol comparison")

    monkeypatch.setattr(preflight, "read_verified_source", forbidden)
    with pytest.raises(AdmissionError, match="frozen protocol"):
        _run(harness, expected="sha256:" + "0" * 64)
    assert not harness.output.exists()


@pytest.mark.parametrize("defect", ["missing", "duplicate", "workflow", "eligibility", "profile"])
def test_complete_inherited_72_axis_is_required_before_reference_or_rna(
    harness, monkeypatch, defect
):
    if defect == "missing":
        harness.plan = replace(harness.plan, candidates=harness.plan.candidates[:-1])
    elif defect == "duplicate":
        harness.plan = replace(harness.plan, candidates=(harness.plan.candidates[0],) * 72)
    elif defect == "workflow":
        values = dict(harness.plan.files)
        key = harness.plan.candidates[0].rna_file_id
        values[key] = replace(values[key], workflow="AscatNGS")
        harness.plan = replace(harness.plan, files=values)
    else:
        changes = (
            {"eligibility_admitted": True}
            if defect == "eligibility"
            else {"profile_id": "foreign/1.0.0"}
        )
        harness.plan = replace(harness.plan, receipt=replace(harness.plan.receipt, **changes))

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid whole-axis metadata reached a reference or measurement read")

    monkeypatch.setattr(preflight, "read_locked_hgnc", forbidden)
    monkeypatch.setattr(preflight, "read_verified_source", forbidden)
    with pytest.raises(AdmissionError, match="complete inherited"):
        preflight.frozen_protocol(harness.inputs)


def _context_inputs(harness):
    directory = harness.root / "clinical"
    directory.mkdir()
    source = b"Synthetic reviewed context source, not an actual clinical record."
    source_path = directory / "source.txt"
    source_path.write_bytes(source)
    source_digest = "sha256:" + hashlib.sha256(source).hexdigest()
    bases = {
        context.ContextComponent.ORGANISM: context.ReviewBasis.ORGANISM,
        context.ContextComponent.DISEASE_POPULATION: context.ReviewBasis.DIAGNOSIS,
        context.ContextComponent.PRIMARY_POPULATION_MAPPING: context.ReviewBasis.POPULATION,
        context.ContextComponent.SPECIMEN_MATERIAL: context.ReviewBasis.MATERIAL,
        context.ContextComponent.ASSAY_CONTEXT: context.ReviewBasis.ASSAY,
    }
    entries = []
    for index in range(3):
        records = [
            {
                "record_key": f"synthetic-{index}-{component.value}",
                "source_digest": source_digest,
                "source_location": "synthetic-sheet:R1C1",
                "source_value": "synthetic-private-context",
                "component": component.value,
                "assertion": "supports_target",
                "review_basis": bases[component].value,
                "lineage_scope": "exact_specimen",
            }
            for component in context.REQUIRED_COMPONENTS
        ]
        if index in (1, 2):
            opposing = {
                **records[1],
                "record_key": f"synthetic-opposition-{index}",
                "assertion": "opposes_target",
            }
            records = [*records, opposing] if index == 1 else [opposing]
        candidate = harness.plan.candidates[index]
        entries.append(
            {
                "rna_key": candidate.rna_file_id,
                "lineage_digest": digest(asdict(candidate)),
                "records": records,
            }
        )
    payload = canonical_bytes({"schema_version": context.EVIDENCE_SCHEMA, "entries": entries})
    evidence_path = directory / "evidence.private.json"
    evidence_path.write_bytes(payload)
    return replace(
        harness.inputs,
        context_evidence=LockedInput(evidence_path, native_oracles._lock(payload)),
        context_sources=(LockedInput(source_path, native_oracles._lock(source)),),
    )


def test_supported_conflicting_out_of_scope_and_unknown_context_never_filter_counts(harness):
    unknown = _run(harness)
    harness.inputs = _context_inputs(harness)
    assessed = _run(harness, output=harness.root / "with-context")
    assert assessed["context"]["state_counts"] == {
        "source_supported": 1,
        "out_of_scope": 1,
        "unknown": 69,
        "conflicting": 1,
    }
    for field in (
        "outcomes",
        "schema_totals",
        "feature_state_totals",
        "recognized_raw_count_sum",
        "coverage_histogram",
        "planned_files",
        "verified_rna_bytes",
    ):
        assert assessed[field] == unknown[field]
    table = {
        row["context_state"]: row["outcomes"]["below_coverage_gate"]
        for row in assessed["context_by_readiness"]
    }
    assert table == assessed["context"]["state_counts"]
    assert not assessed["source_plan_eligibility_admitted"]
    assert not assessed["context"]["inference_context_constructed"]


def test_schema_and_domain_rejections_are_accounted_separately(harness):
    files = dict(harness.plan.files)
    for index, payload in enumerate(
        (
            b"malformed synthetic source\n",
            native_oracles._payload(
                [
                    native_oracles._row(harness.genes[0], str(10**15 + 1)),
                ]
            ),
        )
    ):
        candidate = harness.plan.candidates[index]
        binding = files[candidate.rna_file_id]
        (harness.measurements / binding.relative_path).write_bytes(payload)
        files[candidate.rna_file_id] = replace(binding, lock=native_oracles._lock(payload))
    harness.plan = replace(harness.plan, files=files)
    report = _run(harness)
    assert report["outcomes"] == {
        "ready": 0,
        "below_coverage_gate": 70,
        "zero_recognized_sum": 0,
        "schema_rejected": 1,
        "domain_rejected": 1,
    }
    assert report["feature_state_totals"]["observed_positive"] == 70
    assert sum(report["feature_state_totals"].values()) == 70 * 5829
    assert report["schema_totals"]["input_bytes"] == len(harness.payload) * 70
    assert report["context"]["planned_count"] == 72


@pytest.mark.parametrize("defect", ["checksum", "missing", "unexpected"])
def test_integrity_io_and_unexpected_projection_failures_stop_without_complete_report(
    harness, monkeypatch, defect
):
    expected = preflight.frozen_protocol(harness.inputs)["protocol_digest"]
    binding = harness.plan.files[harness.plan.candidates[1].rna_file_id]
    path = harness.measurements / binding.relative_path
    if defect == "checksum":
        path.write_bytes(b"x" * len(harness.payload))
    elif defect == "missing":
        path.unlink()
    else:

        def unexpected(*_args, **_kwargs):
            raise RuntimeError("synthetic-private-unexpected")

        monkeypatch.setattr(preflight, "project_native_star_counts", unexpected)
    with pytest.raises(RuntimeError if defect == "unexpected" else SourceVerificationError):
        preflight.evaluate_preflight(
            harness.inputs, output_dir=harness.output, expected_protocol_digest=expected
        )
    assert not (harness.output / "preflight.json").exists()
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(harness.output)


@pytest.fixture(scope="module")
def complete_saved_run(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        instance = _make_harness(tmp_path_factory.mktemp("synthetic-rna-completed"), patch)
        _run(instance)
    return instance.output


@pytest.fixture
def mutable_saved(complete_saved_run, tmp_path, monkeypatch):
    output = tmp_path / "saved"
    shutil.copytree(complete_saved_run, output)
    snapshot = json.loads((output / "profile.json").read_bytes())
    monkeypatch.setattr(preflight, "profile", lambda: copy.deepcopy(snapshot))
    return output


def _reseal(path, document, field):
    document[field] = digest({key: value for key, value in document.items() if key != field})
    path.write_bytes(canonical_bytes(document) + b"\n")


@pytest.mark.parametrize("name", ["profile.json", "protocol.json", "preflight.json"])
@pytest.mark.parametrize("defect", ["tamper", "missing", "noncanonical"])
def test_saved_three_file_closure_and_content_tampering_are_rejected(mutable_saved, name, defect):
    path = mutable_saved / name
    if defect == "missing":
        path.unlink()
    elif defect == "tamper":
        path.write_bytes(
            path.read_bytes().replace(b'"models_executed":false', b'"models_executed":true', 1)
        )
    else:
        path.write_bytes(b" " + path.read_bytes())
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("protocol.json", "planned_files", 1),
        ("protocol.json", "planned_files", 72.0),
        ("protocol.json", "models_executed", 0),
        ("protocol.json", "previous_selection_requires_paired_proteome_cnv", 1),
        ("protocol.json", "context_filters_count_preflight", 0),
        ("preflight.json", "complete", 1),
        ("preflight.json", "models_executed", 0),
        ("preflight.json", "planned_files", True),
        ("preflight.json", "coverage_supported_files", True),
        ("preflight.json", "recognized_raw_count_sum", 1.5),
    ],
)
def test_resealed_literal_aliases_and_wrong_scalar_types_are_rejected(
    mutable_saved, name, field, value
):
    path = mutable_saved / name
    document = json.loads(path.read_bytes())
    document[field] = value
    seal = "protocol_digest" if name == "protocol.json" else "report_digest"
    _reseal(path, document, seal)
    if name == "protocol.json":
        report_path = mutable_saved / "preflight.json"
        report = json.loads(report_path.read_bytes())
        report["protocol_digest"] = document["protocol_digest"]
        _reseal(report_path, report, "report_digest")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


@pytest.mark.parametrize("name", ["protocol.json", "preflight.json"])
def test_resealed_omitted_default_flags_cannot_be_silently_restored(mutable_saved, name):
    path = mutable_saved / name
    document = json.loads(path.read_bytes())
    document.pop("models_executed")
    seal = "protocol_digest" if name == "protocol.json" else "report_digest"
    _reseal(path, document, seal)
    if name == "protocol.json":
        report_path = mutable_saved / "preflight.json"
        report = json.loads(report_path.read_bytes())
        report["protocol_digest"] = document["protocol_digest"]
        _reseal(report_path, report, "report_digest")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


def test_nested_literal_flag_alias_is_not_hidden_by_receipt_hydration(mutable_saved):
    path = mutable_saved / "preflight.json"
    document = json.loads(path.read_bytes())
    document["context"]["inference_context_constructed"] = 0
    _reseal(path, document, "report_digest")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


@pytest.mark.parametrize(
    "name", ["extra.private.json", "preflight.json.pending", "extra-directory"]
)
def test_unmanifested_files_or_directories_are_rejected(mutable_saved, name):
    if name == "extra-directory":
        (mutable_saved / name).mkdir()
    else:
        (mutable_saved / name).write_bytes(b"{}")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


@pytest.mark.parametrize(
    "defect", ["existing", "measurement_child", "missing_parent", "source_file"]
)
def test_unsafe_output_targets_fail_before_any_rna_read(harness, monkeypatch, defect):
    if defect == "existing":
        output = harness.root
    elif defect == "measurement_child":
        output = harness.measurements / "output"
    elif defect == "source_file":
        output = harness.inputs.choices_path
    else:
        output = harness.root / "missing-parent/output"

    def forbidden(*_args, **_kwargs):
        pytest.fail("unsafe output reached an RNA read")

    monkeypatch.setattr(preflight, "read_verified_source", forbidden)
    with pytest.raises(AdmissionError):
        _run(harness, output=output)


def test_saved_verification_does_not_reparse_sources_or_call_a_model(mutable_saved, monkeypatch):
    _no_model(monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("saved verification accessed a source or projection")

    monkeypatch.setattr(preflight, "read_verified_source", forbidden)
    monkeypatch.setattr(preflight, "project_native_star_counts", forbidden)
    assert preflight.verify_preflight(mutable_saved)["raw_sources_reparsed"] is False


@pytest.mark.parametrize(("recognized", "count"), [(4664, "7"), (5771, "0")])
def test_high_coverage_readiness_and_zero_sum_are_distinct_from_context(
    tmp_path, monkeypatch, recognized, count
):
    names, _ = identity._released_metadata()
    genes = tuple(native_oracles._gene(index, symbol) for index, symbol in enumerate(names, 1))
    reference = native_oracles._reference(*genes)
    axis = identity.admit_model_axis(reference)
    payload = native_oracles._payload(
        [native_oracles._row(gene, count) for gene in genes[:recognized]]
    )
    # Project one genuine full-axis sample. The 72 identical synthetic sources
    # still pass the public locked-byte reader; avoid repeating that projection.
    sample = native_counts.project_native_star_counts(
        payload, lock=native_oracles._lock(payload), model_axis=axis, hgnc=reference
    )
    instance = _make_harness(
        tmp_path / "high-coverage", monkeypatch, payload=payload, reference=reference
    )
    projected = 0

    def projection(actual, *, lock, model_axis, hgnc):
        nonlocal projected
        assert actual == payload and lock == native_oracles._lock(payload)
        assert model_axis.digest == axis.digest and hgnc is reference
        projected += 1
        return sample

    monkeypatch.setattr(preflight, "project_native_star_counts", projection)
    _no_model(monkeypatch)
    report = _run(instance)
    assert projected == 72
    assert report["outcomes"]["ready"] == (72 if count != "0" else 0)
    assert report["outcomes"]["zero_recognized_sum"] == (72 if count == "0" else 0)
    assert report["outcomes"]["below_coverage_gate"] == 0
    assert report["coverage_supported_files"] == (72 if recognized >= 5771 else 0)
    assert report["zero_recognized_sum_files"] == (72 if count == "0" else 0)
    assert report["recognized_raw_count_sum"] == int(count) * recognized * 72
    assert report["feature_state_totals"]["absent_feature"] == (5829 - recognized) * 72
    assert report["coverage_histogram"][recognized * 10 // 5829]["files"] == 72
    assert report["context"]["state_counts"]["unknown"] == 72
    assert not report["models_executed"] and not report["inference_requests_constructed"]


@pytest.mark.parametrize("failure", ["write", "readback", "corruption", "extra-file", "rename"])
def test_preseal_write_readback_directory_and_rename_failures_never_publish_completion(
    harness, monkeypatch, failure
):
    original_write, original_read, original_rename = preflight._write, preflight._read, Path.rename

    def write(path, document):
        if path.name == "preflight.json.pending" and failure == "write":
            raise AdmissionError
        original_write(path, document)
        if path.name == "preflight.json.pending" and failure == "corruption":
            path.write_bytes(b"{}\n")
        if path.name == "preflight.json.pending" and failure == "extra-file":
            (path.parent / "unexpected.json").write_bytes(b"{}\n")

    def read(path, *, maximum):
        if path.name == "preflight.json.pending" and failure == "readback":
            raise AdmissionError
        return original_read(path, maximum=maximum)

    def rename(path, target):
        if path.name == "preflight.json.pending" and failure == "rename":
            raise PermissionError
        return original_rename(path, target)

    monkeypatch.setattr(preflight, "_write", write)
    monkeypatch.setattr(preflight, "_read", read)
    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(AdmissionError):
        _run(harness)
    assert (harness.output / "profile.json").is_file()
    assert (harness.output / "protocol.json").is_file()
    assert not (harness.output / "preflight.json").exists()
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(harness.output)


def test_written_protocol_is_read_back_before_completion(harness, monkeypatch):
    original = preflight.read_verified_source
    calls = 0

    def source(path, lock, *, max_bytes):
        nonlocal calls
        result = original(path, lock, max_bytes=max_bytes)
        calls += 1
        if calls == 72:
            protocol = harness.output / "protocol.json"
            protocol.write_bytes(b" " + protocol.read_bytes())
        return result

    monkeypatch.setattr(preflight, "read_verified_source", source)
    with pytest.raises(AdmissionError, match="canonical"):
        _run(harness)
    assert calls == 72 and not (harness.output / "preflight.json").exists()
    assert not (harness.output / "preflight.json.pending").exists()


def test_atomic_completion_rename_is_the_last_fallible_operation(harness, monkeypatch):
    sealed = False
    original_rename = Path.rename

    def rename(path, target):
        nonlocal sealed
        assert path.name == "preflight.json.pending"
        result = original_rename(path, target)
        sealed = True
        return result

    def guarded(original):
        def call(*args, **kwargs):
            assert not sealed, "fallible check or file operation followed completion publication"
            return original(*args, **kwargs)

        return call

    for name in (
        "_read",
        "_write",
        "_check_directory",
        "_validate_documents",
        "profile",
        "verify_preflight",
    ):
        monkeypatch.setattr(preflight, name, guarded(getattr(preflight, name)))
    monkeypatch.setattr(Path, "rename", rename)
    report = _run(harness)
    assert sealed and report["complete"] is True
    assert (harness.output / "preflight.json").read_bytes() == canonical_bytes(report) + b"\n"
    assert not (harness.output / "preflight.json.pending").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["outcomes"].update(below_coverage_gate=71),
        lambda d: d["schema_totals"].update(summary_rows=287),
        lambda d: d["schema_totals"].update(data_rows=0),
        lambda d: d["feature_state_totals"].update(unresolved_reference=0),
        lambda d: d.update(coverage_supported_files=1),
        # Twelve nonzero files with three resolved slots can hold at most 36
        # positive slots; 72 positive slots cannot be assigned to zero-sum files.
        lambda d: d.update(zero_recognized_sum_files=60),
        lambda d: d.update(recognized_raw_count_sum=71),
        lambda d: d["coverage_histogram"][0].update(files=71),
        lambda d: d["coverage_histogram"][8].update(files=1),
        lambda d: d["context_by_readiness"][0]["outcomes"].update(ready=1),
    ],
    ids=[
        "outcome-count",
        "summary-count",
        "row-count",
        "unresolved-axis",
        "coverage",
        "positive-in-zero-sum",
        "rawsum",
        "histogram-count",
        "histogram-gate",
        "context-table",
    ],
)
def test_resealed_impossible_aggregate_partitions_remain_invalid(mutable_saved, mutation):
    path = mutable_saved / "preflight.json"
    document = json.loads(path.read_bytes())
    mutation(document)
    _reseal(path, document, "report_digest")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)


@pytest.mark.parametrize("name", ["profile.json", "protocol.json", "preflight.json"])
@pytest.mark.parametrize(
    "defect", ["duplicate-field", "nonfinite", "invalid-utf8", "directory", "oversize"]
)
def test_saved_artifact_closed_json_and_file_bounds(mutable_saved, name, defect):
    path = mutable_saved / name
    if defect == "directory":
        path.unlink()
        path.mkdir()
    elif defect == "duplicate-field":
        path.write_bytes(b'{"models_executed":false,"models_executed":false}\n')
    elif defect == "nonfinite":
        path.write_bytes(b'{"models_executed":NaN}\n')
    elif defect == "invalid-utf8":
        path.write_bytes(b"\xff")
    else:
        path.write_bytes(b" " * (preflight.MAX_OUTPUT_BYTES + 1))
    with pytest.raises(AdmissionError) as error:
        preflight.verify_preflight(mutable_saved)
    assert str(mutable_saved) not in str(error.value)


def test_corrupted_direct_input_instance_is_revalidated_before_metadata(harness, monkeypatch):
    object.__setattr__(harness.inputs, "context_sources", (object(),))

    def forbidden(**_kwargs):
        pytest.fail("caller-corrupted declaration reached metadata admission")

    monkeypatch.setattr(preflight, "load_discovery_plan", forbidden)
    with pytest.raises(AdmissionError):
        preflight.frozen_protocol(harness.inputs)


@pytest.mark.parametrize("role", ["source", "evidence"])
@pytest.mark.parametrize("alias", ["same-path", "copied-assay-digest"])
def test_context_assay_role_overlap_is_rejected_before_any_payload_read(
    harness, monkeypatch, role, alias
):
    binding = harness.plan.files[harness.plan.candidates[0].rna_file_id]
    assay = harness.measurements / binding.relative_path
    context_path = assay if alias == "same-path" else harness.root / "copied-source.txt"
    if alias != "same-path":
        context_path.write_bytes(harness.payload)
    declaration = LockedInput(context_path, binding.lock)
    if role == "source":
        payload = canonical_bytes({"schema_version": context.EVIDENCE_SCHEMA, "entries": []})
        evidence_path = harness.root / "empty-evidence.private.json"
        evidence_path.write_bytes(payload)
        harness.inputs = replace(
            harness.inputs,
            context_evidence=LockedInput(evidence_path, native_oracles._lock(payload)),
            context_sources=(declaration,),
        )
    else:
        harness.inputs = replace(harness.inputs, context_evidence=declaration)

    def forbidden(*_args, **_kwargs):
        pytest.fail("context/assay role overlap reached a payload reader before its metadata guard")

    monkeypatch.setattr(preflight, "read_verified_source", forbidden)
    with pytest.raises(AdmissionError):
        preflight.frozen_protocol(harness.inputs)
    assert not harness.output.exists()


def test_resealed_readiness_requires_enough_aggregate_recognized_slots(mutable_saved):
    path = mutable_saved / "preflight.json"
    document = json.loads(path.read_bytes())
    assert document["model_axis"]["resolved_features"] == 3
    assert (
        document["feature_state_totals"]["observed_positive"]
        + document["feature_state_totals"]["observed_zero"]
    ) == 144
    document["outcomes"].update(ready=72, below_coverage_gate=0)
    for row in document["context_by_readiness"]:
        row["outcomes"].update(
            ready=72 if row["context_state"] == "unknown" else 0, below_coverage_gate=0
        )
    document["coverage_histogram"][0]["files"] = 0
    document["coverage_histogram"][8]["files"] = 72
    _reseal(path, document, "report_digest")
    with pytest.raises(AdmissionError):
        preflight.verify_preflight(mutable_saved)
