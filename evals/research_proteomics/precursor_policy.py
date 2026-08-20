"""Locked evaluator for caller-bound precursor tolerance semantics."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from glio_proteogen.research import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.research_proteomics.run import build_scenario_request, scenarios
else:
    from .run import build_scenario_request, scenarios

_NARROW_TOLERANCE_PPM = 1
_BROAD_TOLERANCE_PPM = 20


def _request_with_precursor(
    precursor_mz: str,
    *,
    tolerance_ppm: int,
) -> ResearchRunRequest:
    scenario = scenarios()[0]
    request = build_scenario_request(scenario)
    return replace(
        request,
        mzml_source=scenario.mzml.replace(
            b"1087.508837466",
            precursor_mz.encode("ascii"),
        ),
        precursor_tolerance_ppm=tolerance_ppm,
    )


def run_precursor_policy_evaluator() -> dict[str, object]:
    """Exercise matching, replay, configuration, and rejection boundaries."""

    narrow_request = _request_with_precursor("1087.510000000", tolerance_ppm=_NARROW_TOLERANCE_PPM)
    broad_request = _request_with_precursor("1087.510000000", tolerance_ppm=_BROAD_TOLERANCE_PPM)
    narrow = run_research_protein_inference(narrow_request)
    broad = run_research_protein_inference(broad_request)
    checks = {
        "narrow_policy_abstains": narrow.psms == (),
        "broad_policy_accepts": len(broad.psms) == 1,
        "configuration_is_bound": (
            dict(narrow.configuration)["precursor_tolerance_ppm"] == _NARROW_TOLERANCE_PPM
            and dict(broad.configuration)["precursor_tolerance_ppm"] == _BROAD_TOLERANCE_PPM
        ),
        "diagnostic_is_bound": (
            dict(narrow.search_diagnostics)["precursor_tolerance_ppm"] == _NARROW_TOLERANCE_PPM
            and dict(broad.search_diagnostics)["precursor_tolerance_ppm"] == _BROAD_TOLERANCE_PPM
        ),
        "policy_changes_digest": narrow.result_digest != broad.result_digest,
        "narrow_replay_passes": (
            replay_research_protein_inference(narrow_request, narrow).result_digest
            == narrow.result_digest
        ),
        "broad_replay_passes": (
            replay_research_protein_inference(broad_request, broad).result_digest
            == broad.result_digest
        ),
    }
    changed_replay_rejected = False
    try:
        replay_research_protein_inference(narrow_request, broad)
    except ValueError:
        changed_replay_rejected = True
    checks["changed_policy_replay_rejected"] = changed_replay_rejected
    return {
        "evaluator": "precursor-tolerance-policy-v1",
        "passed": all(checks.values()),
        "declared": len(checks),
        "executed": len(checks),
        "checks": checks,
        "narrow_result_digest": narrow.result_digest,
        "broad_result_digest": broad.result_digest,
    }


if __name__ == "__main__":
    import json

    sys.stdout.write(json.dumps(run_precursor_policy_evaluator(), sort_keys=True))
