"""Synthetic integration checks for source-first provider-transfer orchestration."""

from __future__ import annotations

import csv
import hashlib
import json
import pickle
import sys
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.assays import AssayFormatError
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AdmissionPlanError,
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
)
from tests.research.test_cptac_external_coverage import synthetic_assay, synthetic_protein
from tools import evaluate_cptac_gbm_provider_transfer as runner


def _plan(cohort, count):
    offset = 100_000 if cohort == "source" else 200_000
    candidates = tuple(
        CandidateBinding(
            case_submitter_id=f"synthetic-{cohort}-case-{index:03d}",
            sample_submitter_id=f"synthetic-{cohort}-sample-{index:03d}",
            gdc_sample_uuid=str(UUID(int=offset + 1000 + index)),
            protein_aliquot_submitter_id=f"SYNTHETIC-{cohort}-PROTEIN-{count - index:03d}",
            protein_aliquot_uuid=str(UUID(int=offset + 2000 + index)),
            rna_file_id=str(UUID(int=offset + 5000 - index)),
            cnv_file_id=str(UUID(int=offset + 7000 - index)),
        )
        for index in range(count)
    )
    lock = SourceLock(1, "1" * 32, "2" * 64)
    bindings = {}
    for candidate in reversed(candidates):
        for identifier, workflow in (
            (candidate.cnv_file_id, "AscatNGS"),
            (candidate.rna_file_id, "STAR - Counts"),
        ):
            bindings[identifier] = AssayInputBinding(identifier + ".bin", lock, workflow)
    receipt = ExternalAdmissionReceipt(
        profile_id=f"synthetic-{cohort}-metadata-plan/1.0.0",
        choices_sha256=("a" if cohort == "source" else "c") * 64,
        files_manifest_sha256=("b" if cohort == "source" else "d") * 64,
        candidate_count=count,
        rna_file_count=count,
        cnv_file_count=count,
        paired_file_count=2 * count,
        manifest_verified_bytes=2 * count,
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=("Synthetic metadata; no eligibility or independence claim.",),
    )
    return ExternalAdmissionPlan(candidates, bindings, receipt)


def _cohort_inputs(directory, cohort):
    return runner.CohortInputs(
        directory / cohort / "private-choices.json",
        ("a" if cohort == "source" else "c") * 64,
        directory / cohort / "private-manifest.json",
        ("b" if cohort == "source" else "d") * 64,
        directory / cohort / "private-protein.tsv",
        directory / cohort / "private-map.tsv",
    )


def _bundle(plan, *, source):
    count = len(plan.candidates)
    base = 100 if source else 10_000
    matrices = {
        family: base + axis * 100 + np.arange(16)[:, None] + np.arange(count)[None, :] / 1000
        for axis, family in enumerate(("cnv", "rna", "protein"))
    }
    for values in matrices.values():
        values[0, 0] = 0.0
    # A source failure and a separate external failure must remain distinct.
    matrices["protein"][-1 if source else -2] = np.nan
    protein = synthetic_protein(
        matrices["protein"], candidate_digest=sha256_digest(plan.protein_aliquots)
    )
    receipt = replace(
        protein.receipt,
        candidate_count=count,
        panel_coverage=tuple(
            replace(row, unshared_missing=count - row.unshared_finite)
            for row in protein.receipt.panel_coverage
        ),
    )
    return SimpleNamespace(
        matrices=matrices,
        protein=replace(protein, receipt=receipt),
        rna=[synthetic_assay(matrices["rna"][:, index], rna=True) for index in range(count)],
        cnv=[synthetic_assay(matrices["cnv"][:, index], rna=False) for index in range(count)],
    )


