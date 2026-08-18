"""Locked evaluator for research-only FDR, quantification, and group invariants."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from itertools import pairwise

from glio_proteogen.research import (
    Psm,
    QuantificationPolicy,
    infer_protein_group_candidates,
    quantify_matched_ions_with_receipt,
    summarize_target_decoy,
    target_decoy_qvalues,
)

from .run import build_scenario_request, scenarios

_EXPECTED_WINNERS = 3
_EXPECTED_BELOW_LOQ = 2
_EXPECTED_MISSING = 3
_EXPECTED_TOTAL_SIGNAL = 8.0


def run_fdr_quant_group_invariants_evaluator() -> dict[str, object]:
    """Exercise the computation boundaries that can silently overstate evidence."""

    target_high = Psm("scan=1", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    target_low = Psm("scan=2", "PEPTIDEK", ("P2",), 4.0, 3, decoy=False)
    decoy = Psm("scan=3", "PEPTIDER", ("DECOY_P1",), 3.0, 3, decoy=True)
    scored = target_decoy_qvalues((decoy, target_low, target_high))
    collision = Psm(
        "scan=collision",
        "PEPTIDER",
        ("P1", "DECOY_P1"),
        6.0,
        3,
        decoy=False,
        target_decoy_collision=True,
    )
    collision_summary = summarize_target_decoy((collision, target_high), q_value_threshold=0.01)
    target_q_values = tuple(
        item.q_value for item in scored if not item.decoy and not item.target_decoy_collision
    )
    forged_flag_rejected = False
    try:
        target_decoy_qvalues((replace(target_high, protein_accessions=("DECOY_P1",)),))
    except ValueError:
        forged_flag_rejected = True

    quantification = quantify_matched_ions_with_receipt(
        "fdr-quant-eval",
        (("PEPTIDE_AT", 4.0), ("PEPTIDE_BELOW", 3.0), ("PEPTIDE_ZERO", 0.0), ("PEPTIDE_OK", 8.0)),
        policy=QuantificationPolicy(normalization_method="none_v1", limit_of_quantification=4.0),
    )
    shared_only, shared_summary = infer_protein_group_candidates(
        (Psm("shared", "SHARED", ("P1", "P2"), 5.0, 3, decoy=False),),
        q_value_threshold=0.01,
    )
    collision_groups, collision_group_summary = infer_protein_group_candidates(
        (collision, target_low), q_value_threshold=0.01
    )
    scenario = scenarios()[0]
    request = build_scenario_request(scenario)
    source_sha256 = {
        "fasta": sha256(scenario.fasta).hexdigest(),
        "mzml": sha256(scenario.mzml).hexdigest(),
    }
    checks = {
        "target_decoy_winner_count": len(scored) == _EXPECTED_WINNERS,
        "decoys_have_no_q_value": all(item.q_value is None for item in scored if item.decoy),
        "target_q_values_monotone": all(
            left <= right
            for left, right in pairwise(target_q_values)
            if left is not None and right is not None
        ),
        "forged_decoy_flag_rejected": forged_flag_rejected,
        "collision_counts_as_peptide_fdr_decoy": (
            collision_summary.decoy_to_target_ratio == 1.0
            and collision_summary.accepted_targets == 0
        ),
        "collision_counts_as_group_fdr_decoy": (
            collision_group_summary.decoy_to_target_ratio == 1.0
            and next(item for item in collision_groups if item.status == "target").q_value == 1.0
        ),
        "exact_loq_is_missing": (
            quantification.receipt.below_loq_peptides == _EXPECTED_BELOW_LOQ
            and quantification.receipt.missing_peptides == _EXPECTED_MISSING
            and dict(quantification.receipt.raw_peptide_statuses)["PEPTIDE_AT"] == "below_loq"
        ),
        "no_imputation_at_loq": (
            quantification.receipt.normalized_total_signal == _EXPECTED_TOTAL_SIGNAL
        ),
        "shared_only_group_abstains": (
            shared_summary.shared_only_candidates == 1
            and shared_only[0].identifiability == "shared_only_ambiguous"
            and shared_only[0].acceptance == "abstained"
        ),
        "fixture_provenance_is_bound": bool(request.fasta_source and request.mzml_source),
    }
    return {
        "evaluator": "fdr-quantification-group-invariants-v1",
        "passed": all(checks.values()),
        "declared": len(checks),
        "executed": len(checks),
        "checks": checks,
        "fixture_id": scenario.scenario_id,
        "fixture_sha256": source_sha256,
        "target_q_values": list(target_q_values),
        "shared_group_accessions": [list(item.accessions) for item in shared_only],
    }


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.write(json.dumps(run_fdr_quant_group_invariants_evaluator(), sort_keys=True))
