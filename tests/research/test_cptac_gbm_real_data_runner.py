"""Runner lifecycle checks; synthetic fixtures never stand in for source verification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import contextmanager
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.artifact import (
    load_artifact,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    DerivationStatus,
    ReplayVerificationRequest,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.errors import (
    DiscordanceSourceLockError,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.model import (
    TranscriptProteinDiscordanceDevelopmentFit,
    fit_transcript_protein_discordance_gene,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
    _StagedSources,
)
from tools import evaluate_cptac_gbm_real_data as runner

if TYPE_CHECKING:
    from collections.abc import Iterator


EXPECTED_PANEL = (
    "CDK4",
    "CDKN2A",
    "CDKN2B",
    "EGFR",
    "IDH1",
    "MDM2",
    "MDM4",
    "NF1",
    "PDGFRA",
    "PIK3CA",
    "PIK3R1",
    "PLCG1",
    "PTEN",
    "PTPN11",
    "RB1",
    "TP53",
)


@pytest.fixture(scope="module")
def synthetic_cohort() -> PreparedCohort:
    """Only two panel genes exist; filler names enforce the production shape gate."""

    random = np.random.default_rng(7_103)
    cnv = random.normal(size=96).astype(np.float32)
    rna = (0.75 * cnv + random.normal(0.0, 0.35, 96)).astype(np.float32)
    protein = (1.15 * rna + 0.10 * cnv + random.normal(0.0, 0.20, 96)).astype(np.float32)
    return PreparedCohort(
        cnv={"EGFR": cnv, "PTEN": cnv.copy()},
        rna={"EGFR": rna, "PTEN": rna.copy()},
        protein={"EGFR": protein, "PTEN": protein.copy()},
        folds=(np.arange(96) % 5).astype(np.int8),
        common_genes=tuple(sorted(("EGFR", "PTEN", *(f"FILLER{i}" for i in range(10_428))))),
        exact_common_measurement_count=96,
        patient_group_count=96,
    )


@pytest.fixture(scope="module")
def accepted_synthetic_fit(
    synthetic_cohort: PreparedCohort,
) -> TranscriptProteinDiscordanceDevelopmentFit:
    """Cache one genuine fit, then mock only the runner's expensive fitting boundary."""

    fit = fit_transcript_protein_discordance_gene(
        synthetic_cohort.cnv["EGFR"],
        synthetic_cohort.rna["EGFR"],
        synthetic_cohort.protein["EGFR"],
        synthetic_cohort.folds,
        request_digest=runner._fit_seed_digest(
            gene_symbol="EGFR",
            source_locks=EXACT_SOURCE_LOCKS,
            profile_digest=runner.algorithm_profile().profile_digest,
        ),
    )
    assert fit is not None
    return fit


def _install_staging_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    output_dir: Path,
    cohort: PreparedCohort,
) -> tuple[Path, Path, list[str]]:
    """Stand in for an already verified snapshot; never bypass a genuine-input test."""

    source_table = tmp_path / "private-source-canary.xlsx"
    source_hgnc = tmp_path / "private-hgnc-canary.tsv"
    staged = _StagedSources(tmp_path / "private-stage.xlsx", tmp_path / "private-stage.tsv")
    events: list[str] = []

    @contextmanager
    def stage(*, table_s2: Path, hgnc: Path) -> Iterator[_StagedSources]:
        assert (table_s2, hgnc) == (source_table, source_hgnc)
        protocol = json.loads((output_dir / "protocol.json").read_text(encoding="utf-8"))
        assert protocol["panel"] == list(EXPECTED_PANEL)
        assert protocol["panel_replacement_permitted"] is False
        events.append("protocol_before_staging")
        try:
            yield staged
        finally:
            events.append("staging_closed")

    def prepare(table_s2: Path, hgnc: Path) -> PreparedCohort:
        assert (table_s2, hgnc) == (staged.table_s2, staged.hgnc)
        assert table_s2 != source_table and hgnc != source_hgnc
        events.append("read_verified_snapshot")
        return cohort

    monkeypatch.setattr(runner, "_stage_exact_sources", stage)
    monkeypatch.setattr(runner, "prepare_cohort", prepare)
    return source_table, source_hgnc, events


def _assert_aggregate_only(value: object) -> None:
    """No transient measurement columns or a patient-sized vector may be persisted."""

    if isinstance(value, dict):
        forbidden = {
            "transient_oof",
            "observed_protein",
            "full_model_residual",
            "patient_ids",
            "patient_group_ids",
            "fold_assignments",
            "fold_membership",
            "oof_predictions",
            "cnv",
            "rna",
            "protein",
        }
        assert not forbidden.intersection(value)
        for nested in value.values():
            _assert_aggregate_only(nested)
    elif isinstance(value, list):
        assert len(value) not in (96, 10_430)
        for nested in value:
            _assert_aggregate_only(nested)


