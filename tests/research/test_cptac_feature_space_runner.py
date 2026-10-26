"""Synthetic source-first orchestration and bounded aggregate export proofs."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import asdict, replace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.assays import AssayFormatError
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL
from glio_proteogen.research.cptac_gbm_feature_space import assays, atlas, cohort
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    CNV_AXIS,
    RNA_AXIS,
    STATES,
    FeatureAxis,
    FeatureMatrix,
    FeatureSpaceError,
    ProjectedAssay,
    ProjectionReceipt,
)
from tests.research.test_cptac_feature_space_atlas import _folds, _matrix
from tests.research.test_cptac_feature_space_cohort import _identity, _protein, _reference
from tests.research.test_cptac_provider_transfer_runner import (
    _cli_arguments,
    _cohort_inputs,
    _plan,
    _processing_receipt,
)
from tools import evaluate_cptac_gbm_feature_space as runner


class _Harness:
    def __init__(self, directory):
        self.directory = directory
        self.output = directory / "result"
        self.inputs = {name: _cohort_inputs(directory, name) for name in ("source", "external")}
        self.plans = {"source": _plan("source", 72), "external": _plan("external", 56)}
        anchors = tuple(_identity(index, symbol) for index, symbol in enumerate(PANEL, start=1))
        self.identities = (
            *anchors,
            _identity(17),
            replace(_identity(18), ensembl_gene_id=None),
            _identity(19),
        )
        self.reference = _reference(self.identities)
        source_genes = (
            *reversed(tuple(gene for gene in anchors if gene.symbol not in ("CDKN2B", "MDM2"))),
            self.identities[16],
            self.identities[17],
            None,
        )
        external_genes = (*anchors, self.identities[18])
        self.proteins = {}
        for name, genes in (("source", source_genes), ("external", external_genes)):
            count = len(self.plans[name].candidates)
            values = np.tile(np.arange(count, dtype=np.float64) - 2, (len(genes), 1))
            for row, gene in enumerate(genes):
                if gene is not None and gene.symbol == ("TP53" if name == "source" else "MDM4"):
                    values[row, : 20 if name == "source" else 10] = np.nan
            self.proteins[name] = _protein(genes, self.plans[name], values)
        self.arguments = {
            "discovery": self.inputs["source"],
            "confirmatory": self.inputs["external"],
            "discovery_map_bindings_path": directory / "private-map-bindings.json",
            "discovery_map_bindings_sha256": "e" * 64,
            "hgnc_path": directory / "private-hgnc.tsv",
            "processing_evidence_path": directory / "private-processing.json",
        }
        self.processing = _processing_receipt(self.plans, self.inputs)
        self.events, self.calls, self.matrices = [], [], {}
        self.failure = None

    def load(self, name, **kwargs):
        inputs = self.inputs[name]
        expected = {
            "choices_path": inputs.choices_path,
            "choices_sha256": inputs.choices_sha256,
            "files_manifest_path": inputs.files_manifest_path,
            "files_manifest_sha256": inputs.files_manifest_sha256,
        }
        if name == "source":
            expected.update(
                map_bindings_path=self.arguments["discovery_map_bindings_path"],
                map_bindings_sha256=self.arguments["discovery_map_bindings_sha256"],
            )
        assert kwargs == expected
        self.events.append(("plan", name))
        if self.failure == ("plan", name):
            raise ValueError
        return self.plans[name]

    def boundary(self, name, stage):
        protocol = json.loads((self.output / "protocol.json").read_text())
        assert protocol["source_catalog_persisted_before_external_measurement_reads"] is True
        assert protocol["model_fits_performed"] is False
        if name == "external":
            source = json.loads((self.output / "source-catalog.json").read_text())
            assert source["external_measurements_read"] is False
            assert source["protocol_digest"] == protocol["protocol_digest"]
            assert (
                sha256_digest(
                    {key: value for key, value in source.items() if key != "source_document_digest"}
                )
                == source["source_document_digest"]
            )
            assert len(self.calls) >= 144
        self.events.append((stage, name))
        if self.failure == (stage, name):
            raise AssayFormatError

    def read_reference(self, path):
        assert path == self.arguments["hgnc_path"]
        self.boundary("source", "hgnc")
        return self.reference

    def read_protein(self, name, **kwargs):
        self.boundary(name, "protein")
        inputs, plan = self.inputs[name], self.plans[name]
        assert kwargs == {
            "protein_path": inputs.protein_path,
            "sample_map_path": inputs.sample_map_path,
            "hgnc_path": self.arguments["hgnc_path"],
            "candidate_aliquots": plan.protein_aliquots,
        }
        return self.proteins[name]

    def read_assay(self, path, *, lock, hgnc, axis, rna):
        name = path.parent.name
        self.boundary(name, "rna" if rna else "cnv")
        plan = self.plans[name]
        column = next(
            index
            for index, candidate in enumerate(plan.candidates)
            if path.name == getattr(candidate, "rna_file_id" if rna else "cnv_file_id") + ".bin"
        )
        candidate = plan.candidates[column]
        file_id = candidate.rna_file_id if rna else candidate.cnv_file_id
        binding = plan.files[file_id]
        assert path == self.inputs[name].files_manifest_path.parent / binding.relative_path
        assert lock == binding.lock and hgnc is self.reference
        if name == "external":
            assert axis is self.matrices["source"].axis
        self.calls.append((name, "rna" if rna else "cnv", column, path))
        states = np.array(
            [2 if gene.ensembl_gene_id is None else 0 for gene in axis.identities], dtype=np.uint8
        )
        values = np.array([float((column + index) % 4) for index in range(len(states))])
        values[states != 0] = np.nan
        receipt = ProjectionReceipt(
            axis=RNA_AXIS if rna else CNV_AXIS,
            workflow=binding.workflow,
            annotation_release="GENCODE v36" if rna else None,
            input_bytes=lock.bytes,
            data_rows=24 if rna else 20,
            gene_rows=20,
            summary_rows=4 if rna else 0,
            versioned_gene_rows=20,
            par_y_gene_rows=0,
            duplicate_gene_symbol_groups=0,
            ambiguous_reference_gene_ids=0,
            missing_gene_rows=0,
            observed_zero_gene_rows=int(np.count_nonzero(values == 0)),
            feature_axis_digest=axis.digest,
            feature_count=len(states),
            state_counts=tuple(int(np.sum(states == code)) for code in range(6)),
        )
        return ProjectedAssay(receipt, values, states)

    def run(self, output=None):
        self.output = output or self.output
        self.events.clear()
        self.calls.clear()
        self.matrices.clear()
        payload = canonical_json_bytes(self.processing)
        self.arguments["processing_evidence_path"].write_bytes(payload)
        return runner.evaluate(
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
        runner.external_protein,
        "admit_confirmatory_protein",
        lambda **kw: result.read_protein("external", **kw),
    )
    monkeypatch.setattr(
        assays, "parse_star_counts_v36", lambda path, **kw: result.read_assay(path, rna=True, **kw)
    )
    monkeypatch.setattr(
        assays, "parse_ascat_gene_cnv", lambda path, **kw: result.read_assay(path, rna=False, **kw)
    )
    original_build = runner.build_cohort_matrix

    def build(**kwargs):
        admission = original_build(**kwargs)
        name = "source" if kwargs["plan"] is result.plans["source"] else "external"
        result.matrices[name] = admission.matrix
        return admission

    monkeypatch.setattr(runner, "build_cohort_matrix", build)
    # The synthetic locks are not the historical real-data locks. Keep the full
    # real protocol constructor while binding this fixture's canonical digest.
    payload = canonical_json_bytes(result.processing)
    expected = runner.parent.frozen_protocol(
        discovery=result.inputs["source"],
        confirmatory=result.inputs["external"],
        discovery_map_bindings_sha256="e" * 64,
        processing_evidence_sha256=hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(runner, "SOURCE_INPUT_PROTOCOL_DIGEST", expected["protocol_digest"])
    return result


def _documents(directory):
    return {
        name: json.loads((directory / name).read_bytes())
        for name in (
            "protocol.json",
            "source-catalog.json",
            "external-coverage.json",
            "evaluation.json",
        )
    }


def test_full_source_catalog_is_persisted_before_any_external_measurement(
    harness, monkeypatch, capsys
):
    def forbidden_fit(*_args, **_kwargs):
        pytest.fail("coverage admission invoked a model operation")

    monkeypatch.setattr(transfer, "fit_source_gene", forbidden_fit)
    monkeypatch.setattr(transfer, "evaluate_external_gene", forbidden_fit)
    monkeypatch.setattr(runner.parent, "fit_source_gene", forbidden_fit)
    monkeypatch.setattr(runner.parent, "evaluate_external_gene", forbidden_fit)
    summary = harness.run()
    assert [(name, family, column) for name, family, column, _ in harness.calls] == [
        (name, family, column)
        for name, count in (("source", 72), ("external", 56))
        for column in range(count)
        for family in ("rna", "cnv")
    ]
    assert len({path for *_, path in harness.calls}) == 256
    assert harness.events[:4] == [
        ("plan", "source"),
        ("plan", "external"),
        ("hgnc", "source"),
        ("protein", "source"),
    ]
    assert summary["verified_assay_files"] == 256
    assert summary["model_fits_performed"] is False
    assert capsys.readouterr().out == ""
    assert {path.name for path in harness.output.iterdir()} == {
        "protocol.json",
        "source-catalog.json",
        "external-coverage.json",
        "evaluation.json",
        "summary.csv",
    }


def test_all_document_hashes_axis_receipts_and_source_only_counts_bind(harness):
    summary = harness.run()
    docs = _documents(harness.output)
    protocol, source, external, report = docs.values()
    for name, key in (
        ("protocol.json", "protocol_digest"),
        ("source-catalog.json", "source_document_digest"),
        ("external-coverage.json", "external_document_digest"),
        ("evaluation.json", "report_digest"),
    ):
        document = docs[name]
        assert (
            sha256_digest({field: value for field, value in document.items() if field != key})
            == document[key]
        )
        assert canonical_json_bytes(document) == (harness.output / name).read_bytes()
    assert (
        source["catalog_digest"]
        == sha256_digest(source["source_catalog"])
        == external["source_catalog_digest"]
        == report["source_catalog_digest"]
    )
    assert (
        external["external_catalog_digest"]
        == sha256_digest(external["external_catalog"])
        == report["external_catalog_digest"]
    )
    assert (
        external["source_document_digest"]
        == source["source_document_digest"]
        == report["source_document_digest"]
    )
    assert external["external_document_digest"] == report["external_document_digest"]
    assert report["source_build_digest"] == sha256_digest(source["source_build_receipt"])
    assert report["external_build_digest"] == sha256_digest(external["external_build_receipt"])
    assert summary["report_digest"] == report["report_digest"]
    assert (
        source["source_catalog"]["feature_axis_digest"]
        == external["external_catalog"]["feature_axis_digest"]
        == report["feature_axis_digest"]
    )
    assert report["source_feature_count"] == 18
    assert report["source_count_capacity_genes"] == 14
    assert report["external_count_sufficient_genes"] == 15
    assert report["source_and_external_count_sufficient_genes"] == 12
    assert (
        report["literature_anchor_count"] == 16
        and report["all_literature_anchors_retained"] is True
    )
    assert report["unresolved_source_protein_rows"] == 1
    assert "genes" not in report
    assert (
        protocol["source_fold_assignment_digest"]
        == source["source_catalog"]["source_fold_assignment_digest"]
    )


def test_protocol_binds_all_new_sources_historical_locks_and_limits(harness):
    harness.run()
    protocol = _documents(harness.output)["protocol.json"]
    assert set(protocol["method_sources"]) == {
        "__init__.py",
        "contracts.py",
        "assays.py",
        "cohort.py",
        "atlas.py",
    }
    for name, digest in protocol["method_sources"].items():
        assert digest == runner.parent._digest(
            runner.files("glio_proteogen.research.cptac_gbm_feature_space")
            .joinpath(name)
            .read_bytes()
        )
    assert protocol["tool_source_digest"] == runner.parent._digest(
        runner.Path(runner.__file__).read_bytes()
    )
    assert protocol["source_input_protocol"]["input_bindings"]["source_choices"] == "a" * 64
    assert protocol["maximum_features"] == 20_000
    assert protocol["maximum_cases"] == 1000
    assert protocol["maximum_gene_case_cells"] == 2_000_000
    assert protocol["maximum_json_bytes"] == 64 * 1024 * 1024
    assert protocol["source_count_capacity"] == {
        "joint_complete": 60,
        "minimum_validation_joint": 3,
        "minimum_outer_training_joint": 48,
        "minimum_inner_training_joint": 32,
        "all_five_original_folds_required": True,
        "ordered_inner_training_contexts": 20,
        "establishes_fitted_eligibility": False,
    }
    assert protocol["source_variation_diagnostics"]["training_contexts"] == 26
    assert protocol["external_joint_complete_descriptive_minimum"] == 48


def test_csv_keeps_absent_anchors_nonpanel_genes_zero_counts_and_all_states(harness):
    harness.run()
    with (harness.output / "summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["hgnc_id"] for row in rows] == sorted(row["hgnc_id"] for row in rows)
    assert len(rows) == 18 and set(PANEL).issubset({row["symbol"] for row in rows})
    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["CDKN2B"]["source_protein_absent_feature"] == "72"
    assert by_symbol["CDKN2B"]["source_joint_complete"] == "0"
    assert by_symbol["CDKN2B"]["source_all_five_fold_count_support_possible"] == "False"
    assert by_symbol["CDKN2B"]["external_protein_observed"] == "56"
    assert by_symbol["SYNTHETIC17"]["external_protein_absent_feature"] == "56"
    assert by_symbol["SYNTHETIC17"]["source_all_five_fold_count_support_possible"] == "True"
    assert by_symbol["SYNTHETIC18"]["source_rna_unresolved_reference"] == "72"
    assert by_symbol["SYNTHETIC18"]["ensembl_gene_id"] == ""
    assert "SYNTHETIC19" not in by_symbol
    for row in rows:
        for name, count in (("source", 72), ("external", 56)):
            assert sum(int(row[f"{name}_pattern_{pattern}"]) for pattern in atlas.PATTERNS) == count
            for family in ("cnv", "rna", "protein"):
                assert sum(int(row[f"{name}_{family}_{state}"]) for state in STATES) == count
        assert row["source_training_contexts"] == "26"
        assert all(row[f"source_fold_{fold}_joint"] != "" for fold in range(5))
    assert int(by_symbol["CDK4"]["source_zero_cnv"]) > 0


def test_external_poison_cannot_change_frozen_source_catalog(harness):
    first = harness.directory / "first"
    harness.run(first)
    baseline = (first / "source-catalog.json").read_bytes()
    admission = harness.proteins["external"]
    values = np.full(admission.values.shape, np.nan)
    harness.proteins["external"] = _protein(admission.identities, harness.plans["external"], values)
    second = harness.directory / "second"
    harness.run(second)
    assert (second / "source-catalog.json").read_bytes() == baseline
    report = _documents(second)["evaluation.json"]
    assert report["source_count_capacity_genes"] == 14
    assert report["external_count_sufficient_genes"] == 0
    assert report["source_and_external_count_sufficient_genes"] == 0


def test_repeated_complete_run_is_byte_identical_and_never_exports_private_tokens(harness):
    first, second = harness.directory / "first", harness.directory / "second"
    harness.run(first)
    harness.run(second)
    tokens = {str(harness.directory)}
    for plan in harness.plans.values():
        for candidate in plan.candidates:
            tokens.update(asdict(candidate).values())
    for path in first.iterdir():
        payload = path.read_bytes()
        assert payload == (second / path.name).read_bytes()
        text = payload.decode()
        assert all(token not in text for token in tokens)
    docs = _documents(first)
    for document in (docs["protocol.json"], docs["evaluation.json"]):
        assert all(document[name] is False for name in runner._FALSE_FLAGS)
        assert document["redistribution_status"] == "local_only_terms_unverified"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (("plan", "source"), set()),
        (("plan", "external"), set()),
        (("hgnc", "source"), {"protocol.json"}),
        (("protein", "source"), {"protocol.json"}),
        (("rna", "source"), {"protocol.json"}),
        (("protein", "external"), {"protocol.json", "source-catalog.json"}),
        (("cnv", "external"), {"protocol.json", "source-catalog.json"}),
    ],
)
def test_admission_failures_preserve_only_completed_prior_phases(harness, failure, expected):
    harness.failure = failure
    with pytest.raises(ValueError):
        harness.run()
    assert (
        {path.name for path in harness.output.iterdir()} if harness.output.exists() else set()
    ) == expected
    if failure[1] == "source":
        assert all(name == "source" for name, *_ in harness.calls)


def test_existing_output_is_not_overwritten_or_read_for_measurements(harness):
    harness.output.mkdir()
    marker = harness.output / "owned.txt"
    marker.write_text("synthetic marker")
    with pytest.raises(FileExistsError):
        harness.run()
    assert marker.read_text() == "synthetic marker"
    assert harness.calls == []
    assert all(event[0] == "plan" for event in harness.events)


def test_metadata_overlap_and_processing_mismatch_fail_before_measurements(harness):
    external = harness.plans["external"]
    first = replace(
        external.candidates[0],
        case_submitter_id=harness.plans["source"].candidates[0].case_submitter_id,
    )
    harness.plans["external"] = replace(external, candidates=(first, *external.candidates[1:]))
    with pytest.raises(ValueError, match="share exact"):
        harness.run()
    assert not harness.output.exists() and harness.calls == []
    harness.plans["external"] = external
    harness.processing["selected_file_set_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="processing evidence"):
        harness.run()
    assert not harness.output.exists() and harness.calls == []


@pytest.mark.parametrize("failure", ["bad_hash", "wrong_frozen_protocol"])
def test_invalid_input_binding_or_parent_protocol_never_reaches_measurements(
    harness, monkeypatch, failure
):
    if failure == "bad_hash":
        harness.arguments["discovery_map_bindings_sha256"] = "PRIVATE-BAD-HASH"
    else:
        monkeypatch.setattr(runner, "SOURCE_INPUT_PROTOCOL_DIGEST", "sha256:" + "0" * 64)
    with pytest.raises(ValueError):
        harness.run()
    assert not harness.output.exists() and harness.calls == []


def test_loss_of_a_declared_anchor_blocks_source_catalog_and_external_reads(harness, monkeypatch):
    original = runner.derive_source_axis

    def incomplete_axis(**kwargs):
        universe = original(**kwargs)
        axis = FeatureAxis(
            tuple(gene for gene in universe.axis.identities if gene.symbol != "CDK4")
        )
        return replace(universe, axis=axis)

    monkeypatch.setattr(runner, "derive_source_axis", incomplete_axis)
    with pytest.raises(FeatureSpaceError, match="sixteen literature anchors"):
        harness.run()
    assert harness.calls == []
    assert {path.name for path in harness.output.iterdir()} == {"protocol.json"}


def test_external_axis_drift_fails_without_a_final_report(harness, monkeypatch):
    original = runner.build_cohort_matrix

    def drift(**kwargs):
        admission = original(**kwargs)
        if kwargs["plan"] is harness.plans["external"]:
            matrix = admission.matrix
            first, *remaining = matrix.axis.identities
            axis = FeatureAxis((replace(first, entrez_id="99999"), *remaining))
            matrix = FeatureMatrix(
                axis,
                matrix.candidate_digest,
                matrix.cnv,
                matrix.rna,
                matrix.protein,
                matrix.cnv_states,
                matrix.rna_states,
                matrix.protein_states,
            )
            return cohort.CohortAdmission(matrix, admission.receipt)
        return admission

    monkeypatch.setattr(runner, "build_cohort_matrix", drift)
    with pytest.raises(FeatureSpaceError, match="cannot change"):
        harness.run()
    assert {path.name for path in harness.output.iterdir()} == {
        "protocol.json",
        "source-catalog.json",
    }


def test_summary_refuses_different_gene_identities(tmp_path):
    matrix = _matrix(features=2)
    source = atlas.build_source_catalog(matrix, _folds())
    external = atlas.project_external_coverage(source, _matrix(axis=matrix.axis, cases=56))
    external = replace(external, genes=tuple(reversed(external.genes)))
    with pytest.raises(FeatureSpaceError, match="gene identities differ"):
        runner._write_summary(tmp_path / "bad.csv", source, external)
    assert not (tmp_path / "bad.csv").exists()


def test_catalog_export_needs_its_axis_and_typed_gene_records(tmp_path):
    matrix = _matrix()
    catalog = atlas.build_source_catalog(matrix, _folds())
    payload = {"source_catalog": asdict(catalog)}
    with pytest.raises(FeatureSpaceError, match="requires its admitted feature axis"):
        runner._write_json(tmp_path / "no-axis.json", payload, catalog=catalog)
    invalid = replace(catalog, genes=(object(),))
    with pytest.raises(FeatureSpaceError, match="typed aggregate gene records"):
        runner._write_json(tmp_path / "untyped.json", payload, catalog=invalid, axis=matrix.axis)


@pytest.mark.parametrize("count", [56, 72, 112, 144])
def test_only_typed_axis_bound_gene_records_bypass_patient_length_guard(tmp_path, count):
    matrix = _matrix(features=count)
    catalog = atlas.build_source_catalog(matrix, _folds())
    document = {"source_catalog": asdict(catalog)}
    with pytest.raises(ValueError, match="vectors"):
        runner._write_json(tmp_path / "untyped.json", document)
    runner._write_json(tmp_path / "typed.json", document, catalog=catalog, axis=matrix.axis)
    assert (
        len(json.loads((tmp_path / "typed.json").read_bytes())["source_catalog"]["genes"]) == count
    )
    changed = replace(matrix.axis.identities[0], entrez_id="99999")
    wrong_axis = FeatureAxis((changed, *matrix.axis.identities[1:]))
    with pytest.raises(FeatureSpaceError, match="feature axis"):
        runner._write_json(tmp_path / "wrong-axis.json", document, catalog=catalog, axis=wrong_axis)
    document["source_catalog"]["genes"] = ()
    with pytest.raises(FeatureSpaceError, match="typed aggregate"):
        runner._write_json(tmp_path / "changed.json", document, catalog=catalog, axis=matrix.axis)


def _histogram_receipt():
    plan = _plan("external", 56)
    protein = _protein((_identity(1),), plan)
    histogram = cohort.SchemaHistogram(
        "gene_rows", tuple(cohort.SchemaHistogramBin(value, 1) for value in range(56))
    )
    summary = cohort.AxisSchemaSummary(
        RNA_AXIS, "STAR - Counts", "GENCODE v36", 56, 56, 1, (56, 0, 0, 0, 0, 0), (histogram,)
    )
    return cohort.CohortBuildReceipt(
        runner.PROFILE_ID,
        "sha256:" + "a" * 64,
        protein.candidate_digest,
        56,
        56,
        56,
        protein.receipt,
        0,
        (summary,),
    )


def test_typed_histogram_bins_conserve_files_without_untyped_vector_exception(tmp_path):
    receipt = _histogram_receipt()
    payload = {"external_build_receipt": asdict(receipt)}
    with pytest.raises(ValueError, match="vectors"):
        runner._write_json(tmp_path / "untyped.json", payload)
    runner._write_json(tmp_path / "typed.json", payload, build_receipts=(receipt,))
    assert (tmp_path / "typed.json").exists()


@pytest.mark.parametrize(
    "failure", ["untyped_receipt", "untyped_summary", "untyped_bin", "document_mismatch"]
)
def test_histogram_exception_requires_exact_typed_record_and_payload(tmp_path, failure):
    receipt = _histogram_receipt()
    if failure == "untyped_receipt":
        receipt = object()
    elif failure == "untyped_summary":
        receipt = replace(receipt, schema_summaries=(object(),))
    elif failure == "untyped_bin":
        summary = receipt.schema_summaries[0]
        histogram = replace(summary.histograms[0], bins=(object(),))
        receipt = replace(receipt, schema_summaries=(replace(summary, histograms=(histogram,)),))
    with pytest.raises(FeatureSpaceError):
        runner._write_json(tmp_path / "bad.json", {}, build_receipts=(receipt,))
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize("mutation", ["zero_files", "negative_value", "lost_file", "extra_bin"])
def test_invalid_typed_histogram_never_weakens_privacy_guard(tmp_path, mutation):
    receipt = _histogram_receipt()
    summary = receipt.schema_summaries[0]
    histogram = summary.histograms[0]
    bins = histogram.bins
    if mutation == "zero_files":
        bins = (replace(bins[0], files=0), *bins[1:])
    elif mutation == "negative_value":
        bins = (replace(bins[0], value=-1), *bins[1:])
    elif mutation == "lost_file":
        bins = bins[:-1]
    else:
        bins = (*bins, cohort.SchemaHistogramBin(56, 1))
    receipt = replace(
        receipt, schema_summaries=(replace(summary, histograms=(replace(histogram, bins=bins),)),)
    )
    with pytest.raises(FeatureSpaceError, match="conserve"):
        runner._write_json(
            tmp_path / "bad.json",
            {"external_build_receipt": asdict(receipt)},
            build_receipts=(receipt,),
        )
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"values": [1]}, ValueError),
        ({"predictions": [1]}, ValueError),
        ({"fold_memberships": [0]}, ValueError),
        ({"patient_indices": [0]}, ValueError),
        ({"draws": [0]}, ValueError),
        ({"case_submitter_id": "synthetic private"}, ValueError),
        ({"arbitrary": np.zeros(2)}, TypeError),
        ({"arbitrary": list(range(72))}, ValueError),
    ],
)
def test_exports_reject_measurement_arrays_memberships_identifiers_and_predictions(
    tmp_path, payload, error
):
    with pytest.raises(error):
        runner._write_json(tmp_path / "rejected.json", payload)
    assert not (tmp_path / "rejected.json").exists()


def test_json_bound_is_inclusive_and_no_partial_file_is_created(tmp_path, monkeypatch):
    payload = {"aggregate": "synthetic"}
    size = len(canonical_json_bytes(payload))
    monkeypatch.setattr(runner, "MAX_JSON_BYTES", size)
    runner._write_json(tmp_path / "exact.json", payload)
    monkeypatch.setattr(runner, "MAX_JSON_BYTES", size - 1)
    with pytest.raises(FeatureSpaceError, match="bounded"):
        runner._write_json(tmp_path / "too-large.json", payload)
    assert not (tmp_path / "too-large.json").exists()


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError])
def test_cli_failure_is_generic_without_private_paths(tmp_path, monkeypatch, capsys, error_type):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))

    def fail(**_kwargs):
        private_message = f"{tmp_path} synthetic-private-specimen"
        raise error_type(private_message)

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    output = capsys.readouterr()
    assert error.value.code == 2 and output.out == ""
    assert (
        output.err == "Feature-space admission failed; private inputs or frozen contracts "
        "were not satisfied.\n"
    )
    assert str(tmp_path) not in output.err


def test_cli_maps_exact_cohort_inputs_and_only_prints_aggregate_summary(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", _cli_arguments(tmp_path))
    expected = {"source_feature_count": 18, "model_fits_performed": False}

    def evaluate(**kwargs):
        for name, key in (("source", "discovery"), ("external", "confirmatory")):
            assert kwargs[key].protein_path == tmp_path / f"private-{name}-protein"
            assert kwargs[key].sample_map_path == tmp_path / f"private-{name}-sample-map"
            assert kwargs[key].choices_sha256 == kwargs[key].files_manifest_sha256 == "a" * 64
        assert kwargs["discovery_map_bindings_sha256"] == "b" * 64
        assert kwargs["output_dir"] == tmp_path / "private-output-dir"
        return expected

    monkeypatch.setattr(runner, "evaluate", evaluate)
    assert runner.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected and output.err == ""
