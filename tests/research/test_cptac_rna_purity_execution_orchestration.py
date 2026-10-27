"""Synthetic whole-axis freeze, source-hold, saved-proof and config-boundary oracles."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AssayInputBinding,
    CandidateBinding,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import (
    COMPONENTS,
    ContextState,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    DiscoveryInputs,
    LockedInput,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution import execution as e
from glio_proteogen.research.cptac_gbm_rna_purity_execution import inference
from glio_proteogen.research.cptac_gbm_rna_purity_execution.clinical import (
    SOURCE_LOCKS,
    ClinicalAdmissionReceipt,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import (
    ExecutionError,
    ExecutionPolicy,
    canonical_bytes,
    digest,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.identity import (
    EXPECTED_MAPPING_DIGEST,
    ModelAxisReceipt,
    _released_metadata,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import (
    CLINICAL_ROLES,
    ExecutionInputs,
    load_inputs,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.native_counts import (
    NativeCountDomainError,
    NativeCountFormatError,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.receipts import ExecutionReport

_D = "sha256:" + "1" * 64
_S = ContextState


def _lock(payload):
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _clinical_receipt(holds):
    unknown = {"source_supported": 0, "out_of_scope": 0, "unknown": 72, "conflicting": 0}
    values = {
        "exact_author_biospecimen_joins": 72,
        "missing_author_biospecimen_rows": 0,
        "clinical_idh_positive_cases": 0,
        "author_idh1_alteration_cases": 0,
        "reported_idh_alteration_union_cases": 0,
        "clinical_negative_cases": 0,
        "molecular_method_negative_cases": 0,
        "ihc_only_negative_cases": 0,
        "unknown_method_negative_cases": 0,
        "no_clinical_result_cases": 72,
        "source_hold_cases": holds,
        "source_hold_reason_counts": (("historical_case_withdrawal", holds),) if holds else (),
        "state_counts": unknown,
        "component_state_counts": [
            {"component": component.value, "states": unknown} for component in COMPONENTS[:7]
        ],
        "source_locks": [lock.model_dump(mode="json") for lock in SOURCE_LOCKS],
        "source_set_digest": digest([lock.model_dump(mode="json") for lock in SOURCE_LOCKS]),
        "ordered_axis_digest": _D,
        "evidence_digest": _D,
    }
    document = ClinicalAdmissionReceipt.model_construct(**values, receipt_digest=_D).model_dump(
        mode="json", warnings="none"
    )
    document.pop("receipt_digest")
    return ClinicalAdmissionReceipt.model_validate_json(
        canonical_bytes({**document, "receipt_digest": digest(document)})
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    measurement_root = tmp_path / "measurements"
    measurement_root.mkdir()
    discovery = DiscoveryInputs(
        choices_path=tmp_path / "choices.json",
        choices_sha256="1" * 64,
        map_bindings_path=tmp_path / "map.json",
        map_bindings_sha256="2" * 64,
        files_manifest_path=measurement_root / "files.json",
        files_manifest_sha256="3" * 64,
        hgnc_path=tmp_path / "hgnc.tsv",
    )
    policy = ExecutionPolicy(
        research_use_only=True,
        caller_authorizes_missing_gene_zero_fill=True,
        allow_limited_support=True,
    )
    inputs = ExecutionInputs(
        discovery=discovery,
        gencode_gtf_path=tmp_path / "gencode.gz",
        gencode_hgnc_path=tmp_path / "gencode-hgnc.gz",
        author_feature_path=tmp_path / "author.csv",
        clinical_sources=tuple(
            LockedInput(
                tmp_path / (role + ".bin"),
                SourceLock(lock.bytes, lock.md5, lock.sha256.removeprefix("sha256:")),
            )
            for role, lock in zip(CLINICAL_ROLES, SOURCE_LOCKS, strict=True)
        ),
        processing_source=LockedInput(tmp_path / "processing.html", e._PROCESSING_LOCK),
        policy=policy,
    )
    candidates, bindings, payloads = [], {}, {}
    for index in range(72):
        key = f"synthetic-rna-{index:03d}"
        candidates.append(
            CandidateBinding(
                f"synthetic-case-{index:03d}",
                f"synthetic-sample-{index:03d}",
                f"synthetic-gdc-{index:03d}",
                f"synthetic-aliquot-{index:03d}",
                f"synthetic-protein-{index:03d}",
                key,
                f"synthetic-cnv-{index:03d}",
            )
        )
        payload = f"synthetic-private-assay-{index:03d}".encode()
        binding = AssayInputBinding(key + ".tsv", _lock(payload), "STAR - Counts")
        bindings[key] = binding
        payloads[measurement_root / binding.relative_path] = payload
    plan = SimpleNamespace(
        candidates=tuple(candidates),
        files=bindings,
        receipt=SimpleNamespace(
            profile_id="cptac-gbm-discovery-metadata-plan/1.0.0",
            eligibility_admitted=False,
        ),
    )
    names, lengths = _released_metadata()
    axis_receipt = ModelAxisReceipt(
        feature_length_digest=digest(lengths),
        feature_mapping_digest=EXPECTED_MAPPING_DIGEST,
    )
    axis = SimpleNamespace(
        features=tuple(
            SimpleNamespace(source_symbol=name, source_length=length)
            for name, length in zip(names, lengths, strict=True)
        ),
        receipt=axis_receipt,
        digest=digest(axis_receipt.model_dump(mode="json")),
    )
    cases = tuple(
        SimpleNamespace(
            source_hold=index == 0,
            component_states=(_S.UNKNOWN,) * 7,
            observations_digest=digest({"synthetic_context": index}),
        )
        for index in range(72)
    )
    clinical = SimpleNamespace(cases=cases, receipt=_clinical_receipt(1))
    reads = []

    def reader(path, _lock, *, max_bytes):
        assert max_bytes > 0
        reads.append(path)
        return payloads.get(path, b"synthetic-metadata")

    def projector(payload, *, lock, model_axis):
        assert _lock(payload) == lock
        assert model_axis is axis
        counts = np.ones(5829, dtype=np.int64)
        states = np.zeros(5829, dtype=np.uint8)
        return SimpleNamespace(
            counts=counts,
            states=states,
            binding_digest=digest({"synthetic": payload.decode()}),
            receipt=SimpleNamespace(
                model_axis_digest=axis.digest,
                recognized_model_gene_count=5829,
                nonzero_model_gene_count=5829,
                observed_zero_model_gene_count=0,
                recognized_raw_count_sum=5829,
                count_ready=True,
                coverage_supported=True,
                state_counts=(5829, 0, 0, 0, 0, 0),
            ),
        )

    def forbidden(*_args, **_kwargs):
        pytest.fail("unknown synthetic clinical evidence must not construct or run a model")

    monkeypatch.setattr(e, "load_discovery_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(e, "read_locked_hgnc", lambda _path: object())
    monkeypatch.setattr(e, "admit_model_axis", lambda **_kwargs: axis)
    monkeypatch.setattr(e, "read_verified_source", reader)
    monkeypatch.setattr(e, "admit_clinical_context", lambda _targets, _sources: clinical)
    monkeypatch.setattr(e, "project_native_star_counts", projector)
    monkeypatch.setattr(inference, "GbmRnaPurityRequest", forbidden)
    monkeypatch.setattr(inference, "algorithm_profile", forbidden)
    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", forbidden)
    return SimpleNamespace(
        inputs=inputs,
        plan=plan,
        axis=axis,
        clinical=clinical,
        payloads=payloads,
        reads=reads,
        tmp=tmp_path,
        projector=projector,
    )


def _execute(setup, name="run"):
    protocol = e.frozen_protocol(setup.inputs)
    return e.evaluate_execution(
        setup.inputs,
        output_dir=setup.tmp / name,
        expected_protocol_digest=protocol["protocol_digest"],
    )


def test_metadata_freeze_reads_no_assays_and_wrong_digest_precedes_assay_or_output(setup):
    protocol = e.frozen_protocol(setup.inputs)
    assert protocol["planned_files"] == 72
    assert not any(path in setup.payloads for path in setup.reads)
    with pytest.raises(ExecutionError):
        e.evaluate_execution(
            setup.inputs,
            output_dir=setup.tmp / "never-created",
            expected_protocol_digest=_D,
        )
    assert not (setup.tmp / "never-created").exists()
    assert not any(path in setup.payloads for path in setup.reads)


def test_source_hold_precedes_read_and_unknown_context_conserves_other71_without_model(setup):
    result = _execute(setup)
    observed = [path for path in setup.reads if path in setup.payloads]
    expected = list(setup.payloads)[1:]
    assert observed == expected
    assert result["outcomes"]["source_hold"] == 1
    assert result["outcomes"]["context_unknown"] == 71
    assert result["read_rna_files"] == result["projected_files"] == 71
    assert result["numerically_ready_files"] == result["coverage_supported_files"] == 71
    assert result["model_executions"] == 0
    assert result["feature_state_totals"] == [71 * 5829, 0, 0, 0, 0, 0]
    assert result["verified_rna_bytes"] == sum(len(setup.payloads[path]) for path in expected)
    assert e.verify_execution(setup.tmp / "run")["verified"] is True
    assert {path.name for path in (setup.tmp / "run").iterdir()} == e._ARTIFACTS
    text = "".join(path.read_text() for path in (setup.tmp / "run").iterdir())
    assert "synthetic-private-assay" not in text
    assert "synthetic-case" not in text and "synthetic-rna" not in text


def test_two_complete_repeats_are_byte_identical(setup):
    _execute(setup, "first")
    _execute(setup, "second")
    for name in e._ARTIFACTS:
        assert (setup.tmp / "first" / name).read_bytes() == (
            setup.tmp / "second" / name
        ).read_bytes()


@pytest.mark.parametrize("error", [NativeCountFormatError, NativeCountDomainError])
def test_expected_projection_failure_is_accounted_and_axis_preserved(setup, monkeypatch, error):
    def projector(payload, **kwargs):
        if payload == list(setup.payloads.values())[1]:
            message = "synthetic invalid count coordinate"
            raise error(message)
        return setup.projector(payload, **kwargs)

    monkeypatch.setattr(e, "project_native_star_counts", projector)
    result = _execute(setup)
    outcome = "schema_rejected" if error is NativeCountFormatError else "domain_rejected"
    assert result["outcomes"][outcome] == 1
    assert result["outcomes"]["context_unknown"] == result["projected_files"] == 70
    assert result["read_rna_files"] == 71 and result["model_executions"] == 0


@pytest.mark.parametrize("error", [SourceVerificationError, RuntimeError])
def test_integrity_and_unexpected_errors_are_fatal_and_never_receive_complete_seal(
    setup, monkeypatch, error
):
    def failed(_payload, **_kwargs):
        message = "synthetic private operational error"
        raise error(message)

    monkeypatch.setattr(e, "project_native_star_counts", failed)
    with pytest.raises(error):
        _execute(setup)
    assert not (setup.tmp / "run" / "execution.json").exists()
    assert (setup.tmp / "run" / "protocol.json").exists()


def _reseal(directory, filename, mutation):
    path = directory / filename
    document = json.loads(path.read_bytes())
    mutation(document)
    seal = {
        "profile.json": "profile_digest",
        "protocol.json": "protocol_digest",
        "execution.json": "report_digest",
        "clinical-context.json": "receipt_digest",
    }.get(filename)
    if seal:
        document.pop(seal)
        document[seal] = digest(document)
    path.write_bytes(canonical_bytes(document) + b"\n")
    return document


@pytest.mark.parametrize(
    "filename",
    ["profile.json", "protocol.json", "identity.json", "clinical-context.json", "execution.json"],
)
def test_saved_verification_rejects_changed_artifact_and_extra_directory_entry(setup, filename):
    _execute(setup)
    directory = setup.tmp / "run"
    _reseal(directory, filename, lambda row: row.update({"unexpected_private_entry": True}))
    with pytest.raises(ExecutionError):
        e.verify_execution(directory)


def test_saved_verifier_performs_no_source_or_model_replay_and_rejects_extra_file(
    setup, monkeypatch
):
    _execute(setup)
    monkeypatch.setattr(
        e,
        "read_verified_source",
        lambda *_args, **_kwargs: pytest.fail("saved verifier reread raw source"),
    )
    result = e.verify_execution(setup.tmp / "run")
    assert result["raw_sources_reparsed"] is False
    assert result["models_executed_by_verifier"] is False
    (setup.tmp / "run" / "extra.txt").write_text("unexpected")
    with pytest.raises(ExecutionError):
        e.verify_execution(setup.tmp / "run")


def _rebind_protocol(directory, **changes):
    protocol = _reseal(directory, "protocol.json", lambda row: row.update(changes))
    _reseal(
        directory,
        "execution.json",
        lambda row: row.update({**changes, "protocol_digest": protocol["protocol_digest"]}),
    )


def test_coherently_resealed_foreign_axis_cannot_replace_fixed_reference_proof(setup):
    _execute(setup)
    directory = setup.tmp / "run"
    axis = _reseal(
        directory, "identity.json", lambda row: row.update({"feature_mapping_digest": _D})
    )
    _rebind_protocol(directory, model_axis_digest=digest(axis))
    with pytest.raises(ExecutionError):
        e.verify_execution(directory)


def test_coherently_resealed_clinical_hold_count_must_match_execution_holds(setup):
    _execute(setup)
    directory = setup.tmp / "run"
    clinical = _reseal(
        directory,
        "clinical-context.json",
        lambda row: row.update(
            {
                "source_hold_cases": 2,
                "source_hold_reason_counts": [["historical_case_withdrawal", 2]],
            }
        ),
    )
    _rebind_protocol(directory, clinical_receipt_digest=digest(clinical))
    with pytest.raises(ExecutionError):
        e.verify_execution(directory)


def test_resealed_estimate_cannot_override_zero_clinically_qualified_cases(setup):
    _execute(setup)
    directory = setup.tmp / "run"

    def add_impossible_estimate(row):
        row["outcomes"]["context_unknown"] -= 1
        row["outcomes"]["estimated"] = row["model_executions"] = 1

    _reseal(directory, "execution.json", add_impossible_estimate)
    with pytest.raises(ExecutionError):
        e.verify_execution(directory)


def _config(setup):
    data = setup.inputs
    return {
        "schema_version": "cptac-gbm-rna-purity-execution-inputs/1.0.0",
        "discovery": {
            key: str(value) if key.endswith("_path") else value
            for key, value in asdict(data.discovery).items()
            if key not in {"hgnc_path", "context_evidence", "context_sources"}
        },
        "hgnc_path": str(data.discovery.hgnc_path),
        "references": dict(
            zip(
                ("gencode_gtf", "gencode_hgnc", "author_features"),
                map(str, data.reference_paths),
                strict=True,
            )
        ),
        "clinical_sources": {
            role: {"path": str(source.path), **asdict(source.lock)}
            for role, source in zip(CLINICAL_ROLES, data.clinical_sources, strict=True)
        },
        "processing_source": {
            "path": str(data.processing_source.path),
            **asdict(data.processing_source.lock),
        },
        "policy": data.policy.model_dump(mode="json"),
    }


def _load(setup, document):
    path = setup.tmp / "inputs.private.json"
    payload = canonical_bytes(document)
    path.write_bytes(payload)
    return load_inputs(path, sha256=hashlib.sha256(payload).hexdigest())


def test_closed_loader_reads_only_config_and_preserves_exact_role_policy(setup):
    loaded = _load(setup, _config(setup))
    assert loaded == setup.inputs
    assert setup.reads == []


@pytest.mark.parametrize("scope", ["top", "discovery", "references", "clinical_sources", "policy"])
def test_input_loader_rejects_unknown_fields_in_each_closed_schema(setup, scope):
    document = _config(setup)
    target = document if scope == "top" else document[scope]
    target["unexpected"] = "synthetic-private-marker"
    with pytest.raises(ExecutionError) as raised:
        _load(setup, document)
    assert "synthetic-private-marker" not in str(raised.value)


def test_source_roles_reject_assay_path_digest_and_swapped_source_roles_before_read(setup):
    first = setup.inputs.clinical_sources[0]
    assay_path = next(iter(setup.payloads))
    variants = [
        replace(
            setup.inputs,
            clinical_sources=(
                LockedInput(assay_path, first.lock),
                *setup.inputs.clinical_sources[1:],
            ),
        ),
        replace(
            setup.inputs,
            clinical_sources=(
                LockedInput(first.path, _lock(setup.payloads[assay_path])),
                *setup.inputs.clinical_sources[1:],
            ),
        ),
        replace(setup.inputs, clinical_sources=tuple(reversed(setup.inputs.clinical_sources))),
    ]
    for inputs in variants:
        with pytest.raises(ExecutionError):
            e.frozen_protocol(inputs)
    assert setup.reads == []


@pytest.mark.parametrize("field", ["hgnc", "gencode", "relative_gencode"])
def test_assay_reference_alias_is_rejected_before_locked_reference_read(setup, monkeypatch, field):
    assay_path = next(iter(setup.payloads))
    if field == "hgnc":
        inputs = replace(
            setup.inputs, discovery=replace(setup.inputs.discovery, hgnc_path=assay_path)
        )
    else:
        path = (
            assay_path.relative_to(Path.cwd(), walk_up=True)
            if field == "relative_gencode"
            else assay_path
        )
        inputs = replace(setup.inputs, gencode_gtf_path=path)
    monkeypatch.setattr(
        e, "read_locked_hgnc", lambda _path: pytest.fail("assay alias reached reference reader")
    )
    with pytest.raises(ExecutionError):
        e.frozen_protocol(inputs)
    assert setup.reads == []


def test_preserved_receipt_oracles_reject_impossible_feature_and_byte_claims(setup):
    values = _execute(setup)
    absent = {**values, "feature_state_totals": [0, 0, 71 * 5829, 0, 0, 0]}
    unread = {
        **values,
        "read_rna_files": 0,
        "projected_files": 0,
        "numerically_ready_files": 0,
        "coverage_supported_files": 0,
        "feature_state_totals": [0] * 6,
        "verified_rna_bytes": 1,
        "outcomes": {**dict.fromkeys(values["outcomes"], 0), "source_hold": 72},
    }
    for document in (absent, unread):
        with pytest.raises(ValueError):
            ExecutionReport.model_validate_json(canonical_bytes(document))


def test_incomplete_axis_is_rejected_before_any_reference_clinical_or_assay_read(setup):
    setup.plan.candidates = setup.plan.candidates[:-1]
    with pytest.raises(ExecutionError):
        e.frozen_protocol(setup.inputs)
    assert setup.reads == []
    with pytest.raises(ExecutionError):
        e.frozen_protocol(SimpleNamespace())


@pytest.mark.parametrize(
    "destination", ["existing", "missing_parent", "source_path", "measurement_child"]
)
def test_output_guards_prevent_clobber_or_input_directory_mutation(setup, destination):
    paths = {
        "existing": setup.tmp / "existing",
        "missing_parent": setup.tmp / "missing" / "run",
        "source_path": setup.inputs.discovery.choices_path,
        "measurement_child": setup.inputs.discovery.files_manifest_path.parent / "run",
    }
    (setup.tmp / "existing").mkdir()
    with pytest.raises(ExecutionError):
        e._output_path(paths[destination], setup.inputs)
    assert setup.reads == []


def test_private_configuration_and_preparation_cannot_be_pickled(setup):
    prepared = e._prepare(setup.inputs)
    assert "private" in repr(setup.inputs)
    for value in (setup.inputs, prepared):
        with pytest.raises(TypeError):
            pickle.dumps(value)
    with pytest.raises(ExecutionError):
        replace(setup.inputs, clinical_sources=())


def test_wrong_configuration_schema_version_is_rejected_without_source_reads(setup):
    document = _config(setup)
    document["schema_version"] = "future-unsupported"
    with pytest.raises(ExecutionError):
        _load(setup, document)
    assert setup.reads == []


def test_atomic_publish_failure_leaves_only_incomplete_evidence(setup, monkeypatch):
    def rename_failed(_path, _target):
        message = "synthetic atomic publication failure"
        raise OSError(message)

    monkeypatch.setattr(Path, "rename", rename_failed)
    with pytest.raises(ExecutionError):
        _execute(setup)
    assert not (setup.tmp / "run" / "execution.json").exists()
    assert (setup.tmp / "run" / "execution.json.pending").exists()
    with pytest.raises(ExecutionError):
        e.verify_execution(setup.tmp / "run")