def test_protocol_binds_exact_sources_and_a_fixed_nonreplaceable_sixteen_gene_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def measurements_are_forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("freezing a protocol must not stage or read cohort measurements")

    monkeypatch.setattr(runner, "_stage_exact_sources", measurements_are_forbidden)
    monkeypatch.setattr(runner, "prepare_cohort", measurements_are_forbidden)
    protocol = runner.frozen_protocol()
    assert runner.PANEL == EXPECTED_PANEL
    assert protocol["panel_replacement_permitted"] is False
    assert (
        protocol["selection"] == "literature_defined_fixed_before_this_run_not_outcome_independent"
    )
    assert protocol["source_locks"] == [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS]
    assert protocol["bootstrap_replicates"] == 128
    assert protocol["evaluation_id"] == "cptac-gbm-real-data-evaluation/2.0.0"
    assert protocol["continuation_policy"] == {
        "profile_id": "cptac-gbm-transcript-protein-continuation/1.0.0",
        "iteration_budget": 240,
        "same_legacy_comparison_bootstrap_draws": True,
        "minimum_bootstrap_successful": 103,
        "legacy_artifact_promotion_permitted": False,
    }
    root = files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
    assert protocol["continuation_source_digests"] == {
        name: "sha256:"
        + hashlib.sha256(root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in ("convergence.py", "convergence_audit.py", "continuation.py")
    }
    assert protocol["iteration_budget_audit"]["budgets"] == (30, 60, 120, 240)
    assert protocol["cohort_invariants"] == {"patient_groups": 96, "common_genes": 10_430}
    assert protocol["redistribution_status"] == "local_only_terms_unverified"
    assert all(
        str(protocol[key]).startswith("sha256:")
        for key in (
            "profile_digest",
            "tool_source_digest",
            "evaluation_source_digest",
        )
    )
    assert protocol["profile_digest"] == runner.algorithm_profile().profile_digest
    assert (
        protocol["tool_source_digest"]
        == "sha256:"
        + hashlib.sha256(Path(runner.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    )
    evaluation_source = (
        files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
        .joinpath("evaluation.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    )
    assert (
        protocol["evaluation_source_digest"]
        == "sha256:" + hashlib.sha256(evaluation_source).hexdigest()
    )
    digest = protocol.pop("protocol_digest")
    assert digest == sha256_digest(protocol)


def test_existing_output_directory_is_never_reused_or_modified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "already-present"
    output.mkdir()
    marker = output / "keep.bin"
    marker.write_bytes(b"existing-result-canary")

    def stage_must_not_run(*_args: object, **_kwargs: object) -> None:
        pytest.fail("existing output must be rejected before source staging")

    monkeypatch.setattr(runner, "_stage_exact_sources", stage_must_not_run)
    with pytest.raises(FileExistsError):
        runner.evaluate_sources(
            table_s2=tmp_path / "input.xlsx", hgnc=tmp_path / "hgnc.tsv", output_dir=output
        )
    assert list(output.iterdir()) == [marker]
    assert marker.read_bytes() == b"existing-result-canary"


def test_counterfeit_sources_cannot_produce_a_real_data_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    table = tmp_path / "not-the-locked-table.xlsx"
    hgnc = tmp_path / "not-the-locked-hgnc.tsv"
    table.write_bytes(b"source-patient-values-must-not-be-persisted")
    hgnc.write_bytes(b"not-the-source-lock")

    def prepare_must_not_run(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unverified bytes must not enter cohort preparation")

    monkeypatch.setattr(runner, "prepare_cohort", prepare_must_not_run)
    output = tmp_path / "rejected"
    with pytest.raises(DiscordanceSourceLockError, match="exact lock"):
        runner.evaluate_sources(table_s2=table, hgnc=hgnc, output_dir=output)
    assert {path.name for path in output.iterdir()} == {"protocol.json"}
    assert not (output / "evaluation.json").exists()


def test_no_accepted_fit_preserves_absent_genes_and_writes_no_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    synthetic_cohort: PreparedCohort,
) -> None:
    output = tmp_path / "no-fit"
    table, hgnc, events = _install_staging_boundary(monkeypatch, tmp_path, output, synthetic_cohort)
    fit_calls: list[str] = []

    def abstain(cnv: np.ndarray, *_args: object, request_digest: str) -> None:
        assert cnv is synthetic_cohort.cnv["EGFR"] or cnv is synthetic_cohort.cnv["PTEN"]
        fit_calls.append(request_digest)

    monkeypatch.setattr(runner, "fit_transcript_protein_discordance_gene", abstain)
    report = runner.evaluate_sources(table_s2=table, hgnc=hgnc, output_dir=output)
    assert len(fit_calls) == 2
    assert events == ["protocol_before_staging", "read_verified_snapshot", "staging_closed"]
    assert report["status_counts"] == {
        "absent_from_exact_common_gene_universe": 14,
        "abstained_legacy_fit": 2,
    }
    assert report["replay_verification"] is None
    assert report["continuation_accepted_count"] == 2
    rows = {row["gene"]: row for row in report["genes"]}
    assert set(rows) == set(EXPECTED_PANEL)
    assert rows["TP53"] == {
        "gene": "TP53",
        "conditional_direction_eligible": False,
        "status": "absent_from_exact_common_gene_universe",
        "diagnostics": None,
    }
    assert all(row["conditional_direction_eligible"] is False for row in rows.values())
    assert rows["EGFR"]["diagnostics"]["bootstrap_fit_supplied"] is False
    assert not (output / "artifact.json").exists()
    assert not (output / "request.json").exists()
    assert {path.stem[5:] for path in output.glob("gene-*.json")} == set(EXPECTED_PANEL)
    assert report["legacy_estimator_changed"] is False
    assert report["independent_validation"] is False
    assert report["redistribution_status"] == "local_only_terms_unverified"
    for path in output.glob("*.json"):
        _assert_aggregate_only(json.loads(path.read_text(encoding="utf-8")))


def test_boundary_attested_run_persists_replayable_aggregate_artifacts_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    synthetic_cohort: PreparedCohort,
    accepted_synthetic_fit: TranscriptProteinDiscordanceDevelopmentFit,
) -> None:
    output = tmp_path / "successful"
    table, hgnc, events = _install_staging_boundary(monkeypatch, tmp_path, output, synthetic_cohort)
    submitted_digests: list[str] = []

    def fitted(
        cnv: np.ndarray, *_args: object, request_digest: str
    ) -> TranscriptProteinDiscordanceDevelopmentFit | None:
        submitted_digests.append(request_digest)
        if cnv is synthetic_cohort.cnv["EGFR"]:
            assert request_digest == accepted_synthetic_fit.request_digest
            return accepted_synthetic_fit
        return None

    monkeypatch.setattr(runner, "fit_transcript_protein_discordance_gene", fitted)
    report = runner.evaluate_sources(table_s2=table, hgnc=hgnc, output_dir=output)
    assert len(submitted_digests) == 2
    assert events[-1] == "staging_closed"
    assert report["status_counts"] == {
        "accepted_legacy_fit": 1,
        "abstained_legacy_fit": 1,
        "absent_from_exact_common_gene_universe": 14,
    }
    assert report["replay_verification"]["verified"] is True
    assert report["continuation_accepted_count"] == 2
    evaluated = {row["gene"]: row for row in report["genes"]}
    assert evaluated["EGFR"]["conditional_direction_eligible"] is True
    assert evaluated["PTEN"]["conditional_direction_eligible"] is False
    for gene in ("EGFR", "PTEN"):
        continued = evaluated[gene]["continuation"]
        assert continued["profile_id"] == "cptac-gbm-transcript-protein-continuation/1.0.0"
        assert continued["budget"] == 240
        assert continued["bootstrap_requested"] == continued["bootstrap_attempted"] == 128
        assert continued["bootstrap_successful"] >= continued["bootstrap_required"] == 103
        assert continued["accepted"] is True
        assert evaluated[gene]["convergence_audit"]["promotes_legacy_artifact"] is False
    artifact, _byte_digest = load_artifact(output / "artifact.json")
    assert artifact.derivation_status is DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES
    assert artifact.attempted_gene_symbols == ("EGFR", "PTEN")
    assert tuple(gene.gene_symbol for gene in artifact.genes) == ("EGFR",)
    assert artifact.cohort.fitted_gene_count == 1
    envelope = ReplayVerificationRequest.model_validate_json(
        (output / "replay-envelope.json").read_bytes(),
        strict=True,
    )
    assert envelope.request.gene_symbols == EXPECTED_PANEL
    verification = runner.verify_transcript_protein_discordance_replay(
        envelope,
        artifact_path=output / "artifact.json",
    )
    assert verification.verified and verification.semantic_match
    saved_report = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    assert saved_report == json.loads(canonical_json_bytes(report))
    digest = saved_report.pop("report_digest")
    assert digest == sha256_digest(saved_report)
    rows = list(csv.DictReader(io.StringIO((output / "summary.csv").read_text(encoding="utf-8"))))
    assert len(rows) == 16
    assert {row["gene"] for row in rows} == set(EXPECTED_PANEL)
    assert next(row for row in rows if row["gene"] == "TP53")["full_r2"] == ""
    for path in output.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        _assert_aggregate_only(document)
        text = path.read_text(encoding="utf-8")
        assert "private-source-canary" not in text and "private-hgnc-canary" not in text
        assert "FILLER" not in text


@pytest.mark.parametrize(
    "field", ["patient_group_count", "exact_common_measurement_count", "common_genes"]
)
def test_exact_cohort_invariant_failure_prevents_fitting_and_real_data_reporting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    synthetic_cohort: PreparedCohort,
    field: str,
) -> None:
    changes = {field: synthetic_cohort.common_genes[:-1] if field == "common_genes" else 95}
    invalid = replace(synthetic_cohort, **changes)
    output = tmp_path / "invariant-failure"
    table, hgnc, events = _install_staging_boundary(monkeypatch, tmp_path, output, invalid)

    def fit_must_not_run(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the fixed cohort invariants must be checked before fitting")

    monkeypatch.setattr(runner, "fit_transcript_protein_discordance_gene", fit_must_not_run)
    with pytest.raises(ValueError, match="exact source cohort invariants"):
        runner.evaluate_sources(table_s2=table, hgnc=hgnc, output_dir=output)
    assert events[-1] == "staging_closed"
    assert {path.name for path in output.iterdir()} == {"protocol.json"}
