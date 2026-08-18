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
    fixture["fixture_version"] = "research-proteomics-3"
    for scenario in locked:
        result = run_research_protein_inference(build_scenario_request(scenario))
        record = records[scenario.scenario_id]
        record["expected_result_digest"] = result.result_digest
        if result.quantification_receipt is None:
            raise ValueError("locked scenario has no quantification receipt")
        record["expected_quantification_receipt"] = result.quantification_receipt.as_dict()
    _FIXTURE.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    refresh()
