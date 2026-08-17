"""Executable M26-06 evaluation matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m26_06.fixture import load_scenarios, request_for
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606AuthorizationError,
    M2606SecurityService,
)


def run_evaluator() -> dict[str, Any]:
    service = M2606SecurityService()
    records: list[dict[str, Any]] = []
    for scenario in load_scenarios():
        scenario_id = str(scenario["scenario_id"])
        request = request_for(
            scenario_id,
            control_mode=str(scenario["control_mode"]),
            consent=str(scenario["consent"]),
        )
        try:
            result = service.execute(request)
        except M2606AuthorizationError:
            records.append(
                {
                    "scenario_id": scenario_id,
                    "outcome": "authorization_rejected",
                    "safe": True,
                }
            )
            continue
        records.append(
            {
                "scenario_id": scenario_id,
                "outcome": result.status.value,
                "support": result.support_decision.status.value,
                "result_digest": result.result_digest,
                "replay_verified": service.verify(result).result_digest == result.result_digest,
                "safe": result.status.value in {"evaluated", "abstained"},
            }
        )
    return {
        "module": "M26-06",
        "scenario_count": len(records),
        "passed": sum(1 for record in records if record["safe"]),
        "records": records,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
