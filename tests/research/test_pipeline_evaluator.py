"""Evaluator and benchmark checks for the research pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from evals.research_proteomics.run import run_benchmark, run_evaluator


def test_research_evaluator_scripts_bootstrap_when_run_by_path() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative_path, expected_key in (
        ("evals/research_proteomics/run.py", "evaluation"),
        ("evals/research_proteomics/cohort.py", "passed"),
    ):
        completed = subprocess.run(  # noqa: S603 - fixed repository-local entrypoint
            [sys.executable, relative_path],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = json.loads(completed.stdout)
        if expected_key == "evaluation":
            assert payload[expected_key]["passed"] is True
        else:
            assert payload[expected_key] is True


def test_locked_research_pipeline_evaluator() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert cast("int", report["declared"]) == cast("int", report["executed"]) == 8
    assert len(cast("str", report["fixture_sha256"])) == 64
    outcomes = cast("list[dict[str, object]]", report["outcomes"])
    collision = next(item for item in outcomes if item["scenario_id"] == "target_decoy_collision")
    collision_summary = cast("dict[str, object]", collision["fdr_summary"])
    assert collision_summary["collision_winners"] == 1
    assert collision["accepted_psms"] == 0
    target = next(item for item in outcomes if item["scenario_id"] == "target_supported")
    quant = cast("list[dict[str, object]]", target["protein_group_quantifications"])
    assert quant[0]["primary_intensity"] == 20.0
    receipt = cast("dict[str, object]", target["quantification_receipt"])
    assert receipt["measurement_unit"] == "median_scaled_matched_ion_intensity"
    assert receipt["raw_positive_median"] == 20.0
    assert receipt["signal_quality"] == "single_positive_signal"
    assert receipt["raw_positive_mad"] is None
    assert receipt["positive_signal_fraction"] == 1.0
    assert receipt["missing_peptides"] == 0
    diagnostics = cast("dict[str, object]", target["search_diagnostics"])
    assert diagnostics["max_fragment_error_da"] == pytest.approx(0.0005254659999991418)
    multi = next(
        item for item in outcomes if item["scenario_id"] == "multi_peptide_quantification"
    )
    multi_receipt = cast("dict[str, object]", multi["quantification_receipt"])
    assert multi_receipt["signal_quality"] == "descriptive_positive_signal"
    assert multi_receipt["raw_positive_mad"] == 7.5
    assert multi_receipt["raw_positive_iqr"] == 15.0
    generated = cast("dict[str, object]", report["generated_search_space"])
    assert generated["passed"] is True
    generated_receipt = cast("dict[str, object]", generated["search_space_receipt"])
    assert generated_receipt["decoy_strategy"] == "reverse_protein"
    assert generated_receipt["generated_decoy_entries"] == 1
    assert generated_receipt["collision_peptides"] == 0


def test_research_pipeline_benchmark_is_deterministic() -> None:
    report = run_benchmark(3)
    assert cast("int", report["iterations"]) == 3
    samples = cast("list[int]", report["samples_ns"])
    assert len(samples) == 3
    assert report["percentile_method"] == "nearest_rank"
    assert cast("float", report["mean_ns"]) > 0
    assert cast("int", report["median_ns"]) > 0
    assert cast("int", report["p95_ns"]) > 0
    assert report["p95_ns"] == max(samples)
    assert len(cast("str", report["result_digest"])) == 64


def test_research_pipeline_benchmark_rejects_empty_iterations() -> None:
    with pytest.raises(ValueError):
        run_benchmark(0)