def _source_fit(protein):
    complete = int(np.isfinite(protein).sum())
    accepted = complete >= 60
    receipt = transfer.SourceFitReceipt(
        profile_id=transfer.PROFILE_ID,
        accepted=accepted,
        complete_count=complete,
        common_oof_count=complete if accepted else 0,
        valid_outer_folds=5 if accepted else 0,
        selected_candidate="full" if accepted else None,
        selection_evidence=tuple(
            transfer.FinalSelectionEvidence(
                candidate, accepted, complete, float(4 - index) if accepted else None
            )
            for index, candidate in enumerate(transfer.CANDIDATE_ORDER)
        ),
        nested_point_summary=None,
        fold_trace=(),
        final_fit_iterations=(0, 4, 5, 6) if accepted else (),
        failure_reason=None if accepted else "synthetic source support abstention",
    )
    return transfer.FrozenSourceGeneFit(receipt, ())


def _external_result(fit, protein, digest, index):
    complete = int(np.isfinite(protein).sum())
    accepted = fit.receipt.accepted and complete >= transfer.EXTERNAL_MINIMUM
    metrics = ()
    uncertainty = None
    contrast = None
    if accepted:
        contrast = 0.0 if index == 0 else -0.5
        metrics = tuple(
            transfer.TransferMetrics(
                candidate,
                complete,
                0.0 if index == 0 else error,
                0.0 if index == 0 else error,
                None,
            )
            for candidate, error in zip(
                (*transfer.CANDIDATE_ORDER, "selected_policy"),
                (3.0, 2.0, 1.5, 1.0, 1.0),
                strict=True,
            )
        )
        interval = transfer.ConditionalInterval(contrast, contrast, contrast, 0.9, 128)
        secondary = transfer.ConditionalInterval(0.0, 0.0, 0.0, 0.9, 128)
        uncertainty = transfer.ConditionalUncertainty(123, 128, 128, 103, interval, secondary, ())
    return transfer.TransferGeneResult(
        profile_id=transfer.PROFILE_ID,
        request_digest=digest,
        source=fit.receipt,
        accepted=accepted,
        external_complete_count=complete,
        external_common_comparison_count=complete if accepted else 0,
        external_minimum=transfer.EXTERNAL_MINIMUM,
        point_metrics=metrics,
        primary_full_minus_cnv_mae=contrast,
        secondary_selected_minus_full_mae=0.0 if accepted else None,
        uncertainty=uncertainty,
        failure_reason=None
        if accepted
        else fit.receipt.failure_reason or "synthetic external support abstention",
    )


def _processing_receipt(plans, inputs):
    return {
        "receipt_id": "cptac-raw-assay-processing-boundary/1.0.0",
        "selected_files_metadata_only": 256,
        "discovery_choices_sha256": inputs["source"].choices_sha256,
        "confirmatory_choices_sha256": inputs["external"].choices_sha256,
        "selected_file_set_digest": sha256_digest(
            sorted((*plans["source"].files, *plans["external"].files))
        ),
        "reference_material_equivalence_proven": False,
        "complete_processing_identity_proven": False,
        "genetic_donor_independence_proven": False,
        "cnv_gene_annotation_release_admitted": False,
        "gdc_workflow_groups": [
            {"cohort": cohort, "workflow_type": workflow, "files": count}
            for cohort, count in (("discovery", 72), ("confirmatory", 56))
            for workflow in ("STAR - Counts", "AscatNGS")
        ],
    }


