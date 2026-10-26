# ruff: noqa: TRY003
"""Synthetic full-axis orchestration using actual fitting, receipt storage and replay."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_feature_space import assays, atlas, cohort
from glio_proteogen.research.cptac_gbm_feature_space.contracts import FeatureMatrix
from glio_proteogen.research.cptac_gbm_source_fit_census import engine
from glio_proteogen.research.cptac_gbm_source_fit_census.contracts import (
    INPUT_DOMAIN_REJECTION,
    MANIFEST_NAME,
    CensusError,
)
from tests.research.test_cptac_feature_space_cohort import _identity, _protein, _reference
from tests.research.test_cptac_feature_space_runner import _Harness as FeatureHarness
from tests.research.test_cptac_provider_transfer_runner import _cli_arguments
from tools import evaluate_cptac_gbm_source_fit_census as runner


def _manual_digest(document):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )


@lru_cache(maxsize=256)
def _historical_result(symbol, protocol_digest, source_bytes, external_bytes, fold_bytes):
    # Only the independently generated synthetic parent is cached. Every census
    # run below still executes the actual unchanged fitter for every identity.
    source = tuple(np.frombuffer(value, dtype=np.float64) for value in source_bytes)
    external = tuple(np.frombuffer(value, dtype=np.float64) for value in external_bytes)
    fit = transfer.fit_source_gene(*source, np.frombuffer(fold_bytes, dtype=np.int8))
    return transfer.evaluate_external_gene(
        fit,
        *external,
        request_digest=sha256_digest({"protocol_digest": protocol_digest, "gene": symbol}),
    )


class _Harness(FeatureHarness):
    def __init__(self, directory):
        super().__init__(directory)
        anchors = self.identities[:16]
        self.identities = (*anchors, *(_identity(i) for i in range(17, 25)))
        self.identities = tuple(
            replace(gene, ensembl_gene_id=None) if gene.hgnc_id == "HGNC:18" else gene
            for gene in self.identities
        )
        self.reference = _reference(self.identities)
        self.data = {}
        for name, cases in (("source", 72), ("external", 56)):
            rows = {}
            for gene in self.identities:
                rng = np.random.default_rng(
                    13000 + int(gene.entrez_id) + (0 if name == "source" else 1000)
                )
                cnv = rng.integers(0, 7, size=cases).astype(np.float64)
                rna = rng.uniform(0.5, 9, size=cases)
                rna[0] = 0
                target = 0.3 + 1.5 * rna + 0.4 * cnv + rng.normal(scale=0.1, size=cases)
                if gene.ensembl_gene_id is None:
                    cnv[:], rna[:] = np.nan, np.nan
                if name == "source" and gene.hgnc_id == "HGNC:20":
                    cnv[0] = 1e12 + 1
                if name == "source" and gene.hgnc_id == "HGNC:24":
                    rna[:] = 0
                if name == "external" and gene.hgnc_id == "HGNC:23":
                    rna[0] = 1e12 + 1
                if name == "source" and (gene.symbol == "TP53" or gene.hgnc_id == "HGNC:17"):
                    target[:20] = np.nan
                if name == "external" and gene.hgnc_id == "HGNC:22":
                    target[:10] = np.nan
                rows[gene.hgnc_id] = {"cnv": cnv, "rna": rna, "protein": target}
            self.data[name] = rows
        for name in ("source", "external"):
            selected = (
                tuple(
                    gene
                    for gene in self.identities
                    if (gene.symbol not in ("CDKN2B", "MDM2") and gene.hgnc_id != "HGNC:19")
                    if name == "source"
                )
                if name == "source"
                else self.identities
            )
            genes = (*reversed(selected), None) if name == "source" else selected
            values = np.vstack(
                [
                    self.data[name][gene.hgnc_id]["protein"] if gene else np.full(72, -0.3)
                    for gene in genes
                ]
            )
            self.proteins[name] = _protein(genes, self.plans[name], values)
        self.universe = cohort.derive_source_axis(
            protein=self.proteins["source"], hgnc=self.reference
        )
        self.folds = transfer.deterministic_patient_folds(
            tuple(row.case_submitter_id for row in self.plans["source"].candidates)
        )
        self.fit_calls, self.score_calls = [], []
        self.fail_fit_at = None
        self.source_matrix = self.make_matrix("source")

    def make_matrix(self, name):
        cases = len(self.plans[name].candidates)
        axis = self.universe.axis
        protein_rows = {gene.hgnc_id for gene in self.proteins[name].identities if gene is not None}
        values, states = [], []
        for measure in ("cnv", "rna", "protein"):
            array = np.vstack(
                [
                    self.data[name][gene.hgnc_id][measure]
                    if measure != "protein" or gene.hgnc_id in protein_rows
                    else np.full(cases, np.nan)
                    for gene in axis.identities
                ]
            )
            codes = np.where(np.isfinite(array), 0, 5).astype(np.uint8)
            for i, gene in enumerate(axis.identities):
                if measure != "protein" and gene.ensembl_gene_id is None:
                    codes[i] = 2
                if measure == "protein" and gene.hgnc_id not in protein_rows:
                    codes[i] = 1
            values.append(array)
            states.append(codes)
        return FeatureMatrix(
            axis, sha256_digest(self.plans[name].protein_aliquots), *values, *states
        )

    def boundary(self, name, stage):
        protocol = json.loads((self.output / "protocol.json").read_bytes())
        assert protocol["source_receipts_sealed_before_external_measurement_reads"] is True
        if name == "external":
            manifest = json.loads((self.output / "source-fit" / MANIFEST_NAME).read_bytes())
            assert manifest["complete"] is True and manifest["external_measurements_read"] is False
            assert (
                manifest["total_genes"] == len(self.universe.axis.identities) == len(self.fit_calls)
            )
            checks = json.loads((self.output / "source-checks.json").read_bytes())
            assert checks["all_sixteen_original_source_receipts_replayed"] is True
            assert len(self.calls) >= 144
        self.events.append((stage, name))
        if self.failure == (stage, name):
            raise ValueError("synthetic admission failure")

    def read_assay(self, path, *, lock, hgnc, axis, rna):
        base = super().read_assay(path, lock=lock, hgnc=hgnc, axis=axis, rna=rna)
        name = path.parent.name
        column = self.calls[-1][2]
        values = np.array(
            [
                self.data[name][gene.hgnc_id]["rna" if rna else "cnv"][column]
                for gene in axis.identities
            ]
        )
        receipt = replace(
            base.receipt,
            gene_rows=100,
            data_rows=104 if rna else 100,
            versioned_gene_rows=100,
            observed_zero_gene_rows=int(np.count_nonzero(values == 0)),
        )
        return type(base)(receipt, values, base.states)

    def parent_document(self, protocol_digest):
        external = self.make_matrix("external")
        source_coverage = {
            row.coverage.identity.symbol: asdict(row.coverage)
            for row in atlas.build_source_catalog(self.source_matrix, self.folds).genes
        }
        external_coverage = {
            row.identity.symbol: asdict(row)
            for row in atlas.project_external_coverage(
                atlas.build_source_catalog(self.source_matrix, self.folds), external
            ).genes
        }
        genes, covers = [], {}
        for name, rows in (("source", source_coverage), ("external", external_coverage)):
            covers[name] = [
                {
                    "gene": symbol,
                    **{
                        key: value
                        for key, value in rows[symbol].items()
                        if key
                        not in (
                            "identity",
                            "rna_protein_complete",
                            "cnv_protein_complete",
                            "pattern_counts_cnv_rna_protein",
                            "cnv_state_counts",
                            "rna_state_counts",
                            "protein_state_counts",
                        )
                    },
                }
                for symbol in PANEL
            ]
        for symbol in PANEL:
            gene = next(
                identity for identity in self.universe.axis.identities if identity.symbol == symbol
            )
            src, ext = self.source_matrix.gene(gene.hgnc_id), external.gene(gene.hgnc_id)
            result = _historical_result(
                symbol,
                protocol_digest,
                tuple(value.tobytes() for value in (src.cnv, src.rna, src.protein)),
                tuple(value.tobytes() for value in (ext.cnv, ext.rna, ext.protein)),
                self.folds.tobytes(),
            )
            genes.append({"gene": symbol, **asdict(result)})
        document = {
            "evaluation_id": runner.parent.EVALUATION_ID,
            "profile_id": transfer.PROFILE_ID,
            "protocol_digest": protocol_digest,
            "genes": genes,
            "source_protein": asdict(self.proteins["source"].receipt),
            "external_protein": asdict(self.proteins["external"].receipt),
            "source_coverage": covers["source"],
            "external_coverage": covers["external"],
            "accepted_genes": sum(gene["accepted"] for gene in genes),
            "abstained_genes": sum(not gene["accepted"] for gene in genes),
            "all_panel_genes_retained": True,
            "measurement_bytes_reverified": True,
            "aligned_external_validation": False,
            "clinical_validation": False,
            "default_promotion": False,
            "redistribution_status": "local_only_terms_unverified",
        }
        document["report_digest"] = sha256_digest(document)
        return document

    def run(self, output=None, *, page_size=4):
        self.output = output or self.output
        self.events.clear()
        self.calls.clear()
        self.matrices.clear()
        self.fit_calls.clear()
        self.score_calls.clear()
        payload = canonical_json_bytes(self.processing)
        self.arguments["processing_evidence_path"].write_bytes(payload)
        return runner.evaluate(
            **self.arguments,
            processing_evidence_sha256=hashlib.sha256(payload).hexdigest(),
            parent_report_path=self.parent_path,
            parent_report_lock=self.parent_lock,
            output_dir=self.output,
            page_size=page_size,
        )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    result = _Harness(tmp_path)
    monkeypatch.setattr(
        runner.admission, "load_discovery_plan", lambda **kw: result.load("source", **kw)
    )
    monkeypatch.setattr(
        runner.admission.metadata, "load_admission_plan", lambda **kw: result.load("external", **kw)
    )
    monkeypatch.setattr(runner, "read_locked_hgnc", result.read_reference)
    monkeypatch.setattr(
        runner.discovery_module,
        "admit_discovery_protein",
        lambda **kw: result.read_protein("source", **kw),
    )
    monkeypatch.setattr(
        runner.protein,
        "admit_confirmatory_protein",
        lambda **kw: result.read_protein("external", **kw),
    )
    monkeypatch.setattr(
        assays, "parse_star_counts_v36", lambda path, **kw: result.read_assay(path, rna=True, **kw)
    )
    monkeypatch.setattr(
        assays, "parse_ascat_gene_cnv", lambda path, **kw: result.read_assay(path, rna=False, **kw)
    )
    original_build = cohort.build_cohort_matrix

    def build(**kwargs):
        admitted = original_build(**kwargs)
        name = "source" if kwargs["plan"] is result.plans["source"] else "external"
        result.matrices[name] = admitted.matrix
        return admitted

    monkeypatch.setattr(runner, "build_cohort_matrix", build)
    expected = runner.parent.frozen_protocol(
        discovery=result.inputs["source"],
        confirmatory=result.inputs["external"],
        discovery_map_bindings_sha256="e" * 64,
        processing_evidence_sha256=hashlib.sha256(
            canonical_json_bytes(result.processing)
        ).hexdigest(),
    )
    monkeypatch.setattr(
        runner.admission, "SOURCE_INPUT_PROTOCOL_DIGEST", expected["protocol_digest"]
    )
    monkeypatch.setattr(runner.historical, "PARENT_PROTOCOL_DIGEST", expected["protocol_digest"])
    result.parent = result.parent_document(expected["protocol_digest"])
    payload = canonical_json_bytes(result.parent)
    result.parent_path = tmp_path / "synthetic-parent.json"
    result.parent_path.write_bytes(payload)
    result.parent_lock = SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )
    lookup = {
        result.source_matrix.cnv[index].tobytes(): gene
        for index, gene in enumerate(result.universe.axis.identities)
    }

    def fit(cnv, rna, target, folds):
        assert not any(
            name == "external" and stage in ("protein", "rna", "cnv")
            for stage, name in result.events
        )
        gene = lookup[cnv.tobytes()]
        inputs = result.source_matrix.gene(gene.hgnc_id)
        for actual, wanted in zip(
            (cnv, rna, target, folds),
            (inputs.cnv, inputs.rna, inputs.protein, result.folds),
            strict=True,
        ):
            np.testing.assert_array_equal(actual, wanted)
        result.fit_calls.append(gene.hgnc_id)
        if result.fail_fit_at == len(result.fit_calls):
            raise ValueError("synthetic unexpected valid-input failure")
        return transfer.fit_source_gene(cnv, rna, target, folds)

    def score(source, cnv, rna, target, *, request_digest):
        assert len(result.fit_calls) == len(result.universe.axis.identities)
        result.score_calls.append(request_digest)
        return transfer.evaluate_external_gene(
            source, cnv, rna, target, request_digest=request_digest
        )

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    monkeypatch.setattr(runner, "evaluate_external_gene", score)
    return result


def _json(path):
    return json.loads(path.read_bytes())


def _source_records(output):
    return [
        row
        for path in sorted((output / "source-fit/pages").glob("*.json"))
        for row in _json(path)["genes"]
    ]


def _external_records(output):
    return [
        row
        for path in sorted((output / "external-score/pages").glob("*.json"))
        for row in _json(path)["genes"]
    ]


def test_actual_synthetic_census_attempts_every_gene_seals_source_and_replays_complete_old16(
    harness,
):
    harness.run()
    report = _json(harness.output / "evaluation.json")
    assert report["all_genes_attempted"] is report["all_genes_retained"] is True
    assert report["all_original_source_receipts_and_external_results_replayed"] is True
    assert harness.fit_calls == list(harness.universe.axis.hgnc_ids)
    assert len(harness.calls) == 256
    records = _external_records(harness.output)
    old = {row["gene"]: row for row in _json(harness.parent_path)["genes"]}
    for row in records:
        symbol = row["identity"]["symbol"]
        if symbol in PANEL:
            assert {"gene": symbol, **row["result"]} == old[symbol]
        if symbol not in PANEL and row["result"] is not None:
            assert row["result"]["request_digest"] == _manual_digest(
                {
                    "census_protocol_digest": report["protocol_digest"],
                    "hgnc_id": row["identity"]["hgnc_id"],
                }
            )
    assert not any(row["identity"]["hgnc_id"] == "HGNC:19" for row in records)
    assert all(report[key] is False for key in runner._FALSE_FLAGS)
    assert _json(harness.output / "progress.json")["complete"] is True


def _assert_digest(document, field):
    assert document[field] == _manual_digest(
        {key: value for key, value in document.items() if key != field}
    )


def test_pages_manifests_catalog_and_summary_have_independent_closed_digest_chains(harness):
    harness.run(page_size=4)
    output = harness.output
    report = _json(output / "evaluation.json")
    protocol = _json(output / "protocol.json")
    _assert_digest(report, "report_digest")
    _assert_digest(protocol, "protocol_digest")
    for filename, field in (
        ("source-catalog.json", "source_document_digest"),
        ("source-checks.json", "checks_digest"),
        ("external-coverage.json", "external_document_digest"),
    ):
        document = _json(output / filename)
        _assert_digest(document, field)
        assert document["protocol_digest"] == protocol["protocol_digest"]
    source = _json(output / "source-fit" / MANIFEST_NAME)
    external = _json(output / "external-score/manifest.json")
    for directory, manifest in (("source-fit", source), ("", external)):
        _assert_digest(manifest, "manifest_digest")
        ordered = []
        for number, binding in enumerate(manifest["pages"]):
            payload = (output / directory / binding["file_name"]).read_bytes()
            assert len(payload) == binding["bytes"]
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == binding["sha256"]
            page = json.loads(payload)
            _assert_digest(page, "page_digest")
            assert page["page_digest"] == binding["page_digest"]
            assert page["page_number"] == binding["page_number"] == number
            assert len(page["genes"]) == binding["gene_count"] <= 4
            assert page["genes"][0]["identity"]["hgnc_id"] == binding["first_hgnc_id"]
            assert page["genes"][-1]["identity"]["hgnc_id"] == binding["last_hgnc_id"]
            ordered.extend(row["identity"]["hgnc_id"] for row in page["genes"])
        assert ordered == list(harness.universe.axis.hgnc_ids)
    records = _source_records(output)
    assert source["gene_record_digests"] == [_manual_digest(row) for row in records]
    assert report["source_manifest_digest"] == source["manifest_digest"]
    assert external["source_manifest_digest"] == source["manifest_digest"]
    assert report["external_manifest_digest"] == external["manifest_digest"]
    assert report["summary_sha256"] == (
        "sha256:" + hashlib.sha256((output / "summary.csv").read_bytes()).hexdigest()
    )
    with (output / "summary.csv").open(newline="", encoding="utf-8") as stream:
        summary = list(csv.DictReader(stream))
    assert [row["hgnc_id"] for row in summary] == list(harness.universe.axis.hgnc_ids)
    assert sum(row["source_accepted"] == "True" for row in summary) == source["accepted_genes"]


def test_domain_rejections_missingness_constant_features_and_capacity_failures_stay_distinct(
    harness,
):
    harness.run()
    source = {row["identity"]["hgnc_id"]: row for row in _source_records(harness.output)}
    external = {row["identity"]["hgnc_id"]: row for row in _external_records(harness.output)}
    catalog = _json(harness.output / "source-catalog.json")["source_catalog"]
    capacity = {
        row["coverage"]["identity"]["hgnc_id"]: row["count_capacity"] for row in catalog["genes"]
    }
    rejected = source["HGNC:20"]
    assert rejected["source"] is None
    assert rejected["input_domain_rejection"] == INPUT_DOMAIN_REJECTION
    assert external["HGNC:20"]["external_complete_count"] == 56
    assert external["HGNC:20"]["external_evaluator_attempted"] is False
    assert external["HGNC:20"]["result"] is None
    assert external["HGNC:23"]["source_accepted"] is True
    assert external["HGNC:23"]["external_evaluator_attempted"] is True
    assert (
        external["HGNC:23"]["external_input_domain_rejection"] == runner.EXTERNAL_DOMAIN_REJECTION
    )
    assert external["HGNC:23"]["result"] is None
    assert external["HGNC:22"]["external_complete_count"] == 46
    assert external["HGNC:22"]["external_support_sufficient"] is False
    assert external["HGNC:22"]["source_accepted"] is True
    assert external["HGNC:22"]["point_scores_available"] is False
    assert source["HGNC:17"]["source"]["complete_count"] == 52
    assert capacity["HGNC:17"]["all_five_fold_count_support_possible"] is False
    assert source["HGNC:17"]["source"]["accepted"] is False
    assert source["HGNC:24"]["source"]["complete_count"] == 72
    assert capacity["HGNC:24"]["all_five_fold_count_support_possible"] is True
    assert source["HGNC:24"]["source"]["accepted"] is False
    assert source["HGNC:18"]["source"]["complete_count"] == 0
    assert all(
        row["source"] is not None and row["source"]["complete_count"] == 0
        for row in source.values()
        if row["identity"]["symbol"] in ("CDKN2B", "MDM2")
    )
    report = _json(harness.output / "evaluation.json")
    expected = Counter()
    for row in external.values():
        for field in (
            "source_accepted",
            "external_evaluator_attempted",
            "external_support_sufficient",
            "point_scores_available",
            "conditional_intervals_available",
            "external_result_accepted",
        ):
            expected[field] += row[field]
        expected["external_input_domain_rejected"] += (
            row["external_input_domain_rejection"] is not None
        )
    assert report["external_stage_counts"] == dict(expected)
    assert sum(row["genes"] for row in report["capacity_fit_cross_table"]) == len(source)
    assert report["source_input_domain_rejected_genes"] == 1


def test_external_poisoning_cannot_change_source_receipt_pages_or_refit_sources(harness):
    first, second = harness.directory / "first", harness.directory / "second"
    harness.run(first)
    harness.data["external"]["HGNC:21"]["rna"] *= 7
    harness.run(second)
    for relative in ("source-catalog.json", "source-checks.json", "source-fit"):
        path = first / relative
        files = path.rglob("*.json") if path.is_dir() else (path,)
        for original in files:
            assert original.read_bytes() == (second / original.relative_to(first)).read_bytes()
    before = {row["identity"]["hgnc_id"]: row for row in _external_records(first)}
    after = {row["identity"]["hgnc_id"]: row for row in _external_records(second)}
    assert (
        before["HGNC:21"]["result"]["point_metrics"] != after["HGNC:21"]["result"]["point_metrics"]
    )
    assert harness.fit_calls == list(harness.universe.axis.hgnc_ids)


def test_all_completed_bytes_repeat_without_exporting_identifiers_private_arrays_or_paths(harness):
    first, second = harness.directory / "first", harness.directory / "second"
    harness.run(first)
    harness.run(second)
    tokens = {str(harness.directory)}
    for plan in harness.plans.values():
        for candidate in plan.candidates:
            tokens.update(asdict(candidate).values())
    names = {path.relative_to(first) for path in first.rglob("*") if path.is_file()}
    assert names == {path.relative_to(second) for path in second.rglob("*") if path.is_file()}
    for name in names:
        payload = (first / name).read_bytes()
        assert payload == (second / name).read_bytes()
        assert all(token not in payload.decode() for token in tokens)
        assert b'"_predictors"' not in payload and b'"patient_indices"' not in payload
    assert all(path.suffix in (".json", ".csv") for path in names)


def test_unexpected_valid_source_failure_keeps_only_completed_pages_and_never_reads_external(
    harness,
):
    harness.fail_fit_at = 3
    with pytest.raises(ValueError, match="unexpected valid-input"):
        harness.run(page_size=2)
    assert len(harness.fit_calls) == 3
    assert len(list((harness.output / "source-fit/pages").glob("*.json"))) == 1
    assert not (harness.output / "source-fit" / MANIFEST_NAME).exists()
    assert not (harness.output / "source-checks.json").exists()
    assert not (harness.output / "evaluation.json").exists()
    progress = _json(harness.output / "progress.json")
    assert progress["source_attempted"] == 2 and progress["complete"] is False
    assert progress["external_measurements_read"] is False
    assert all(name == "source" for name, *_ in harness.calls)


def test_unexpected_valid_external_failure_preserves_source_seal_but_not_complete_result(
    harness, monkeypatch
):
    def fail(*_args, **_kwargs):
        raise ValueError("synthetic valid external software failure")

    monkeypatch.setattr(runner, "evaluate_external_gene", fail)
    with pytest.raises(ValueError, match="valid external"):
        harness.run()
    assert (harness.output / "source-fit" / MANIFEST_NAME).exists()
    assert (harness.output / "source-checks.json").exists()
    assert not (harness.output / "external-score/manifest.json").exists()
    assert not (harness.output / "evaluation.json").exists()
    assert _json(harness.output / "progress.json")["complete"] is False


@pytest.mark.parametrize("page_size", [0, 65, True, 1.5, None])
def test_invalid_page_size_stops_before_any_measurements(harness, page_size):
    with pytest.raises(ValueError):
        harness.run(page_size=page_size)
    assert harness.calls == [] and harness.fit_calls == []
    assert not harness.output.exists()


def test_existing_output_is_never_overwritten(harness):
    harness.output.mkdir()
    marker = harness.output / "private-owned.txt"
    marker.write_text("unchanged")
    with pytest.raises(FileExistsError):
        harness.run()
    assert marker.read_text() == "unchanged"
    assert harness.fit_calls == [] and harness.calls == []


def test_bad_historical_bytes_are_rejected_before_metadata_or_measurements(harness):
    harness.parent_path.write_bytes(harness.parent_path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        harness.run()
    assert harness.events == [] and harness.calls == [] and harness.fit_calls == []
    assert not harness.output.exists()


def _replace_parent(harness, mutate):
    document = _json(harness.parent_path)
    mutate(document)
    document["report_digest"] = _manual_digest(
        {key: value for key, value in document.items() if key != "report_digest"}
    )
    payload = canonical_json_bytes(document)
    harness.parent_path.write_bytes(payload)
    harness.parent_lock = SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


@pytest.mark.parametrize("boundary", ["protein", "source", "interval"])
def test_hash_valid_but_changed_historical_evidence_cannot_pass_replay(harness, boundary):
    def mutate(document):
        if boundary == "protein":
            document["source_protein"]["missing_unshared_cells"] += 1
        elif boundary == "source":
            document["genes"][0]["source"]["complete_count"] -= 1
        else:
            accepted = next(row for row in document["genes"] if row["uncertainty"] is not None)
            accepted["uncertainty"]["primary_full_minus_cnv_mae"]["lower"] -= 0.001

    _replace_parent(harness, mutate)
    with pytest.raises(ValueError, match="replay"):
        harness.run()
    assert not (harness.output / "evaluation.json").exists()
    if boundary != "interval":
        assert all(name == "source" for name, *_ in harness.calls)


def test_source_page_tampering_after_seal_stops_hydration_instead_of_refitting(
    harness, monkeypatch
):
    original = runner._score_external

    def corrupt(**kwargs):
        path = min((harness.output / "source-fit/pages").glob("*.json"))
        path.write_bytes(path.read_bytes() + b" ")
        return original(**kwargs)

    monkeypatch.setattr(runner, "_score_external", corrupt)
    with pytest.raises(ValueError):
        harness.run()
    assert harness.fit_calls == list(harness.universe.axis.hgnc_ids)
    assert not (harness.output / "evaluation.json").exists()


def test_external_page_tampering_is_rejected_before_manifest_or_report(harness, monkeypatch):
    original = runner._seal_external_manifest

    def corrupt(output, manifest, matrix):
        path = min((output / "external-score/pages").glob("*.json"))
        path.write_bytes(path.read_bytes() + b" ")
        return original(output, manifest, matrix)

    monkeypatch.setattr(runner, "_seal_external_manifest", corrupt)
    with pytest.raises(ValueError, match="file size changed"):
        harness.run()
    assert not (harness.output / "external-score/manifest.json").exists()
    assert not (harness.output / "evaluation.json").exists()


def test_point_scores_are_preserved_when_interval_success_gate_fails(harness, monkeypatch):
    original = runner.evaluate_external_gene
    gene = next(row for row in harness.universe.axis.identities if row.hgnc_id == "HGNC:21")

    def score(source, *args, request_digest):
        result = original(source, *args, request_digest=request_digest)
        protocol = _json(harness.output / "protocol.json")
        if request_digest == _manual_digest(
            {"census_protocol_digest": protocol["protocol_digest"], "hgnc_id": gene.hgnc_id}
        ):
            assert result.accepted and result.point_metrics
            return replace(
                result, accepted=False, uncertainty=None, failure_reason="synthetic interval gate"
            )
        return result

    monkeypatch.setattr(runner, "evaluate_external_gene", score)
    harness.run()
    row = next(
        row for row in _external_records(harness.output) if row["identity"]["hgnc_id"] == "HGNC:21"
    )
    assert (
        row["source_accepted"]
        is row["external_support_sufficient"]
        is row["point_scores_available"]
        is True
    )
    assert row["conditional_intervals_available"] is row["external_result_accepted"] is False
    assert row["result"]["point_metrics"] and row["result"]["uncertainty"] is None


def _census_cli_arguments(directory):
    arguments = _cli_arguments(directory)
    arguments[arguments.index("--output-dir")] = "--output"
    return [
        *arguments,
        "--parent-report",
        str(directory / "synthetic-parent.json"),
        "--parent-report-bytes",
        "123",
        "--parent-report-md5",
        "b" * 32,
        "--parent-report-sha256",
        "c" * 64,
        "--page-size",
        "3",
    ]


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError, KeyError, RuntimeError])
def test_cli_errors_are_sanitized_without_private_paths(tmp_path, monkeypatch, capsys, error_type):
    monkeypatch.setattr(sys, "argv", _census_cli_arguments(tmp_path))

    def fail(**_kwargs):
        raise error_type(f"{tmp_path} synthetic-private-specimen")

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    output = capsys.readouterr()
    assert error.value.code == 2 and output.out == ""
    assert output.err == (
        "Source-fit census did not complete; retain incomplete local evidence "
        "without treating it as a finished result.\n"
    )
    assert str(tmp_path) not in output.err and "synthetic-private" not in output.err


def test_cli_preserves_exact_locks_page_size_and_aggregate_only_stdout(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", _census_cli_arguments(tmp_path))
    expected = {"source_feature_count": 23, "all_genes_attempted": True}

    def evaluate(**kwargs):
        for name, key in (("source", "discovery"), ("external", "confirmatory")):
            assert kwargs[key].protein_path == tmp_path / f"private-{name}-protein"
            assert kwargs[key].sample_map_path == tmp_path / f"private-{name}-sample-map"
            assert kwargs[key].choices_sha256 == kwargs[key].files_manifest_sha256 == "a" * 64
        assert kwargs["parent_report_path"] == tmp_path / "synthetic-parent.json"
        assert kwargs["parent_report_lock"] == SourceLock(123, "b" * 32, "c" * 64)
        assert kwargs["page_size"] == 3
        assert kwargs["output_dir"] == tmp_path / "private-output-dir"
        return expected

    monkeypatch.setattr(runner, "evaluate", evaluate)
    assert runner.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected and output.err == ""


def test_hash_valid_historical_coverage_change_stops_before_source_fitting(harness):
    _replace_parent(
        harness, lambda document: document["source_coverage"][0].update(joint_complete=1)
    )
    with pytest.raises(CensusError, match="coverage did not replay"):
        harness.run()
    assert harness.fit_calls == []
    assert all(name == "source" for name, *_ in harness.calls)


def test_protocol_rejects_a_hash_valid_change_to_inherited_admission_method(harness):
    # Keep the new hash internally valid; semantic replay must still reject it.
    harness.run()
    feature = _json(harness.output / "protocol.json")["feature_space_protocol"]
    feature["maximum_features"] -= 1
    feature["protocol_digest"] = _manual_digest(
        {key: value for key, value in feature.items() if key != "protocol_digest"}
    )
    with pytest.raises(CensusError, match="frozen admission"):
        runner.frozen_protocol(
            feature_space_protocol=feature,
            parent_report_lock=harness.parent_lock,
            parent_report_digest=harness.parent["report_digest"],
        )


def test_external_evaluator_must_return_the_identical_frozen_source_receipt(harness, monkeypatch):
    original = runner.evaluate_external_gene

    def changed(source, *args, **kwargs):
        result = original(source, *args, **kwargs)
        return replace(result, source=replace(result.source, complete_count=1))

    monkeypatch.setattr(runner, "evaluate_external_gene", changed)
    with pytest.raises(CensusError, match="changed its frozen source"):
        harness.run()
    assert not (harness.output / "evaluation.json").exists()


@pytest.mark.parametrize("count", [0, 65])
def test_external_result_pages_enforce_gene_count_before_creation(tmp_path, count):
    with pytest.raises(CensusError, match="gene bound"):
        runner._write_external_page(
            tmp_path,
            [{}] * count,
            number=0,
            protocol={"protocol_digest": "sha256:" + "a" * 64},
            source_manifest_digest="sha256:" + "b" * 64,
            feature_axis_digest="sha256:" + "c" * 64,
        )
    assert list(tmp_path.iterdir()) == []


def test_external_result_page_byte_limit_precedes_opening_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "MAX_PAGE_BYTES", 1)
    with pytest.raises(CensusError, match="byte bound"):
        runner._write_external_page(
            tmp_path,
            [{"identity": {"hgnc_id": "HGNC:1"}}],
            number=0,
            protocol={"protocol_digest": "sha256:" + "a" * 64},
            source_manifest_digest="sha256:" + "b" * 64,
            feature_axis_digest="sha256:" + "c" * 64,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field",
    [
        "source_accepted",
        "external_evaluator_attempted",
        "external_support_sufficient",
        "point_scores_available",
        "conditional_intervals_available",
        "external_result_accepted",
    ],
)
def test_stage_counters_reject_truthy_nonbooleans(field):
    record = dict.fromkeys(
        (
            "source_accepted",
            "external_evaluator_attempted",
            "external_support_sufficient",
            "point_scores_available",
            "conditional_intervals_available",
            "external_result_accepted",
        ),
        False,
    )
    record["external_input_domain_rejection"] = None
    record[field] = 1
    with pytest.raises(CensusError, match="exact booleans"):
        runner._count_external_stages([record])


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest_axis",
        "page_bytes",
        "page_identity",
        "stage_count",
        "extra_page",
        "total_bytes",
        "manifest_bytes",
    ],
)
def test_external_sealing_rejects_hash_and_semantic_tampering(harness, monkeypatch, mutation):
    harness.run()
    output = harness.output
    manifest = _json(output / "external-score/manifest.json")
    (output / "external-score/manifest.json").unlink()
    first = manifest["pages"][0]
    path = output / first["file_name"]
    if mutation == "manifest_axis":
        manifest["feature_axis_digest"] = "sha256:" + "0" * 64
    elif mutation == "page_bytes":
        payload = path.read_bytes()
        # A same-length edit defeats a size-only check.
        path.write_bytes(payload.replace(b'"accepted":true', b'"accepted":fals', 1))
    elif mutation == "page_identity":
        page = _json(path)
        page["genes"][0]["identity"]["entrez_id"] = "999999"
        page["page_digest"] = _manual_digest(
            {key: value for key, value in page.items() if key != "page_digest"}
        )
        payload = canonical_json_bytes(page)
        path.write_bytes(payload)
        first.update(
            bytes=len(payload),
            sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            page_digest=page["page_digest"],
        )
    elif mutation == "stage_count":
        manifest["stage_counts"]["point_scores_available"] += 1
    elif mutation == "extra_page":
        (output / "external-score/pages/99999.json").write_text("{}")
    elif mutation == "total_bytes":
        monkeypatch.setattr(runner, "MAX_EXTERNAL_BYTES", 1)
    elif mutation == "manifest_bytes":
        monkeypatch.setattr(runner, "MAX_MANIFEST_BYTES", 1)
    manifest["manifest_digest"] = _manual_digest(
        {key: value for key, value in manifest.items() if key != "manifest_digest"}
    )
    with pytest.raises(CensusError):
        runner._seal_external_manifest(output, manifest, harness.matrices["external"])
    assert not (output / "external-score/manifest.json").exists()


@pytest.mark.parametrize("limit", ["MAX_EXTERNAL_BYTES", "MAX_MANIFEST_BYTES"])
def test_late_external_byte_limits_leave_an_incomplete_run(harness, monkeypatch, limit):
    monkeypatch.setattr(runner, limit, 1)
    with pytest.raises(CensusError, match="byte bound"):
        harness.run()
    assert (harness.output / "source-fit" / MANIFEST_NAME).exists()
    assert not (harness.output / "evaluation.json").exists()
    assert _json(harness.output / "progress.json")["complete"] is False


def test_external_page_preflights_cumulative_bytes_before_opening_next_page(tmp_path, monkeypatch):
    (tmp_path / "external-score/pages").mkdir(parents=True)
    kwargs = {
        "protocol": {"protocol_digest": "sha256:" + "a" * 64},
        "source_manifest_digest": "sha256:" + "b" * 64,
        "feature_axis_digest": "sha256:" + "c" * 64,
    }
    records = [{"identity": {"hgnc_id": "HGNC:1"}}]
    first = runner._write_external_page(tmp_path, records, number=0, **kwargs)
    monkeypatch.setattr(runner, "MAX_EXTERNAL_BYTES", 2 * first["bytes"] - 1)
    with pytest.raises(CensusError, match="byte bound"):
        runner._write_external_page(
            tmp_path, records, number=1, bytes_already_written=first["bytes"], **kwargs
        )
    assert not (tmp_path / "external-score/pages/00001.json").exists()
    monkeypatch.setattr(runner, "MAX_EXTERNAL_BYTES", 2 * first["bytes"])
    second = runner._write_external_page(
        tmp_path, records, number=1, bytes_already_written=first["bytes"], **kwargs
    )
    assert first["bytes"] + second["bytes"] == runner.MAX_EXTERNAL_BYTES


def test_external_phase_limit_includes_manifest_and_is_inclusive(harness, monkeypatch):
    harness.run()
    output = harness.output
    path = output / "external-score/manifest.json"
    payload = path.read_bytes()
    manifest = json.loads(payload)
    path.unlink()
    total = len(payload) + sum(page["bytes"] for page in manifest["pages"])
    monkeypatch.setattr(runner, "MAX_EXTERNAL_BYTES", total - 1)
    with pytest.raises(CensusError, match="manifest exceeds its byte bound"):
        runner._seal_external_manifest(output, manifest, harness.matrices["external"])
    assert not path.exists()
    monkeypatch.setattr(runner, "MAX_EXTERNAL_BYTES", total)
    runner._seal_external_manifest(output, manifest, harness.matrices["external"])
    assert path.read_bytes() == payload


@pytest.mark.parametrize("size", [0, True, 1.5, -1, 8 * 1024 * 1024 + 1])
def test_external_snapshot_rejects_invalid_declared_size_before_opening(tmp_path, size):
    with pytest.raises(CensusError):
        runner._read_external_snapshot(tmp_path / "never-opened", size)


def test_external_snapshot_reads_only_declared_size_plus_one(tmp_path, monkeypatch):
    path = tmp_path / "page.json"
    path.write_bytes(b"synthetic")
    original = runner.os.fdopen
    lengths = []

    class Stream:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.wrapped.close()

        def fileno(self):
            return self.wrapped.fileno()

        def read(self, count):
            lengths.append(count)
            return self.wrapped.read(count)

    def opened(descriptor, *args, **kwargs):
        return Stream(original(descriptor, *args, **kwargs))

    monkeypatch.setattr(runner.os, "fdopen", opened)
    assert runner._read_external_snapshot(path, 9) == b"synthetic"
    assert lengths == [10]


@pytest.mark.parametrize(
    "mutation",
    ["opened_inode", "after_size", "after_time", "after_ctime", "path_inode", "extra_byte"],
)
def test_external_snapshot_detects_descriptor_path_and_growth_races(  # noqa: C901
    tmp_path, monkeypatch, mutation
):
    path = tmp_path / "page.json"
    path.write_bytes(b"synthetic")
    original_fstat, original_lstat = runner.os.fstat, Path.lstat
    fstats = 0
    lstats = 0

    def changed(value, field):
        return SimpleNamespace(
            **{
                name: getattr(value, name) + (1 if name == field else 0)
                for name in (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                    "st_mode",
                    "st_birthtime_ns",
                    "st_file_attributes",
                )
                if hasattr(value, name)
            }
        )

    def fstat(fd):
        nonlocal fstats
        fstats += 1
        value = original_fstat(fd)
        if mutation == "opened_inode" and fstats == 1:
            return changed(value, "st_ino")
        if mutation == "after_size" and fstats == 2:
            return changed(value, "st_size")
        if mutation == "after_time" and fstats == 2:
            return changed(value, "st_mtime_ns")
        if mutation == "after_ctime" and fstats == 2:
            return changed(value, "st_ctime_ns")
        return value

    def lstat(candidate, *args, **kwargs):
        nonlocal lstats
        value = original_lstat(candidate, *args, **kwargs)
        if candidate == path:
            lstats += 1
            if mutation == "path_inode" and lstats == 2:
                return changed(value, "st_ino")
        return value

    monkeypatch.setattr(runner.os, "fstat", fstat)
    monkeypatch.setattr(Path, "lstat", lstat)
    if mutation == "extra_byte":
        original_open = runner.os.fdopen

        class ExtraByteStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def read(self, count):
                return self.stream.read(count) + b"x"

        def open_extra(descriptor, *args, **kwargs):
            return ExtraByteStream(original_open(descriptor, *args, **kwargs))

        monkeypatch.setattr(runner.os, "fdopen", open_extra)
    with pytest.raises(CensusError, match="external page changed"):
        runner._read_external_snapshot(path, 9)


@pytest.mark.parametrize("kind", ["directory", "wrong_size"])
def test_external_snapshot_requires_declared_regular_file(tmp_path, kind):
    path = tmp_path / "page"
    if kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"short")
    with pytest.raises(CensusError, match="bounded regular file"):
        runner._read_external_snapshot(path, 9)


def test_external_snapshot_accepts_distinct_windows_path_ctime_with_shared_birthtime(
    tmp_path, monkeypatch
):
    path = tmp_path / "synthetic-page"
    path.write_bytes(b"synthetic")
    original_fstat, original_lstat = runner.os.fstat, Path.lstat

    def metadata(value, *, path_metadata):
        fields = {
            name: getattr(value, name)
            for name in (
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
                "st_mode",
            )
        }
        fields["st_birthtime_ns"] = 123456789
        fields["st_file_attributes"] = 0
        if path_metadata:
            fields["st_ctime_ns"] += 123
        return SimpleNamespace(**fields)

    monkeypatch.setattr(
        runner.os, "fstat", lambda fd: metadata(original_fstat(fd), path_metadata=False)
    )
    monkeypatch.setattr(
        Path, "lstat", lambda candidate: metadata(original_lstat(candidate), path_metadata=True)
    )
    assert runner._read_external_snapshot(path, 9) == b"synthetic"


def test_external_snapshot_rejects_reparse_metadata(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-page"
    path.write_bytes(b"synthetic")
    value = path.lstat()
    fields = {
        name: getattr(value, name)
        for name in (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_mode",
        )
    }
    fields["st_file_attributes"] = 1024
    monkeypatch.setattr(runner.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, raising=False)
    monkeypatch.setattr(Path, "lstat", lambda _candidate: SimpleNamespace(**fields))
    with pytest.raises(CensusError, match="non-link binding"):
        runner._read_external_snapshot(path, 9)
