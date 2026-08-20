"""Focused evaluator for research-only quantification policy semantics."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from glio_proteogen.research import (
    QuantificationPolicy,
    quantify_matched_ions_with_receipt,
    replay_research_protein_inference,
    run_research_protein_inference,
)

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.research_proteomics.run import build_scenario_request, scenarios
else:
    from .run import build_scenario_request, scenarios

_LOQ = 4.0
_BELOW_LOQ = 2
_QUANTIFIABLE = 1
_NORMALIZED_TOTAL = 10.0


def run_quantification_policy_evaluator() -> dict[str, object]:
    """Exercise LOQ, normalization, and single-run replay binding explicitly."""

    policy = QuantificationPolicy(normalization_method="none_v1", limit_of_quantification=_LOQ)
    projection = quantify_matched_ions_with_receipt(
        "policy-eval",
        (("P1", 2.0), ("P2", 1.0), ("P3", 10.0)),
        policy=policy,
    )
    quant_passed = (
        projection.receipt.below_loq_peptides == _BELOW_LOQ
        and projection.receipt.quantifiable_peptides == _QUANTIFIABLE
        and projection.receipt.normalized_total_signal == _NORMALIZED_TOTAL
        and projection.receipt.as_dict()["limit_of_quantification"] == _LOQ
    )
    request = replace(build_scenario_request(scenarios()[0]), quantification_policy=policy)
    result = run_research_protein_inference(request)
    replayed = replay_research_protein_inference(request, result)
    replay_passed = (
        dict(result.configuration)["quantification_policy"] == policy.as_dict()
        and result.quantification_receipt is not None
        and result.quantification_receipt.limit_of_quantification == _LOQ
        and replayed.result_digest == result.result_digest
    )
    outcomes = (
        {"scenario_id": "loq_below_signal", "passed": quant_passed},
        {"scenario_id": "policy_replay_binding", "passed": replay_passed},
    )
    return {
        "passed": all(bool(item["passed"]) for item in outcomes),
        "declared": len(outcomes),
        "executed": len(outcomes),
        "outcomes": outcomes,
    }


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.write(json.dumps(run_quantification_policy_evaluator(), sort_keys=True))