class _Harness:
    def __init__(self, tmp_path):
        self.directory = tmp_path
        self.plans = {"source": _plan("source", 72), "external": _plan("external", 56)}
        self.inputs = {name: _cohort_inputs(tmp_path, name) for name in self.plans}
        self.bundles = {
            name: _bundle(plan, source=name == "source") for name, plan in self.plans.items()
        }
        self.arguments = {
            "discovery_map_bindings_path": tmp_path / "private-map-bindings.json",
            "discovery_map_bindings_sha256": "e" * 64,
            "hgnc_path": tmp_path / "private-hgnc.tsv",
            "processing_evidence_path": tmp_path / "private-processing.json",
        }
        self.processing = _processing_receipt(self.plans, self.inputs)
        self.calls = []
        self.events = []
        self.fits = []
        self.scores = []
        self.cohorts = {}
        self.failure = None
        self.output = tmp_path / "result"
        self.reference = object()
        self._reference_calls = 0

    def load(self, cohort, **kwargs):
        inputs = self.inputs[cohort]
        expected = {
            "choices_path": inputs.choices_path,
            "choices_sha256": inputs.choices_sha256,
            "files_manifest_path": inputs.files_manifest_path,
            "files_manifest_sha256": inputs.files_manifest_sha256,
        }
        if cohort == "source":
            expected.update(
                map_bindings_path=self.arguments["discovery_map_bindings_path"],
                map_bindings_sha256=self.arguments["discovery_map_bindings_sha256"],
            )
        assert kwargs == expected
        self.events.append(("plan", cohort))
        return self.plans[cohort]

    def before_measurement(self, cohort, stage):
        protocol = json.loads((self.output / "protocol.json").read_text())
        assert protocol["source_only_fit_before_any_external_measurement_read"] is True
        assert protocol["nested_source_gates"]["common_oof"] == 60
        if cohort == "external":
            assert len(self.fits) == 16
            receipts = json.loads((self.output / "source-fit-receipts.json").read_text())
            assert [row["gene"] for row in receipts["source_fits"]] == list(PANEL)
            assert receipts["external_measurements_read"] is False
            assert receipts["protocol_digest"] == protocol["protocol_digest"]
        self.events.append((stage, cohort))
        if self.failure == (cohort, stage):
            raise AssayFormatError

    def read_reference(self, path):
        cohort = "source" if self._reference_calls == 0 else "external"
        self._reference_calls += 1
        self.before_measurement(cohort, "hgnc")
        assert path == self.arguments["hgnc_path"]
        return self.reference

    def read_protein(self, cohort, **kwargs):
        self.before_measurement(cohort, "protein")
        inputs = self.inputs[cohort]
        assert kwargs == {
            "protein_path": inputs.protein_path,
            "sample_map_path": inputs.sample_map_path,
            "hgnc_path": self.arguments["hgnc_path"],
            "candidate_aliquots": self.plans[cohort].protein_aliquots,
        }
        return self.bundles[cohort].protein

    def read_assay(self, path, *, lock, hgnc, family):
        cohort = path.parent.name
        inputs, plan = self.inputs[cohort], self.plans[cohort]
        index = next(
            index
            for index, candidate in enumerate(plan.candidates)
            if path.name == getattr(candidate, f"{family}_file_id") + ".bin"
        )
        identifier = getattr(plan.candidates[index], f"{family}_file_id")
        assert path == inputs.files_manifest_path.parent / plan.files[identifier].relative_path
        assert lock == plan.files[identifier].lock
        assert hgnc is self.reference
        self.before_measurement(cohort, family)
        self.calls.append((cohort, family, index, path))
        if self.failure == (cohort, family, index):
            raise AssayFormatError
        return getattr(self.bundles[cohort], family)[index]

    def fit(self, cnv, rna, protein, folds):
        index = len(self.fits)
        assert len(self.calls) == 144
        assert all(cohort == "source" for cohort, *_ in self.calls)
        for family, values in (("cnv", cnv), ("rna", rna), ("protein", protein)):
            np.testing.assert_array_equal(values, self.bundles["source"].matrices[family][index])
            assert not values.flags.writeable
        np.testing.assert_array_equal(
            folds,
            transfer.deterministic_patient_folds(
                tuple(row.case_submitter_id for row in self.plans["source"].candidates)
            ),
        )
        result = _source_fit(protein)
        self.fits.append(result)
        self.events.append(("fit", PANEL[index]))
        return result

    def score(self, fit, cnv, rna, protein, *, request_digest):
        index = len(self.scores)
        assert len(self.calls) == 256
        assert fit is self.fits[index]
        for family, values in (("cnv", cnv), ("rna", rna), ("protein", protein)):
            np.testing.assert_array_equal(values, self.bundles["external"].matrices[family][index])
            assert not values.flags.writeable
        protocol = json.loads((self.output / "protocol.json").read_text())
        assert request_digest == sha256_digest(
            {"protocol_digest": protocol["protocol_digest"], "gene": PANEL[index]}
        )
        self.scores.append(request_digest)
        return _external_result(fit, protein, request_digest, index)

    def run(self, output=None):
        self.output = output or self.directory / "result"
        self.calls.clear()
        self.events.clear()
        self.fits.clear()
        self.scores.clear()
        self._reference_calls = 0
        payload = canonical_json_bytes(self.processing)
        self.arguments["processing_evidence_path"].write_bytes(payload)
        return runner.evaluate(
            discovery=self.inputs["source"],
            confirmatory=self.inputs["external"],
            **self.arguments,
            processing_evidence_sha256=hashlib.sha256(payload).hexdigest(),
            output_dir=self.output,
        )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    result = _Harness(tmp_path)
    monkeypatch.setattr(runner, "load_discovery_plan", lambda **kw: result.load("source", **kw))
    monkeypatch.setattr(
        runner.metadata, "load_admission_plan", lambda **kw: result.load("external", **kw)
    )
    monkeypatch.setattr(runner, "read_locked_hgnc", result.read_reference)
    monkeypatch.setattr(
        runner.source_protein,
        "admit_discovery_protein",
        lambda **kw: result.read_protein("source", **kw),
    )
    monkeypatch.setattr(
        runner.test_protein,
        "admit_confirmatory_protein",
        lambda **kw: result.read_protein("external", **kw),
    )
    monkeypatch.setattr(
        runner,
        "parse_star_counts_v36",
        lambda path, **kw: result.read_assay(path, family="rna", **kw),
    )
    monkeypatch.setattr(
        runner,
        "parse_ascat_gene_cnv",
        lambda path, **kw: result.read_assay(path, family="cnv", **kw),
    )
    monkeypatch.setattr(runner, "fit_source_gene", result.fit)
    monkeypatch.setattr(runner, "evaluate_external_gene", result.score)
    original_reader = runner._read_cohort

    def record_cohort(*args, **kwargs):
        matrix = original_reader(*args, **kwargs)
        result.cohorts["source" if kwargs["discovery"] else "external"] = matrix
        return matrix

    monkeypatch.setattr(runner, "_read_cohort", record_cohort)
    return result


