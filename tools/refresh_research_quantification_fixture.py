# ruff: noqa: E402, I001, TRY003
"""Refresh locked single-run fixture projections after research receipt changes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.research_proteomics.run import build_scenario_request, scenarios
from glio_proteogen.research import run_research_protein_inference

_FIXTURE = _ROOT / "tests" / "fixtures" / "research" / "proteomics_scenarios.json"


def refresh() -> None:
    """Update only replay-derived receipt and result-digest projections."""

    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    records = {record["id"]: record for record in fixture["scenarios"]}
    locked = scenarios()
    if tuple(records) != tuple(item.scenario_id for item in locked):
        raise ValueError("fixture scenario inventory does not match the locked evaluator")
    fixture["fixture_version"] = "research-proteomics-5"
    for scenario in locked:
        result = run_research_protein_inference(build_scenario_request(scenario))
        record = records[scenario.scenario_id]
        record["expected_psms"] = len(result.psms)
        record["expected_accepted"] = len(result.accepted_psms)
        record["expected_groups"] = [list(group.accessions) for group in result.protein_groups]
        record["expected_shared"] = [
            peptide for group in result.protein_groups for peptide in group.shared_peptides
        ]
        if result.fdr_summary is None or result.protein_group_fdr_summary is None:
            raise ValueError("locked scenario has no FDR summary")
        record["expected_target_winners"] = result.fdr_summary.target_winners
        record["expected_decoy_winners"] = result.fdr_summary.decoy_winners
        record["expected_collision_winners"] = result.fdr_summary.collision_winners
        record["expected_quantified_peptides"] = len(result.peptide_intensities)
        record["expected_group_quant"] = [
            {
                "group_accessions": list(item.group_accessions),
                "primary_intensity": item.primary_intensity,
                "status": item.status,
            }
            for item in result.protein_group_quantifications
        ]
        record["expected_group_fdr"] = result.protein_group_fdr_summary.as_dict()
        record["expected_group_candidates"] = [
            {
                "accessions": list(item.accessions),
                "acceptance": item.acceptance,
                "q_value": item.q_value,
                "status": item.status,
            }
            for item in result.protein_group_candidates
        ]
        record["fasta_sha256"] = result.fasta_sha256
        record["mzml_sha256"] = result.mzml_sha256
        record["expected_result_digest"] = result.result_digest
        record["expected_psm_peptides"] = [item.peptide for item in result.psms]
        record["expected_q_values"] = [item.q_value for item in result.psms]
        record["expected_peptide_intensities"] = [list(item) for item in result.peptide_intensities]
        record["expected_search_diagnostics"] = dict(result.search_diagnostics)
        record["expected_competition_audit"] = [item.as_dict() for item in result.competition_audit]
        if result.quantification_receipt is None:
            raise ValueError("locked scenario has no quantification receipt")
        record["expected_quantification_receipt"] = result.quantification_receipt.as_dict()
    _FIXTURE.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    refresh()
