# ruff: noqa: TRY003
"""Evaluate the existing conditional RNA/protein lane on exact real CPTAC sources.

Writes local-only aggregate diagnostics and the ordinary 1.0 artifact/query/replay.
The fixed literature panel is frozen before reading measurements. No patient rows,
identifiers, fold membership, predictions, residuals or source copies are persisted.
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
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.artifact import (
    build_artifact,
    write_artifact,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.continuation import (
    fit_continuation_gene,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    CohortArtifactSummary,
    DerivationStatus,
    GeneDiscordanceStatistics,
    ReplayVerificationRequest,
    TranscriptProteinDiscordanceRequest,
    UnverifiedTranscriptProteinDiscordanceResult,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.convergence_audit import (
    evaluate_convergence_budgets,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.evaluation import (
    evaluate_gene_inputs,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.fitter import (
    _fit_seed_digest,
    _statistics,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.model import (
    fit_transcript_protein_discordance_gene,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.profile import (
    algorithm_profile,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.service import (
    analyze_transcript_protein_discordance,
    verify_transcript_protein_discordance_replay,
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
EVALUATION_ID: Final = "cptac-gbm-real-data-evaluation/2.0.0"
LIMITATIONS: Final = (
    "Real measured source-cohort data; internal held-out evaluation, not external validation.",
    "Historical GBM cohort includes IDH-mutant tumors; no WHO2021 IDH-wildtype-only claim.",
    "Published whole-cohort normalization/ComBat predates our folds; "
    "raw-assay preprocessing is not fold-isolated.",
    "The literature panel was fixed before this run but informed by "
    "published source-cohort results.",
    "Nominal 90% patient-bootstrap intervals are not multiplicity-adjusted discovery tests.",
    "Conditional slopes are not causal, clinical, or mechanistic evidence; "
    "abundance does not identify mutation.",
    "Rank/condition diagnostics flag numerical ambiguity without changing "
    "the legacy 1.0 estimator or its labels.",
    "The separate 240-iteration continuation policy was chosen after "
    "development-cohort convergence failures; it is not independent validation.",
    "Continuation intervals condition on successful bootstrap refits; "
    "unsuccessful draws remain counted and are not replaced.",
    "No conditional-null calibration is claimed; independent RNA permutations "
    "would break RNA-CNV dependence.",
    "Aggregate artifacts remain local_only_terms_unverified; "
    "do not upload them or commit them to Git.",
)


def _source_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def frozen_protocol() -> dict[str, Any]:
    """Declare panel, exact sources and code bindings without reading measurements."""

    profile = algorithm_profile()
    evaluation_source = (
        files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
        .joinpath("evaluation.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    )
    protocol: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "panel": PANEL,
        "selection": "literature_defined_fixed_before_this_run_not_outcome_independent",
        "citations": [
            "https://doi.org/10.1016/j.ccell.2021.01.006",
            "https://doi.org/10.1016/j.cell.2013.09.034",
        ],
        "source_locks": [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS],
        "profile_digest": profile.profile_digest,
        "tool_source_digest": _source_hash(Path(__file__)),
        "evaluation_source_digest": "sha256:" + hashlib.sha256(evaluation_source).hexdigest(),
        "bootstrap_replicates": 128,
        "continuation_policy": {
            "profile_id": "cptac-gbm-transcript-protein-continuation/1.0.0",
            "iteration_budget": 240,
            "same_legacy_comparison_bootstrap_draws": True,
            "minimum_bootstrap_successful": 103,
            "legacy_artifact_promotion_permitted": False,
        },
        "iteration_budget_audit": {
            "budgets": (30, 60, 120, 240),
            "comparator_support": "intersection_of_accepted_folds_at_every_budget",
        },
        "continuation_source_digests": {
            name: "sha256:"
            + hashlib.sha256(
                files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
                .joinpath(name)
                .read_bytes()
                .replace(b"\r\n", b"\n")
            ).hexdigest()
            for name in ("convergence.py", "convergence_audit.py", "continuation.py")
        },
        "conditional_direction_policy": (
            "require_accepted_legacy_fit_exact_point_replay_and_identified_training_designs"
        ),
        "panel_replacement_permitted": False,
        "cohort_invariants": {"patient_groups": 96, "common_genes": 10_430},
        "python": platform.python_version(),
        "numpy": np.__version__,
        "redistribution_status": "local_only_terms_unverified",
        "limitations": LIMITATIONS,
    }
    return {**protocol, "protocol_digest": sha256_digest(protocol)}


def _write_json(path: Path, document: object) -> None:
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(document))


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = (
        "gene",
        "status",
        "legacy_pattern",
        "conditional_direction_eligible",
        "conditional_design_unidentified",
        "oof_patient_groups",
        "full_r2",
        "rna_only_r2",
        "cnv_only_r2",
        "delta_r2_vs_cnv_only",
        "delta_r2_vs_cnv_lower90",
        "delta_r2_vs_cnv_upper90",
        "bootstrap_successful",
        "continuation_accepted",
        "continuation_oof_patient_groups",
        "continuation_full_r2",
        "continuation_rna_only_r2",
        "continuation_cnv_only_r2",
        "continuation_delta_r2_vs_cnv_only",
        "continuation_bootstrap_successful",
    )
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def evaluate_sources(  # noqa: PLR0915 - complete source-to-replay evaluation orchestration.
    *, table_s2: Path, hgnc: Path, output_dir: Path
) -> dict[str, Any]:
    """Run every fixed-panel gene, preserving absence and failure as explicit states."""

    output_dir.mkdir(parents=True, exist_ok=False)
    protocol = frozen_protocol()
    _write_json(output_dir / "protocol.json", protocol)
    sys.stdout.write("Protocol frozen; verifying and privately staging exact sources.\n")
    sys.stdout.flush()
    statistics: dict[str, GeneDiscordanceStatistics] = {}
    evaluations: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    with _stage_exact_sources(table_s2=table_s2, hgnc=hgnc) as staged:
        cohort = prepare_cohort(staged.table_s2, staged.hgnc)
        if (
            cohort.exact_common_measurement_count,
            cohort.patient_group_count,
            len(cohort.common_genes),
        ) != (96, 96, 10_430):
            raise ValueError("exact source cohort invariants did not match")
        available = tuple(gene for gene in PANEL if gene in cohort.common_genes)
        for gene in PANEL:
            row: dict[str, Any] = {"gene": gene, "conditional_direction_eligible": False}
            if gene not in available:
                row["status"] = "absent_from_exact_common_gene_universe"
                evaluations.append({**row, "diagnostics": None})
            else:
                seed_digest = _fit_seed_digest(
                    gene_symbol=gene,
                    source_locks=EXACT_SOURCE_LOCKS,
                    profile_digest=protocol["profile_digest"],
                )
                fit = fit_transcript_protein_discordance_gene(
                    cohort.cnv[gene],
                    cohort.rna[gene],
                    cohort.protein[gene],
                    cohort.folds,
                    request_digest=seed_digest,
                )
                diagnostics = evaluate_gene_inputs(
                    cohort.cnv[gene],
                    cohort.rna[gene],
                    cohort.protein[gene],
                    cohort.folds,
                    fit=fit,
                )
                row.update(
                    status="accepted_legacy_fit" if fit is not None else "abstained_legacy_fit",
                    conditional_design_unidentified=diagnostics.conditional_design_unidentified,
                    conditional_direction_eligible=diagnostics.conditional_effect_reportable,
                )
                if fit is not None:
                    stats = _statistics(fit.summary)
                    statistics[gene] = stats
                    row.update(
                        oof_patient_groups=stats.full_model.n_oof,
                        full_r2=stats.full_model.r2_vs_fold_train_median,
                        rna_only_r2=stats.rna_only_r2,
                        cnv_only_r2=stats.cnv_only_r2,
                        delta_r2_vs_cnv_only=stats.delta_r2_vs_cnv_only,
                        delta_r2_vs_cnv_lower90=stats.bootstrap.delta_r2_vs_cnv_only.lower,
                        delta_r2_vs_cnv_upper90=stats.bootstrap.delta_r2_vs_cnv_only.upper,
                        bootstrap_successful=stats.bootstrap.successful_replicates,
                    )
                audit = evaluate_convergence_budgets(
                    cohort.cnv[gene],
                    cohort.rna[gene],
                    cohort.protein[gene],
                    cohort.folds,
                )
                continued = fit_continuation_gene(
                    cohort.cnv[gene],
                    cohort.rna[gene],
                    cohort.protein[gene],
                    cohort.folds,
                    request_digest=seed_digest,
                )
                row["continuation_accepted"] = continued.accepted
                row["continuation_bootstrap_successful"] = continued.bootstrap_successful
                if continued.summary is not None:
                    summary = continued.summary
                    row.update(
                        continuation_oof_patient_groups=summary.oof_patient_groups,
                        continuation_full_r2=summary.full_model.r2_vs_fold_train_median,
                        continuation_rna_only_r2=summary.rna_only.r2_vs_fold_train_median,
                        continuation_cnv_only_r2=summary.cnv_only.r2_vs_fold_train_median,
                        continuation_delta_r2_vs_cnv_only=summary.delta_r2_vs_cnv_only,
                    )
                evaluations.append(
                    {
                        **row,
                        "diagnostics": asdict(diagnostics),
                        "convergence_audit": asdict(audit),
                        "continuation": asdict(continued),
                    }
                )
            summary_rows.append(row)
            _write_json(output_dir / f"gene-{gene}.json", evaluations[-1])
            sys.stdout.write(f"{gene}: {row['status']}\n")
            sys.stdout.flush()

    verification: dict[str, Any] | None = None
    if statistics:
        artifact = build_artifact(
            source_locks=EXACT_SOURCE_LOCKS,
            cohort=CohortArtifactSummary(
                exact_common_measurement_count=96,
                patient_group_count=96,
                common_gene_count=10_430,
                fitted_gene_count=len(statistics),
            ),
            attempted_gene_symbols=available,
            gene_statistics=statistics,
            derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
        )
        artifact_path = output_dir / "artifact.json"
        write_artifact(artifact_path, artifact)
        request = TranscriptProteinDiscordanceRequest(
            query_id="cptac-gbm-real-literature-panel",
            artifact_content_digest=artifact.artifact_content_digest,
            gene_symbols=PANEL,
        )
        result = analyze_transcript_protein_discordance(request, artifact_path=artifact_path)
        envelope = ReplayVerificationRequest(
            request=request,
            result=UnverifiedTranscriptProteinDiscordanceResult.model_validate_json(
                canonical_json_bytes(result),
                strict=True,
            ),
        )
        verified = verify_transcript_protein_discordance_replay(
            envelope, artifact_path=artifact_path
        )
        if not verified.verified:
            raise RuntimeError("the freshly fitted real-source artifact failed exact replay")
        verification = verified.model_dump(mode="json")
        by_gene = {item.gene_symbol: item for item in result.genes}
        for row in summary_rows:
            item = by_gene[row["gene"]]
            row["legacy_pattern"] = None if item.pattern is None else item.pattern.value
        _write_json(output_dir / "request.json", request)
        _write_json(output_dir / "result.json", result)
        _write_json(output_dir / "replay-envelope.json", envelope)
        _write_json(output_dir / "replay-verification.json", verified)
    report = {
        "evaluation_id": EVALUATION_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_data": "real_measured_cptac_table_s2",
        "patient_groups": 96,
        "fixed_panel_size": len(PANEL),
        "status_counts": dict(Counter(row["status"] for row in summary_rows)),
        "continuation_accepted_count": sum(
            bool(row.get("continuation_accepted")) for row in summary_rows
        ),
        "genes": evaluations,
        "replay_verification": verification,
        "legacy_estimator_changed": False,
        "independent_validation": False,
        "redistribution_status": "local_only_terms_unverified",
        "limitations": LIMITATIONS,
    }
    report["report_digest"] = sha256_digest(report)
    _write_json(output_dir / "evaluation.json", report)
    _write_summary(output_dir / "summary.csv", summary_rows)
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
                "replay_verified": bool(report["replay_verification"]),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