def test_source_fits_every_gene_and_persists_receipts_before_external_measurements(harness, capsys):
    summary = harness.run()
    assert [(cohort, family, index) for cohort, family, index, _ in harness.calls] == [
        (cohort, family, index)
        for cohort, count in (("source", 72), ("external", 56))
        for index in range(count)
        for family in ("rna", "cnv")
    ]
    assert len({path for *_, path in harness.calls}) == 256
    assert Counter(cohort for cohort, *_ in harness.calls) == {"source": 144, "external": 112}
    assert harness.events[:4] == [
        ("plan", "source"),
        ("plan", "external"),
        ("hgnc", "source"),
        ("protein", "source"),
    ]
    last_fit = max(index for index, event in enumerate(harness.events) if event[0] == "fit")
    first_external = harness.events.index(("hgnc", "external"))
    assert last_fit < first_external
    assert summary["verified_assay_files"] == 256
    assert summary["accepted_genes"] == 14
    assert summary["abstained_genes"] == 2
    assert summary["aligned_external_validation"] is False
    assert capsys.readouterr().out == ""


def test_protocol_and_report_digests_bind_all_inputs_and_every_gene(harness):
    summary = harness.run()
    protocol = json.loads((harness.output / "protocol.json").read_text())
    digest = protocol.pop("protocol_digest")
    assert sha256_digest(protocol) == digest == summary["protocol_digest"]
    assert tuple(protocol["panel"]) == PANEL
    assert protocol["input_bindings"]["source_choices"] == "a" * 64
    assert protocol["input_bindings"]["external_manifest"] == "d" * 64
    assert protocol["bootstrap"]["training_refitted"] is False
    assert protocol["bootstrap"]["training_uncertainty_available"] is False
    assert protocol["nested_source_gates"]["common_oof"] == 60
    assert protocol["external_common_complete_minimum"] == 48
    assert protocol["aligned_external_validation"] is False
    report = json.loads((harness.output / "evaluation.json").read_text())
    report_digest = report.pop("report_digest")
    assert sha256_digest(report) == report_digest == summary["report_digest"]
    receipts = json.loads((harness.output / "source-fit-receipts.json").read_text())
    assert sha256_digest(receipts) == report["source_fit_receipts_digest"]
    assert [row["gene"] for row in report["genes"]] == list(PANEL)
    assert len({row["request_digest"] for row in report["genes"]}) == 16
    assert report["all_panel_genes_retained"] is True
    assert report["metadata_separation"]["donor_independence_admitted"] is False
    assert report["clinical_validation"] is report["default_promotion"] is False


