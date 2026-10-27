"""Exact-source orchestration gates, using explicitly synthetic boundary fixtures."""

from __future__ import annotations

import csv
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from tools.evaluate_cptac_gbm_real_data import PANEL as ORIGINAL_PANEL

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.errors import (
    DiscordanceSourceLockError,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
    _StagedSources,
)
from tools import evaluate_cptac_gbm_nested_selection as runner

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class SyntheticEngineBoundaryResult:
    accepted: bool = False
    complete_count: int = 96
    common_oof_count: int = 0
    selected_oof_count: int = 96
    bootstrap_attempted: int = 0
    bootstrap_successful: int = 0
    failure_reason: str = "synthetic engine-boundary abstention"
    point_summary: None = None
    uncertainty: None = None


def _boundary_cohort() -> PreparedCohort:
    values = np.arange(96, dtype=np.float32)
    return PreparedCohort(
        cnv={"EGFR": values},
        rna={"EGFR": values + 1},
        protein={"EGFR": values + 2},
        folds=(np.arange(96) % 5).astype(np.int8),
        common_genes=("EGFR", *(f"SYNTHETIC-FILLER-{index}" for index in range(10_429))),
        exact_common_measurement_count=96,
        patient_group_count=96,
    )


def _install_source_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cohort: PreparedCohort,
    output: Path,
) -> list[str]:
    events = []

    @contextmanager
    def staged(**_kwargs: object) -> Iterator[_StagedSources]:
        assert (output / "protocol.json").is_file()
        events.append("protocol_frozen_before_staging")
        yield _StagedSources(Path("synthetic-verified-source"), Path("synthetic-hgnc"))
        events.append("private_stage_closed")

    def prepare(table: Path, hgnc: Path) -> PreparedCohort:
        assert table.name == "synthetic-verified-source" and hgnc.name == "synthetic-hgnc"
        events.append("prepared_verified_snapshot")
        return cohort

    monkeypatch.setattr(runner, "_stage_exact_sources", staged)
    monkeypatch.setattr(runner, "prepare_cohort", prepare)
    return events


def _assert_aggregate(value: object) -> None:
    if isinstance(value, dict):
        assert not {"patient_id", "sample_headers", "predictions", "residuals"}.intersection(value)
        for nested in value.values():
            _assert_aggregate(nested)
    elif isinstance(value, list):
        assert len(value) not in (96, 128, 10_430)
        for nested in value:
            _assert_aggregate(nested)


def test_frozen_nested_protocol_pins_new_inner_policy_without_reading_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("protocol freezing must not access cohort measurements")

    monkeypatch.setattr(runner, "prepare_cohort", forbidden)
    monkeypatch.setattr(runner, "_stage_exact_sources", forbidden)
    protocol = runner.frozen_protocol()
    assert runner.PANEL == ORIGINAL_PANEL and len(runner.PANEL) == 16
    assert protocol["panel_replacement_permitted"] is False
    assert protocol["source_locks"] == [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS]
    policy = protocol["selection"]
    assert policy["inner_training_complete_minimum"] == 32
    assert policy["outer_training_complete_minimum"] == 48
    assert policy["candidate_family_tie_order"] == (
        "training_median",
        "rna_only",
        "cnv_only",
        "full",
    )
    assert policy["bootstrap_replicates"] == 128
    assert policy["bootstrap_successful_minimum"] == 103
    assert policy["bootstrap_refits_inner_selection"] is True
    assert protocol["prediction_policy_digest"] == runner.nested_selection_profile_digest()
    assert (
        protocol["tool_source_digest"]
        == "sha256:"
        + hashlib.sha256(Path(runner.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    )
    digest = protocol.pop("protocol_digest")
    assert digest == sha256_digest(protocol)


def test_nested_runner_rejects_counterfeit_sources_before_real_data_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table, hgnc = tmp_path / "fake.xlsx", tmp_path / "fake.tsv"
    table.write_bytes(b"synthetic-not-a-source-workbook")
    hgnc.write_bytes(b"synthetic-not-hgnc")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unverified bytes cannot enter numerical fitting")

    monkeypatch.setattr(runner, "prepare_cohort", forbidden)
    monkeypatch.setattr(runner, "fit_nested_selection_gene", forbidden)
    output = tmp_path / "rejected"
    with pytest.raises(DiscordanceSourceLockError):
        runner.evaluate_sources(table_s2=table, hgnc=hgnc, output_dir=output)
    assert {path.name for path in output.iterdir()} == {"protocol.json"}


def test_nested_runner_keeps_absent_and_failed_genes_without_individual_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "synthetic-boundary-only"
    cohort = _boundary_cohort()
    events = _install_source_boundary(monkeypatch, cohort=cohort, output=output)
    observed_digests = []

    def fit(*_args: object, request_digest: str) -> SyntheticEngineBoundaryResult:
        observed_digests.append(request_digest)
        return SyntheticEngineBoundaryResult()

    monkeypatch.setattr(runner, "fit_nested_selection_gene", fit)
    report = runner.evaluate_sources(
        table_s2=Path("unused"), hgnc=Path("unused"), output_dir=output
    )
    assert events == [
        "protocol_frozen_before_staging",
        "prepared_verified_snapshot",
        "private_stage_closed",
    ]
    assert len(observed_digests) == 1
    assert report["status_counts"] == {
        "absent_from_exact_common_gene_universe": 15,
        "abstained_nested_policy": 1,
    }
    assert report["legacy_estimator_changed"] is False and report["independent_validation"] is False
    assert not (output / "artifact.json").exists()
    assert {row["gene"] for row in report["genes"]} == set(ORIGINAL_PANEL)
    for path in output.glob("*.json"):
        document = json.loads(path.read_text())
        _assert_aggregate(document)
        assert "SYNTHETIC-FILLER" not in path.read_text()
    saved = json.loads((output / "evaluation.json").read_text())
    digest = saved.pop("report_digest")
    assert digest == sha256_digest(saved)
    with (output / "summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 16
    egfr = next(row for row in rows if row["gene"] == "EGFR")
    assert egfr["selected_policy_oof"] == "96" and egfr["point_selected_mae"] == ""
    assert next(row for row in rows if row["gene"] == "TP53")["complete_count"] == ""


@pytest.mark.parametrize(
    "field", ["patient_group_count", "exact_common_measurement_count", "common_genes"]
)
def test_nested_runner_requires_all_exact_cohort_invariants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    cohort = _boundary_cohort()
    changed = {field: cohort.common_genes[:-1] if field == "common_genes" else 95}
    output = tmp_path / "bad-cohort"
    _install_source_boundary(monkeypatch, cohort=replace(cohort, **changed), output=output)
    with pytest.raises(ValueError, match="exact source cohort invariants"):
        runner.evaluate_sources(table_s2=Path("unused"), hgnc=Path("unused"), output_dir=output)
    assert {path.name for path in output.iterdir()} == {"protocol.json"}


def test_nested_runner_never_modifies_existing_output_directory(tmp_path: Path) -> None:
    marker = tmp_path / "keep.json"
    marker.write_bytes(canonical_json_bytes({"keep": True}))
    with pytest.raises(FileExistsError):
        runner.evaluate_sources(table_s2=Path("unused"), hgnc=Path("unused"), output_dir=tmp_path)
    assert marker.read_bytes() == canonical_json_bytes({"keep": True})
    assert list(tmp_path.iterdir()) == [marker]
