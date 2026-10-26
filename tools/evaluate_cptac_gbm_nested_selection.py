# ruff: noqa: TRY003
"""Evaluate a training-only nested comparator policy on exact real CPTAC inputs.

This local workflow freezes its panel and policy before reading measurements.
It writes aggregate prediction-policy evidence, never individual predictions or
the existing conditional-association artifact format. All outputs remain local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import Counter
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

import numpy as np

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import prepare_cohort
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.fitter import (
    _fit_seed_digest,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.nested_selection import (
    CANDIDATE_ORDER,
    PROFILE_ID,
    fit_nested_selection_gene,
    nested_selection_profile_digest,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.profile import (
    algorithm_profile,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
    _stage_exact_sources,
)

PANEL: Final = tuple(
    sorted(
        (
            "EGFR",
            "PDGFRA",
            "NF1",
            "PTEN",
            "PIK3CA",
            "PIK3R1",
            "PTPN11",
            "PLCG1",
            "TP53",
            "MDM2",
            "MDM4",
            "RB1",
            "CDK4",
            "CDKN2A",
            "CDKN2B",
            "IDH1",
        )
    )
)
EVALUATION_ID: Final = "cptac-gbm-real-nested-selection-evaluation/1.0.0"
LIMITATIONS: Final = (
    "Real exact-source, internal cohort evaluation; no independent validation.",
    "The prediction policy was developed after examining this cohort's prior model comparisons.",
    "Historical GBM scope includes IDH-mutant contexts; no expression-derived molecular diagnosis.",
    "Upstream whole-cohort source normalization and ComBat preceded the nested splits.",
    "Inner training minimum 32 is a new policy; the original conditional model is unchanged.",
    "Nominal 90% full-refit bootstrap intervals are not postselection-calibrated discovery tests.",
    "Model-selection frequencies are computational stability diagnostics, "
    "not biological probabilities.",
    "All real-data derivatives remain local_only_terms_unverified; do not upload or commit them.",
)


def _source_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def frozen_protocol() -> dict[str, Any]:
    """Bind numerical policy and code without reading source measurements."""

    legacy = algorithm_profile()
    root = files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
    protocol = {
        "evaluation_id": EVALUATION_ID,
        "prediction_policy_id": PROFILE_ID,
        "prediction_policy_digest": nested_selection_profile_digest(),
        "source_locks": [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS],
        "panel": PANEL,
        "panel_replacement_permitted": False,
        "panel_basis": "same_literature_defined_16_genes_from_prior_source_cohort_evaluation",
        "policy_development": "outcome_informed_development_cohort_not_independent_validation",
        "legacy_profile_digest": legacy.profile_digest,
        "comparison_bootstrap_seed_basis": "legacy_profile_exact_source_locks_and_gene",
        "tool_source_digest": _source_digest(Path(__file__).read_bytes()),
        "numerical_source_digests": {
            name: _source_digest(root.joinpath(name).read_bytes())
            for name in ("nested_selection.py", "convergence.py")
        },
        "selection": {
            "outer_folds": 5,
            "inner_folds": 4,
            "outer_training_complete_minimum": 48,
            "inner_training_complete_minimum": 32,
            "held_out_complete_minimum": 3,
            "valid_outer_fold_minimum": 4,
            "common_outer_oof_minimum": 60,
            "iteration_budget": 240,
            "candidate_family_tie_order": CANDIDATE_ORDER,
            "selection_loss": "unrounded_participant_weighted_inner_oof_mae",
            "inner_candidate_coverage": "every_prespecified_inner_validation_block",
            "comparison_support": "outer_folds_with_all_four_fixed_families_valid",
            "insufficient_inner_support_or_refit_failure": "explicit_training_median_fallback",
            "bootstrap_replicates": 128,
            "bootstrap_successful_minimum": 103,
            "bootstrap_refits_inner_selection": True,
            "bootstrap_preserves_original_fold_stratum_for_repeated_patients": True,
        },
        "cohort_invariants": {"patient_groups": 96, "common_genes": 10_430},
        "python": platform.python_version(),
        "numpy": np.__version__,
        "redistribution_status": "local_only_terms_unverified",
        "limitations": LIMITATIONS,
    }
    return {**protocol, "protocol_digest": sha256_digest(protocol)}


def _write_json(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(value))


def _summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = (
        "gene",
        "status",
        "complete_count",
        "point_common_oof",
        "selected_policy_oof",
        "bootstrap_attempted",
        "bootstrap_successful",
        "point_selected_mae",
        "point_selected_r2",
        "point_median_mae",
        "point_rna_only_mae",
        "point_cnv_only_mae",
        "point_full_mae",
        "point_mae_difference_vs_full",
        "point_r2_difference_vs_full",
        "mae_difference_vs_full_lower90",
        "mae_difference_vs_full_upper90",
        "selected_mae_lower90",
        "selected_mae_upper90",
        "selected_median_folds",
        "selected_rna_only_folds",
        "selected_cnv_only_folds",
        "selected_full_folds",
        "failure_reason",
    )
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))


def _csv_row(row: dict[str, Any]) -> dict[str, Any]:
    values = {"gene": row["gene"], "status": row["status"]}
    result = row.get("result")
    if result is None:
        return values
    values.update(
        complete_count=result["complete_count"],
        point_common_oof=result["common_oof_count"],
        selected_policy_oof=result["selected_oof_count"],
        bootstrap_attempted=result["bootstrap_attempted"],
        bootstrap_successful=result["bootstrap_successful"],
        failure_reason=result["failure_reason"],
    )
    point = result["point_summary"]
    if point is not None:
        values.update(
            point_selected_mae=point["selected"]["mae"],
            point_selected_r2=point["selected"]["r2_vs_fold_train_median"],
        )
        for metric in point["fixed"]:
            candidate = metric["candidate"].removeprefix("training_")
            values[f"point_{candidate}_mae"] = metric["mae"]
        for delta in point["deltas"]:
            if delta["candidate"] == "full":
                values["point_mae_difference_vs_full"] = delta["mae_difference"]
                values["point_r2_difference_vs_full"] = delta["r2_difference"]
        for count in point["selection_counts"]:
            candidate = count["candidate"].removeprefix("training_")
            values[f"selected_{candidate}_folds"] = count["fold_decisions"]
    uncertainty = result["uncertainty"]
    if uncertainty is not None:
        values.update(
            selected_mae_lower90=uncertainty["selected_mae"]["lower"],
            selected_mae_upper90=uncertainty["selected_mae"]["upper"],
        )
        for interval in uncertainty["paired_deltas"]:
            if interval["candidate"] == "full":
                values["mae_difference_vs_full_lower90"] = interval["mae_difference"]["lower"]
                values["mae_difference_vs_full_upper90"] = interval["mae_difference"]["upper"]
    return values


def evaluate_sources(*, table_s2: Path, hgnc: Path, output_dir: Path) -> dict[str, Any]:
    """Retain every predeclared gene and serialize aggregate results only."""

    output_dir.mkdir(parents=True, exist_ok=False)
    protocol = frozen_protocol()
    _write_json(output_dir / "protocol.json", protocol)
    sys.stdout.write("Nested-selection protocol frozen; staging exact real sources.\n")
    sys.stdout.flush()
    genes: list[dict[str, Any]] = []
    with _stage_exact_sources(table_s2=table_s2, hgnc=hgnc) as staged:
        cohort = prepare_cohort(staged.table_s2, staged.hgnc)
        if (
            cohort.patient_group_count,
            cohort.exact_common_measurement_count,
            len(cohort.common_genes),
        ) != (96, 96, 10_430):
            raise ValueError("exact source cohort invariants did not match")
        for symbol in PANEL:
            row: dict[str, Any]
            if symbol not in cohort.common_genes:
                row = {
                    "gene": symbol,
                    "status": "absent_from_exact_common_gene_universe",
                    "result": None,
                }
            else:
                comparison_digest = _fit_seed_digest(
                    gene_symbol=symbol,
                    source_locks=EXACT_SOURCE_LOCKS,
                    profile_digest=protocol["legacy_profile_digest"],
                )
                result = fit_nested_selection_gene(
                    cohort.cnv[symbol],
                    cohort.rna[symbol],
                    cohort.protein[symbol],
                    cohort.folds,
                    request_digest=comparison_digest,
                )
                row = {
                    "gene": symbol,
                    "status": "accepted_nested_policy"
                    if result.accepted
                    else "abstained_nested_policy",
                    "result": asdict(result),
                }
            genes.append(row)
            _write_json(output_dir / f"gene-{symbol}.json", row)
            sys.stdout.write(f"{symbol}: {row['status']}\n")
            sys.stdout.flush()
    report = {
        "evaluation_id": EVALUATION_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_data": "real_measured_cptac_table_s2",
        "patient_groups": 96,
        "fixed_panel_size": len(PANEL),
        "status_counts": dict(Counter(row["status"] for row in genes)),
        "genes": genes,
        "legacy_estimator_changed": False,
        "independent_validation": False,
        "redistribution_status": "local_only_terms_unverified",
        "limitations": LIMITATIONS,
    }
    report["report_digest"] = sha256_digest(report)
    _write_json(output_dir / "evaluation.json", report)
    _summary_csv(output_dir / "summary.csv", genes)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-s2", type=Path, required=True)
    parser.add_argument("--hgnc", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_sources(table_s2=args.table_s2, hgnc=args.hgnc, output_dir=args.output_dir)
    sys.stdout.write(
        json.dumps(
            {
                "report_digest": report["report_digest"],
                "status_counts": report["status_counts"],
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