def test_repeated_execution_produces_identical_canonical_artifacts(harness):
    first = harness.run(harness.directory / "first")
    second = harness.run(harness.directory / "second")
    assert first == second
    names = {"protocol.json", "source-fit-receipts.json", "evaluation.json", "summary.csv"}
    assert {path.name for path in harness.output.iterdir()} == names
    for name in names:
        assert (harness.directory / "first" / name).read_bytes() == (
            harness.directory / "second" / name
        ).read_bytes()


def _protocol_arguments(harness):
    return {
        "discovery": harness.inputs["source"],
        "confirmatory": harness.inputs["external"],
        "discovery_map_bindings_sha256": "e" * 64,
        "processing_evidence_sha256": "f" * 64,
    }


@pytest.mark.parametrize(
    ("cohort", "field", "binding"),
    [
        ("discovery", "choices_sha256", "source_choices"),
        ("discovery", "files_manifest_sha256", "source_manifest"),
        ("confirmatory", "choices_sha256", "external_choices"),
        ("confirmatory", "files_manifest_sha256", "external_manifest"),
        (None, "discovery_map_bindings_sha256", "source_channel_bindings"),
        (None, "processing_evidence_sha256", "processing_evidence"),
    ],
)
def test_each_frozen_metadata_input_changes_the_protocol_digest(harness, cohort, field, binding):
    arguments = _protocol_arguments(harness)
    original = runner.frozen_protocol(**arguments)
    if cohort is None:
        arguments[field] = "0" * 64
    else:
        arguments[cohort] = replace(arguments[cohort], **{field: "0" * 64})
    changed = runner.frozen_protocol(**arguments)
    assert changed["protocol_digest"] != original["protocol_digest"]
    assert changed["input_bindings"][binding] == "0" * 64
    assert changed["source_modules"] == original["source_modules"]


def test_parser_code_content_changes_the_frozen_protocol_without_editing_sources(
    harness, monkeypatch
):
    arguments = _protocol_arguments(harness)
    original = runner.frozen_protocol(**arguments)
    resources = runner.files

    def altered_resources(package):
        root = resources(package)
        if package != "glio_proteogen.research.cptac_gbm_external_admission":
            return root

        def joinpath(name):
            source = root.joinpath(name)
            if name != "assays.py":
                return source
            return SimpleNamespace(read_bytes=lambda: source.read_bytes() + b"\n# parser change")

        return SimpleNamespace(joinpath=joinpath)

    monkeypatch.setattr(runner, "files", altered_resources)
    changed = runner.frozen_protocol(**arguments)
    assert changed["protocol_digest"] != original["protocol_digest"]
    assert changed["source_modules"]["assays.py"] != original["source_modules"]["assays.py"]
    assert changed["nested_dependency_sources"] == original["nested_dependency_sources"]
    assert changed["input_bindings"] == original["input_bindings"]
    assert all(
        digest == original["source_modules"][name]
        for name, digest in changed["source_modules"].items()
        if name != "assays.py"
    )


