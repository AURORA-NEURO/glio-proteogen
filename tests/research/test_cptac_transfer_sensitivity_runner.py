"""Synthetic immutable-parent and phase-boundary tests for additive sensitivity."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import asdict, replace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.source import SourceVerificationError
from glio_proteogen.research.cptac_gbm_external_admission.transfer_sensitivity import (
    FailureCount,
    MatchedSensitivityRanges,
    PairedVarianceIdentity,
    PercentileRange,
    SelectionFrequency,
    SensitivityMetricRanges,
)
from tests.research.test_cptac_provider_transfer_runner import (
    _cli_arguments,
    _external_result,
    _Harness,
    _source_fit,
)
from tools import evaluate_cptac_gbm_transfer_sensitivity as runner


def _stamp(document):
    document = {key: value for key, value in document.items() if key != "report_digest"}
    document["report_digest"] = sha256_digest(document)
    return document


def _parent_document():
    genes = []
    for index, gene in enumerate(PANEL):
        fit = _source_fit(np.ones(72) if index < 12 else np.full(72, np.nan))
        digest = sha256_digest({"protocol_digest": runner.PARENT_PROTOCOL_DIGEST, "gene": gene})
        result = _external_result(fit, np.ones(56), digest, index)
        genes.append({"gene": gene, **asdict(result)})
    return _stamp(
        {
            "evaluation_id": runner.parent.EVALUATION_ID,
            "profile_id": runner.parent.PROFILE_ID,
            "protocol_digest": runner.PARENT_PROTOCOL_DIGEST,
            "genes": genes,
            "accepted_genes": 12,
            "abstained_genes": 4,
            "all_panel_genes_retained": True,
            "measurement_bytes_reverified": True,
            "aligned_external_validation": False,
            "clinical_validation": False,
            "default_promotion": False,
            "redistribution_status": "local_only_terms_unverified",
        }
    )


def _locked_payload(tmp_path, payload):
    path = tmp_path / "private-parent.json"
    path.write_bytes(payload)
    lock = SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )
    return path, lock


def _locked_document(tmp_path, document):
    return _locked_payload(tmp_path, canonical_json_bytes(document))


def test_parent_admission_preserves_exact_locked_sixteen_gene_report(tmp_path):
    document = _parent_document()
    path, lock = _locked_document(tmp_path, document)
    admitted = runner.load_parent_report(path, lock=lock)
    assert canonical_json_bytes(admitted) == canonical_json_bytes(document) == path.read_bytes()
    assert admitted["protocol_digest"] == runner.PARENT_PROTOCOL_DIGEST
    assert tuple(row["gene"] for row in admitted["genes"]) == PANEL
    assert admitted["accepted_genes"] == 12
    assert admitted["abstained_genes"] == 4


@pytest.mark.parametrize("field", ["bytes", "md5", "sha256"])
def test_size_and_both_hashes_are_checked_before_any_parent_json_parsing(
    tmp_path, monkeypatch, field
):
    path, lock = _locked_document(tmp_path, _parent_document())
    bad = len(path.read_bytes()) + 1 if field == "bytes" else "0" * (32 if field == "md5" else 64)

    def forbidden(_pairs):
        pytest.fail("parent JSON parser ran before exact byte verification")

    monkeypatch.setattr(runner, "_unique_object", forbidden)
    with pytest.raises(SourceVerificationError):
        runner.load_parent_report(path, lock=replace(lock, **{field: bad}))


def test_parent_larger_than_two_mib_is_rejected_before_open_or_parse(tmp_path, monkeypatch):
    lock = SourceLock(runner.PARENT_REPORT_MAX_BYTES + 1, "0" * 32, "0" * 64)

    def forbidden(_pairs):
        pytest.fail("oversized parent report reached JSON parsing")

    monkeypatch.setattr(runner, "_unique_object", forbidden)
    with pytest.raises(SourceVerificationError, match="read bound"):
        runner.load_parent_report(tmp_path / "not-opened", lock=lock)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"same":1,"same":2}',
        b'{"nested":{"same":1,"same":2}}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"value":1e999}',
        b'{"value":-1e999}',
        b"[1,2,3]",
        b'{"malformed":"synthetic-private-specimen"',
        b"\xff\xfe{not-utf8}",
    ],
)
def test_locked_invalid_json_is_rejected_without_tainted_error_messages(tmp_path, payload):
    path, lock = _locked_payload(tmp_path, payload)
    with pytest.raises(runner.ParentReportError) as error:
        runner.load_parent_report(path, lock=lock)
    assert "synthetic-private-specimen" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_parent_must_retain_canonical_bytes_even_when_its_semantic_digest_matches(tmp_path):
    document = _parent_document()
    path, lock = _locked_payload(tmp_path, json.dumps(document, indent=2).encode())
    with pytest.raises(runner.ParentReportError, match="canonical digest or bytes"):
        runner.load_parent_report(path, lock=lock)


def test_parent_canonical_digest_cannot_be_rebound_by_only_changing_the_source_lock(tmp_path):
    document = _parent_document()
    document["genes"][0]["point_metrics"][0]["mae"] += 1
    path, lock = _locked_document(tmp_path, document)
    with pytest.raises(runner.ParentReportError, match="canonical digest or bytes"):
        runner.load_parent_report(path, lock=lock)


@pytest.mark.parametrize("digest", [None, 1, "a" * 64, "sha256:" + "A" * 64])
def test_parent_declared_digest_requires_exact_lowercase_namespaced_sha256(tmp_path, digest):
    document = _parent_document()
    document["report_digest"] = digest
    path, lock = _locked_document(tmp_path, document)
    with pytest.raises(runner.ParentReportError, match="lacks a canonical digest"):
        runner.load_parent_report(path, lock=lock)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_digest", "sha256:" + "f" * 64),
        ("profile_id", "another-profile/1.0.0"),
        ("evaluation_id", "another-evaluation/1.0.0"),
        ("all_panel_genes_retained", False),
        ("measurement_bytes_reverified", False),
        ("aligned_external_validation", True),
        ("clinical_validation", True),
        ("default_promotion", True),
        ("redistribution_status", "publicly-redistributable"),
    ],
)
def test_rehashed_parent_cannot_change_the_frozen_historical_scope(tmp_path, field, value):
    document = _parent_document()
    document[field] = value
    path, lock = _locked_document(tmp_path, _stamp(document))
    with pytest.raises(runner.ParentReportError, match="frozen research scope"):
        runner.load_parent_report(path, lock=lock)


@pytest.mark.parametrize(
    "mutation", ["drop", "reverse", "duplicate", "unknown_field", "missing_field"]
)
def test_parent_cannot_drop_reorder_duplicate_or_retype_historical_gene_rows(tmp_path, mutation):
    document = _parent_document()
    genes = document["genes"]
    if mutation == "drop":
        genes.pop()
    elif mutation == "reverse":
        genes.reverse()
    elif mutation == "duplicate":
        genes[-1]["gene"] = genes[0]["gene"]
    elif mutation == "unknown_field":
        genes[0]["unchecked_note"] = "unbound"
    else:
        genes[0].pop("source")
    path, lock = _locked_document(tmp_path, _stamp(document))
    with pytest.raises(runner.ParentReportError, match="frozen research scope"):
        runner.load_parent_report(path, lock=lock)


@pytest.mark.parametrize(
    ("field", "value"),
    [("accepted_genes", True), ("accepted_genes", 13), ("abstained_genes", 3)],
)
def test_parent_panel_counts_are_strict_and_conserve_all_sixteen_genes(tmp_path, field, value):
    document = _parent_document()
    document[field] = value
    path, lock = _locked_document(tmp_path, _stamp(document))
    with pytest.raises(runner.ParentReportError, match="outcome counts"):
        runner.load_parent_report(path, lock=lock)


def _coverage(bundle):
    values = bundle.matrices
    count = values["cnv"].shape[1]
    return tuple(
        {
            "gene": gene,
            "candidate_specimens": count,
            "protein_feature_present": True,
            **{
                "observed_" + family: int(np.isfinite(matrix[index]).sum())
                for family, matrix in values.items()
            },
            "joint_complete": int(
                np.logical_and.reduce(
                    [np.isfinite(matrix[index]) for matrix in values.values()]
                ).sum()
            ),
            **{
                "zero_" + family: int(np.count_nonzero(matrix[index] == 0))
                for family, matrix in values.items()
            },
        }
        for index, gene in enumerate(PANEL)
    )


def _ranges(previous):
    def interval(value):
        return PercentileRange(value, value, value, 0.9, 128)

    metrics = tuple(
        SensitivityMetricRanges(item.candidate, interval(item.mae), interval(item.rmse), None)
        for item in previous.point_metrics
    )
    primary = interval(previous.primary_full_minus_cnv_mae)
    secondary = interval(previous.secondary_selected_minus_full_mae)
    zero = interval(0.0)
    # A signed covariance term must survive serialization without truncation.
    variance = PairedVarianceIdentity(
        joint_variance=0.01,
        frozen_reference_variance=0.02,
        source_perturbation_variance=0.01,
        twice_covariance=-0.02,
        reconstruction_error=0.0,
        replicates=128,
        reconstructed_variance=0.01,
    )
    return MatchedSensitivityRanges(
        metrics,
        metrics,
        primary,
        primary,
        zero,
        secondary,
        secondary,
        zero,
        variance,
        variance,
        128,
    )


def _sensitivity(previous, digest, index):
    attempted = 128 if previous.accepted else 0
    successful = (102 if index == 0 else 128) if previous.accepted else 0
    accepted = successful >= 103
    return runner.TwoCohortSensitivityResult(
        profile_id=runner.PROFILE_ID,
        request_digest=digest,
        parent_result=previous,
        accepted=accepted,
        draws_attempted=attempted,
        draws_successful=successful,
        draws_required=103,
        uncertainty=_ranges(previous) if accepted else None,
        failure_reason=None if accepted else "synthetic sensitivity abstention",
        source_sampling_diagnostics=None,
        selection_frequencies=tuple(
            SelectionFrequency(
                family, attempted if family == "full" else 0, successful if family == "full" else 0
            )
            for family in runner.parent.CANDIDATE_ORDER
        ),
        accepted_source_refits=attempted,
        failure_counts=(FailureCount("comparison", "synthetic paired failure", 26),)
        if attempted and not accepted
        else (),
        frozen_reference_available_draws=attempted,
        reference_available_but_unmatched_draws=attempted - successful,
    )


class _SensitivityHarness(_Harness):
    def prepare_parent(self, monkeypatch):
        payload = canonical_json_bytes(self.processing)
        self.arguments["processing_evidence_path"].write_bytes(payload)
        self.evidence_digest = hashlib.sha256(payload).hexdigest()
        self.parent_protocol = runner.parent.frozen_protocol(
            discovery=self.inputs["source"],
            confirmatory=self.inputs["external"],
            discovery_map_bindings_sha256=self.arguments["discovery_map_bindings_sha256"],
            processing_evidence_sha256=self.evidence_digest,
        )
        monkeypatch.setattr(
            runner, "PARENT_PROTOCOL_DIGEST", self.parent_protocol["protocol_digest"]
        )
        fits = tuple(_source_fit(row) for row in self.bundles["source"].matrices["protein"])
        results = tuple(
            _external_result(
                fit,
                self.bundles["external"].matrices["protein"][index],
                sha256_digest(
                    {"protocol_digest": runner.PARENT_PROTOCOL_DIGEST, "gene": PANEL[index]}
                ),
                index,
            )
            for index, fit in enumerate(fits)
        )
        self.document = _stamp(
            {
                **_parent_document(),
                "genes": [
                    {"gene": gene, **asdict(result)}
                    for gene, result in zip(PANEL, results, strict=True)
                ],
                "accepted_genes": sum(result.accepted for result in results),
                "abstained_genes": sum(not result.accepted for result in results),
                "source_fit_receipts_digest": sha256_digest(
                    {
                        "protocol_digest": runner.PARENT_PROTOCOL_DIGEST,
                        "source_fits": tuple(
                            {"gene": gene, **asdict(fit.receipt)}
                            for gene, fit in zip(PANEL, fits, strict=True)
                        ),
                        "external_measurements_read": False,
                    }
                ),
                "source_metadata": asdict(self.plans["source"].receipt),
                "external_metadata": asdict(self.plans["external"].receipt),
                "metadata_separation": asdict(
                    runner.assert_distinct_cohort_plans(
                        self.plans["source"], self.plans["external"]
                    )
                ),
                "source_coverage": _coverage(self.bundles["source"]),
                "external_coverage": _coverage(self.bundles["external"]),
                "source_protein": asdict(self.bundles["source"].protein.receipt),
                "external_protein": asdict(self.bundles["external"].protein.receipt),
            }
        )
        self.rebind_parent()
        self.panel_calls = []

    def rebind_parent(self):
        self.document = _stamp(self.document)
        self.parent_path, self.parent_lock = _locked_document(self.directory, self.document)

    def before_measurement(self, cohort, stage):
        protocol = json.loads((self.output / "protocol.json").read_text())
        assert protocol["parent_protocol"]["protocol_digest"] == runner.PARENT_PROTOCOL_DIGEST
        assert protocol["original_point_source_fitting_before_external_measurement_reads"] is True
        if cohort == "external":
            assert len(self.fits) == 16
            receipts = json.loads((self.output / "source-fit-receipts.json").read_text())
            assert receipts["parent_source_fits_replayed"] is True
            assert receipts["external_measurements_read"] is False
        self.events.append((stage, cohort))
        if self.failure == (cohort, stage):
            raise ValueError

    def score(self, fit, cnv, rna, protein, *, request_digest):
        index = len(self.scores)
        assert len(self.calls) == 256 and len(self.fits) == 16
        assert request_digest == sha256_digest(
            {"protocol_digest": runner.PARENT_PROTOCOL_DIGEST, "gene": PANEL[index]}
        )
        for family, array in (("cnv", cnv), ("rna", rna), ("protein", protein)):
            np.testing.assert_array_equal(array, self.bundles["external"].matrices[family][index])
        self.scores.append(request_digest)
        return _external_result(fit, protein, request_digest, index)

    def panel(self, **kwargs):
        assert len(self.scores) == len(self.fits) == 16
        assert len(self.calls) == 256
        assert kwargs["source_fits"] == tuple(self.fits)
        protocol = json.loads((self.output / "protocol.json").read_text())
        assert kwargs["request_digest"] == protocol["protocol_digest"]
        for name, cohort in (("source_inputs", "source"), ("external_inputs", "external")):
            for index, inputs in enumerate(kwargs[name]):
                for family in ("cnv", "rna", "protein"):
                    array = getattr(inputs, family)
                    np.testing.assert_array_equal(
                        array, self.bundles[cohort].matrices[family][index]
                    )
                    assert not array.flags.writeable
        self.panel_calls.append(kwargs)
        results = tuple(
            _sensitivity(previous, kwargs["request_digest"], index)
            for index, previous in enumerate(kwargs["parent_results"])
        )
        return runner.PanelSensitivityResult(
            runner.PROFILE_ID,
            kwargs["request_digest"],
            results,
            sum(previous.accepted for previous in kwargs["parent_results"]),
            102,
        )

    def run(self, output=None):
        self.output = output or self.directory / "result"
        self.calls.clear()
        self.events.clear()
        self.fits.clear()
        self.scores.clear()
        self.panel_calls.clear()
        self._reference_calls = 0
        return runner.evaluate(
            discovery=self.inputs["source"],
            confirmatory=self.inputs["external"],
            **self.arguments,
            processing_evidence_sha256=self.evidence_digest,
            parent_report_path=self.parent_path,
            parent_report_lock=self.parent_lock,
            output_dir=self.output,
        )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    result = _SensitivityHarness(tmp_path)
    result.prepare_parent(monkeypatch)
    monkeypatch.setattr(runner, "load_discovery_plan", lambda **kw: result.load("source", **kw))
    monkeypatch.setattr(
        runner.metadata, "load_admission_plan", lambda **kw: result.load("external", **kw)
    )
    monkeypatch.setattr(runner.parent, "read_locked_hgnc", result.read_reference)
    monkeypatch.setattr(
        runner.parent.source_protein,
        "admit_discovery_protein",
        lambda **kw: result.read_protein("source", **kw),
    )
    monkeypatch.setattr(
        runner.parent.test_protein,
        "admit_confirmatory_protein",
        lambda **kw: result.read_protein("external", **kw),
    )
    monkeypatch.setattr(
        runner.parent,
        "parse_star_counts_v36",
        lambda path, **kw: result.read_assay(path, family="rna", **kw),
    )
    monkeypatch.setattr(
        runner.parent,
        "parse_ascat_gene_cnv",
        lambda path, **kw: result.read_assay(path, family="cnv", **kw),
    )
    monkeypatch.setattr(runner, "fit_source_gene", result.fit)
    monkeypatch.setattr(runner, "evaluate_external_gene", result.score)
    monkeypatch.setattr(runner, "evaluate_panel_sensitivity", result.panel)
    return result


def test_all_parent_replays_finish_before_one_shared_panel_sensitivity_call(harness, capsys):
    summary = harness.run()
    assert len(harness.panel_calls) == 1
    assert [(cohort, family, index) for cohort, family, index, _ in harness.calls] == [
        (cohort, family, index)
        for cohort, count in (("source", 72), ("external", 56))
        for index in range(count)
        for family in ("rna", "cnv")
    ]
    assert summary["verified_assay_files"] == 256
    assert summary["parent_accepted_genes"] == 14
    assert summary["parent_abstained_genes"] == 2
    assert summary["accepted_genes"] == 13
    assert summary["abstained_genes"] == 3
    assert summary["post_hoc"] is True
    assert summary["aligned_external_validation"] is False
    assert capsys.readouterr().out == ""


def test_repeated_sensitivity_runner_outputs_are_canonical_and_identical(harness):
    first = harness.run(harness.directory / "first")
    second = harness.run(harness.directory / "second")
    assert first == second
    names = {"protocol.json", "source-fit-receipts.json", "evaluation.json", "summary.csv"}
    assert {path.name for path in harness.output.iterdir()} == names
    for name in names:
        assert (harness.directory / "first" / name).read_bytes() == (
            harness.directory / "second" / name
        ).read_bytes()
    report = json.loads((harness.output / "evaluation.json").read_text())
    digest = report.pop("report_digest")
    assert sha256_digest(report) == digest == second["report_digest"]
    protocol = json.loads((harness.output / "protocol.json").read_text())
    digest = protocol.pop("protocol_digest")
    assert sha256_digest(protocol) == digest == second["protocol_digest"]
    assert protocol["bootstrap_refit_inputs_source_only"] is True
    assert protocol["bootstrap_refits_after_external_loading"] is True
    assert protocol["support_counts_represent_expanded_observation_mass"] is True
    assert protocol["nominal_interval_coverage_established"] is False


def test_new_failure_keeps_parent_point_and_original_abstentions_visible_in_csv(harness):
    harness.run()
    with (harness.output / "summary.csv").open(newline="") as stream:
        rows = {row["gene"]: row for row in csv.DictReader(stream)}
    assert tuple(rows) == PANEL
    first = rows[PANEL[0]]
    assert first["parent_accepted"] == "True"
    assert first["sensitivity_accepted"] == "False"
    assert first["parent_primary_full_minus_cnv_mae"] == "0.0"
    assert first["draws_successful"] == "102"
    assert first["primary_joint_lower_p05"] == ""
    last = rows[PANEL[-1]]
    assert last["parent_accepted"] == last["sensitivity_accepted"] == "False"
    assert last["draws_attempted"] == "0"
    assert last["parent_primary_full_minus_cnv_mae"] == ""
    assert rows[PANEL[1]]["primary_twice_covariance"] == "-0.02"
    assert rows[PANEL[1]]["primary_reconstructed_variance"] == "0.01"
    assert rows[PANEL[1]]["secondary_reconstructed_variance"] == "0.01"
    for row in rows.values():
        attempted = int(row["draws_attempted"])
        successful = int(row["draws_successful"])
        available = int(row["frozen_reference_available_draws"])
        unmatched = int(row["reference_available_but_unmatched_draws"])
        source_refits = int(row["accepted_source_refits"])
        unavailable = int(row["unavailable_source_selections"])
        assert 0 <= successful <= available <= attempted <= 128
        assert 0 <= unmatched <= available
        assert successful + unmatched == available
        assert source_refits + unavailable == attempted
    report = json.loads((harness.output / "evaluation.json").read_text())
    assert report["panel_sensitivity"]["jointly_successful_draws_all_eligible"] == 102
    assert report["all_parent_gene_outcomes_preserved"] is True


def test_csv_retains_nonzero_unavailable_source_and_unmatched_reference_counts(tmp_path):
    previous = _external_result(_source_fit(np.ones(72)), np.ones(56), "sha256:" + "a" * 64, 0)
    result = replace(
        _sensitivity(previous, "sha256:" + "b" * 64, 0),
        accepted_source_refits=100,
        unavailable_source_selections=28,
        draws_successful=90,
        frozen_reference_available_draws=128,
        reference_available_but_unmatched_draws=38,
        failure_counts=(
            FailureCount("source_refit", "synthetic source failure", 28),
            FailureCount("external_comparison", "synthetic comparison failure", 10),
        ),
    )
    path = tmp_path / "summary.csv"
    runner._write_summary(path, ((PANEL[0], result),))
    with path.open(newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["accepted_source_refits"] == "100"
    assert row["unavailable_source_selections"] == "28"
    assert row["frozen_reference_available_draws"] == "128"
    assert row["reference_available_but_unmatched_draws"] == "38"
    assert int(row["draws_successful"]) + int(row["reference_available_but_unmatched_draws"]) == 128
    assert int(row["accepted_source_refits"]) + int(row["unavailable_source_selections"]) == 128


@pytest.mark.parametrize("stage", ["source_fit", "source_digest", "point", "coverage"])
def test_a_rehashed_changed_parent_cannot_reach_new_sensitivity(harness, stage):
    if stage == "source_fit":
        harness.document["genes"][0]["source"]["common_oof_count"] -= 1
    elif stage == "source_digest":
        harness.document["source_fit_receipts_digest"] = "sha256:" + "f" * 64
    elif stage == "point":
        harness.document["genes"][0]["point_metrics"][0]["mae"] += 1
    else:
        harness.document["external_coverage"][0]["observed_protein"] -= 1
    harness.rebind_parent()
    with pytest.raises(runner.ParentReportError, match=r"do(es)? not replay"):
        harness.run()
    assert harness.panel_calls == []
    assert not (harness.output / "evaluation.json").exists()
    assert not (harness.output / "summary.csv").exists()
    if stage in ("source_fit", "source_digest"):
        assert all(cohort == "source" for cohort, *_ in harness.calls)
        assert {path.name for path in harness.output.iterdir()} == {"protocol.json"}
    if stage == "point":
        assert len(harness.scores) == 16


def test_mismatched_original_protocol_is_rejected_before_measurement_reads(harness, monkeypatch):
    changed = dict(harness.parent_protocol, values_imputed=True)
    monkeypatch.setattr(runner.parent, "frozen_protocol", lambda **kw: changed)
    with pytest.raises(runner.ParentReportError, match="exact frozen parent"):
        harness.run()
    assert not harness.output.exists()
    assert harness.calls == harness.fits == []


def test_existing_output_is_not_overwritten(harness):
    harness.output.mkdir()
    keep = harness.output / "caller-owned.txt"
    keep.write_bytes(b"caller-owned")
    with pytest.raises(FileExistsError):
        harness.run()
    assert list(harness.output.iterdir()) == [keep]
    assert keep.read_bytes() == b"caller-owned"
    assert harness.calls == []


def test_report_and_protocol_export_only_aggregates_without_private_bindings(harness):
    harness.run()
    text = "\n".join(path.read_text() for path in harness.output.iterdir())
    for plan in harness.plans.values():
        for candidate in plan.candidates:
            assert all(value not in text for value in asdict(candidate).values())
    assert str(harness.directory) not in text
    assert "10000.001" not in text
    assert "_predictors" not in text
    for path in harness.output.glob("*.json"):
        runner.parent._aggregate_only(json.loads(path.read_text()))


def test_bad_parent_lock_stops_before_metadata_protocol_and_measurement_admission(harness):
    harness.parent_lock = replace(harness.parent_lock, sha256="0" * 64)
    with pytest.raises(SourceVerificationError):
        harness.run()
    assert harness.events == harness.calls == harness.fits == harness.panel_calls == []
    assert not harness.output.exists()


def test_changed_parent_metadata_stops_before_measurements_and_output(harness):
    harness.document["source_metadata"]["manifest_verified_bytes"] += 1
    harness.rebind_parent()
    with pytest.raises(runner.ParentReportError, match="parent metadata"):
        harness.run()
    assert not harness.output.exists()
    assert harness.calls == harness.fits == []


@pytest.mark.parametrize(
    "failure",
    [("source", "protein"), ("source", "cnv", 7), ("external", "protein"), ("external", "rna", 7)],
)
def test_reader_failure_cannot_produce_partial_sensitivity_report(harness, failure):
    harness.failure = failure
    with pytest.raises(ValueError):
        harness.run()
    names = {"protocol.json"}
    if failure[0] == "external":
        names.add("source-fit-receipts.json")
        assert len(harness.fits) == 16
    assert {path.name for path in harness.output.iterdir()} == names
    assert harness.scores == harness.panel_calls == []


def _protocol_kwargs(harness):
    return {
        "parent_protocol": harness.parent_protocol,
        "parent_report_lock": harness.parent_lock,
        "parent_report_digest": harness.document["report_digest"],
        "source_fold_assignment_digest": "sha256:" + "a" * 64,
    }


@pytest.mark.parametrize("binding", ["parent_lock", "parent_digest", "fold_assignment"])
def test_each_new_request_binding_changes_the_shared_schedule_digest(harness, binding):
    arguments = _protocol_kwargs(harness)
    original = runner.frozen_protocol(**arguments)
    if binding == "parent_lock":
        arguments["parent_report_lock"] = replace(harness.parent_lock, md5="0" * 32)
    elif binding == "parent_digest":
        arguments["parent_report_digest"] = "sha256:" + "f" * 64
    else:
        arguments["source_fold_assignment_digest"] = "sha256:" + "f" * 64
    changed = runner.frozen_protocol(**arguments)
    assert changed["protocol_digest"] != original["protocol_digest"]
    assert changed["parent_protocol"] == original["parent_protocol"]


def test_resampling_code_change_binds_a_different_whole_panel_request(harness, monkeypatch):
    arguments = _protocol_kwargs(harness)
    original = runner.frozen_protocol(**arguments)
    resources = runner.files

    def altered_resources(package):
        root = resources(package)

        class Altered:
            def joinpath(self, name):
                source = root.joinpath(name)
                if name != "resampling.py":
                    return source
                return type(
                    "SyntheticSource",
                    (),
                    {"read_bytes": lambda _self: source.read_bytes() + b"\n# draw policy changed"},
                )()

        return Altered()

    monkeypatch.setattr(runner, "files", altered_resources)
    changed = runner.frozen_protocol(**arguments)
    assert changed["protocol_digest"] != original["protocol_digest"]
    assert changed["method_sources"]["resampling.py"] != original["method_sources"]["resampling.py"]
    assert changed["parent_protocol_digest"] == original["parent_protocol_digest"]


@pytest.mark.parametrize(
    "mutation", ["historical_outcome", "false_coverage", "attempts", "panel_joint", "gene_order"]
)
def test_invalid_engine_result_cannot_publish_changed_parent_or_inference_claims(
    harness, monkeypatch, mutation
):
    def altered(**kwargs):
        panel = harness.panel(**kwargs)
        first = panel.gene_results[0]
        if mutation == "panel_joint":
            return replace(panel, jointly_successful_draws_all_eligible=129)
        if mutation == "gene_order":
            return replace(panel, gene_results=tuple(reversed(panel.gene_results)))
        if mutation == "historical_outcome":
            first = replace(first, parent_result=replace(first.parent_result, accepted=False))
        elif mutation == "false_coverage":
            first = replace(first, calibrated_coverage_established=True)
        else:
            first = replace(first, draws_attempted=127)
        return replace(panel, gene_results=(first, *panel.gene_results[1:]))

    monkeypatch.setattr(runner, "evaluate_panel_sensitivity", altered)
    with pytest.raises(ValueError, match=r"frozen (parent outcome|evaluation)"):
        harness.run()
    assert not (harness.output / "evaluation.json").exists()
    assert not (harness.output / "summary.csv").exists()


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError])
def test_cli_error_is_generic_and_never_echoes_private_parent_or_source_paths(
    tmp_path, monkeypatch, capsys, error_type
):
    args = [
        *_cli_arguments(tmp_path),
        "--parent-report",
        str(tmp_path / "private-parent"),
        "--parent-report-bytes",
        "1",
        "--parent-report-md5",
        "1" * 32,
        "--parent-report-sha256",
        "2" * 64,
    ]
    monkeypatch.setattr(sys, "argv", args)
    message = str(tmp_path / "private-tainted-source") + " synthetic-private-specimen"

    def fail(**kw):
        assert kw["parent_report_lock"] == SourceLock(1, "1" * 32, "2" * 64)
        raise error_type(message)

    monkeypatch.setattr(runner, "evaluate", fail)
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Transfer sensitivity failed; private inputs or immutable parent contracts "
        "were not satisfied.\n"
    )
    assert str(tmp_path) not in output.err


def test_cli_passes_explicit_parent_lock_and_prints_only_aggregate_summary(
    tmp_path, monkeypatch, capsys
):
    arguments = [
        *_cli_arguments(tmp_path),
        "--parent-report",
        str(tmp_path / "private-parent"),
        "--parent-report-bytes",
        "1",
        "--parent-report-md5",
        "1" * 32,
        "--parent-report-sha256",
        "2" * 64,
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    expected = {"post_hoc": True, "accepted_genes": 13, "parent_accepted_genes": 14}

    def evaluate(**kwargs):
        assert kwargs["parent_report_path"] == tmp_path / "private-parent"
        assert kwargs["parent_report_lock"] == SourceLock(1, "1" * 32, "2" * 64)
        assert kwargs["discovery"].choices_path == tmp_path / "private-source-choices"
        assert kwargs["confirmatory"].choices_path == tmp_path / "private-external-choices"
        return expected

    monkeypatch.setattr(runner, "evaluate", evaluate)
    assert runner.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == expected
    assert captured.err == ""