def test_abstentions_are_retained_and_csv_distinguishes_zero_from_unavailable(harness):
    harness.run()
    with (harness.output / "summary.csv").open(newline="") as stream:
        rows = {row["gene"]: row for row in csv.DictReader(stream)}
    assert tuple(rows) == PANEL
    assert rows[PANEL[0]]["accepted"] == "True"
    for column in ("full_mae", "cnv_only_mae", "full_minus_cnv_mae", "primary_lower90"):
        assert rows[PANEL[0]][column] == "0.0"
        assert rows[PANEL[-1]][column] == rows[PANEL[-2]][column] == ""
    assert rows[PANEL[-1]]["source_complete"] == "0"
    assert rows[PANEL[-1]]["failure_reason"] == "synthetic source support abstention"
    assert rows[PANEL[-2]]["source_complete"] == "72"
    assert rows[PANEL[-2]]["external_complete"] == "0"
    assert rows[PANEL[-2]]["failure_reason"] == "synthetic external support abstention"
    assert "nan" not in (harness.output / "summary.csv").read_text().lower()
    report = json.loads((harness.output / "evaluation.json").read_text())
    for key in ("source_coverage", "external_coverage"):
        assert report[key][0]["zero_cnv"] == report[key][0]["zero_protein"] == 1


def test_transient_measurement_matrices_are_immutable_hidden_and_nonpickleable(harness):
    snapshots = {
        (cohort, family): values.tobytes()
        for cohort, bundle in harness.bundles.items()
        for family, values in bundle.matrices.items()
    }
    harness.run()
    for cohort, matrix in harness.cohorts.items():
        for family in ("cnv", "rna", "protein"):
            values = getattr(matrix, family)
            assert values.tobytes() == snapshots[cohort, family]
            with pytest.raises(ValueError):
                values.setflags(write=True)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(matrix)
        assert "array(" not in repr(matrix)


def test_outputs_export_aggregates_without_private_identifiers_or_measurements(harness):
    harness.run()
    text = "\n".join(path.read_text() for path in harness.output.iterdir())
    for plan in harness.plans.values():
        for candidate in plan.candidates:
            for field in candidate.__dataclass_fields__:
                assert getattr(candidate, field) not in text
    assert str(harness.directory) not in text
    assert "10000.001" not in text
    assert "_predictors" not in text
    for path in harness.output.glob("*.json"):
        runner._aggregate_only(json.loads(path.read_text()))


@pytest.mark.parametrize(
    "namespace",
    [
        "case_submitter_id",
        "sample_submitter_id",
        "gdc_sample_uuid",
        "protein_aliquot_submitter_id",
        "protein_aliquot_uuid",
        "rna_file_id",
    ],
)
def test_exact_cross_cohort_overlaps_fail_before_protocol_or_measurements(harness, namespace):
    source = harness.plans["source"].candidates[0]
    external = harness.plans["external"]
    overlapping = replace(external.candidates[0], **{namespace: getattr(source, namespace)})
    harness.plans["external"] = replace(
        external, candidates=(overlapping, *external.candidates[1:])
    )
    with pytest.raises(AdmissionPlanError, match="share exact"):
        harness.run()
    assert not harness.output.exists()
    assert harness.calls == harness.fits == []


@pytest.mark.parametrize(
    "failure",
    [
        ("source", "hgnc"),
        ("source", "protein"),
        ("source", "rna", 0),
        ("source", "cnv", 7),
        ("external", "hgnc"),
        ("external", "protein"),
        ("external", "cnv", 7),
    ],
)
def test_reader_failure_cannot_emit_partial_evaluation_or_summary(harness, failure):
    harness.failure = failure
    with pytest.raises(AssayFormatError):
        harness.run()
    expected = {"protocol.json"}
    if failure[0] == "external":
        expected.add("source-fit-receipts.json")
        assert len(harness.fits) == 16
    else:
        assert harness.fits == []
    assert {path.name for path in harness.output.iterdir()} == expected
    assert harness.scores == []


def test_unexpected_source_fitting_error_prevents_external_access_and_partial_receipts(
    harness, monkeypatch
):
    def fit(*args):
        if len(harness.fits) == 3:
            message = "synthetic numerical failure"
            raise ValueError(message)
        return harness.fit(*args)

    monkeypatch.setattr(runner, "fit_source_gene", fit)
    with pytest.raises(ValueError, match="synthetic numerical failure"):
        harness.run()
    assert len(harness.fits) == 3
    assert len(harness.calls) == 144
    assert all(cohort == "source" for cohort, *_ in harness.calls)
    assert {path.name for path in harness.output.iterdir()} == {"protocol.json"}


@pytest.mark.parametrize("cohort", ["source", "external"])
def test_protein_order_digest_mismatch_withholds_the_entire_cohort(harness, cohort):
    bundle = harness.bundles[cohort]
    bundle.protein = replace(bundle.protein, candidate_digest="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="ordered metadata plan differ"):
        harness.run()
    assert not (harness.output / "evaluation.json").exists()
    assert not (harness.output / "summary.csv").exists()
    assert harness.scores == []


def test_wrong_assay_axis_fails_before_any_source_fit(harness):
    harness.bundles["source"].rna[0] = synthetic_assay([1] * 16, rna=False)
    with pytest.raises(ValueError, match="assay family"):
        harness.run()
    assert harness.fits == []
    assert {path.name for path in harness.output.iterdir()} == {"protocol.json"}


def test_duplicate_protein_gene_identity_is_rejected_before_source_fitting(harness):
    bundle = harness.bundles["source"]
    bundle.protein = replace(
        bundle.protein,
        identities=(bundle.protein.identities[1], *bundle.protein.identities[1:]),
    )
    with pytest.raises(ValueError, match="identities are not unique"):
        harness.run()
    assert harness.fits == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("reference_material_equivalence_proven", True),
        ("complete_processing_identity_proven", 0),
        ("genetic_donor_independence_proven", True),
        ("cnv_gene_annotation_release_admitted", True),
        ("discovery_choices_sha256", "f" * 64),
        ("confirmatory_choices_sha256", "f" * 64),
        ("selected_file_set_digest", "sha256:" + "f" * 64),
    ],
)
def test_processing_evidence_must_match_the_exact_stress_boundary(harness, key, value):
    harness.processing[key] = value
    with pytest.raises(ValueError, match="stress boundary"):
        harness.run()
    assert not harness.output.exists()
    assert harness.calls == []


def test_processing_evidence_cannot_substitute_equal_total_wrong_workflow_counts(harness):
    groups = harness.processing["gdc_workflow_groups"]
    groups[0]["files"] -= 1
    groups[1]["files"] += 1
    assert sum(group["files"] for group in groups) == 256
    with pytest.raises(ValueError, match="every selected assay"):
        harness.run()
    assert not harness.output.exists()


def test_existing_output_is_preserved_without_reading_measurements(harness):
    harness.output.mkdir()
    keep = harness.output / "caller-owned.txt"
    keep.write_bytes(b"caller-owned")
    with pytest.raises(FileExistsError):
        harness.run()
    assert keep.read_bytes() == b"caller-owned"
    assert list(harness.output.iterdir()) == [keep]
    assert harness.calls == harness.fits == []


def test_invalid_plan_checksum_fails_before_protocol_and_measurement_readers(tmp_path, monkeypatch):
    discovery = _cohort_inputs(tmp_path, "source")
    discovery.choices_path.parent.mkdir()
    discovery.choices_path.write_bytes(b'{"synthetic-private-token":"not-admitted"}')
    discovery = replace(discovery, choices_sha256="0" * 64)

    def forbidden(*_args, **_kwargs):
        pytest.fail("a later boundary ran before source-plan checksum admission")

    for name in ("frozen_protocol", "_read_cohort", "fit_source_gene"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.metadata, "load_admission_plan", forbidden)
    output = tmp_path / "never-created"
    with pytest.raises(AdmissionPlanError):
        runner.evaluate(
            discovery=discovery,
            confirmatory=_cohort_inputs(tmp_path, "external"),
            discovery_map_bindings_path=tmp_path / "unused-bindings",
            discovery_map_bindings_sha256="e" * 64,
            hgnc_path=tmp_path / "unused-hgnc",
            processing_evidence_path=tmp_path / "unused-processing",
            processing_evidence_sha256="f" * 64,
            output_dir=output,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"nested": {"case_submitter_id": "synthetic-private"}}, ValueError),
        ({"protein_aliquot_uuid": "synthetic-private"}, ValueError),
        ({"nested": [{"predictions": [1]}]}, ValueError),
        ({"_predictors": []}, ValueError),
        ({"unexpected": [0] * 72}, ValueError),
        ({"unexpected": [0] * 56}, ValueError),
        ({"unexpected": np.zeros(16)}, TypeError),
    ],
)
def test_export_guard_rejects_individual_fields_and_arrays_before_file_creation(
    tmp_path, payload, error_type
):
    path = tmp_path / "never-created.json"
    with pytest.raises(error_type):
        runner._write_json(path, payload)
    assert not path.exists()


def _cli_arguments(tmp_path):
    arguments = ["provider-transfer"]
    for prefix in ("source", "external"):
        for name in ("choices", "files-manifest", "protein", "sample-map"):
            arguments.extend((f"--{prefix}-{name}", str(tmp_path / f"private-{prefix}-{name}")))
        for name in ("choices-sha256", "files-manifest-sha256"):
            arguments.extend((f"--{prefix}-{name}", "a" * 64))
    for name in ("source-map-bindings", "hgnc", "processing-evidence", "output-dir"):
        arguments.extend((f"--{name}", str(tmp_path / f"private-{name}")))
    for name in ("source-map-bindings-sha256", "processing-evidence-sha256"):
        arguments.extend((f"--{name}", "b" * 64))
    return arguments


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError])
def test_cli_errors_hide_private_paths_and_reader_details(
    tmp_path, monkeypatch, capsys, error_type
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    private_message = f"{tmp_path}/private-source synthetic-private-specimen"

    def fail(**_kwargs):
        raise error_type(private_message)

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Provider-transfer evaluation failed; private inputs or frozen contracts "
        "were not satisfied.\n"
    )
    assert str(tmp_path) not in output.err


def test_cli_maps_both_cohort_inputs_and_prints_only_aggregate_summary(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    expected = {"accepted_genes": 14, "abstained_genes": 2, "aligned_external_validation": False}

    def evaluate(**kwargs):
        for cohort, key in (("source", "discovery"), ("external", "confirmatory")):
            inputs = kwargs[key]
            assert inputs.choices_path == tmp_path / f"private-{cohort}-choices"
            assert inputs.files_manifest_path == tmp_path / f"private-{cohort}-files-manifest"
            assert inputs.choices_sha256 == inputs.files_manifest_sha256 == "a" * 64
        assert kwargs["discovery_map_bindings_sha256"] == "b" * 64
        assert kwargs["processing_evidence_path"] == tmp_path / "private-processing-evidence"
        return expected

    monkeypatch.setattr(runner, "evaluate", evaluate)
    assert runner.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected
    assert output.err == ""
