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
from glio_proteogen.contracts.m26_06.canonical import result_payload_digest
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606AuthorizationError,
    M2606ReplayError,
    M2606SecurityService,
)

_MODULE_ID = "GLIO-PROTEOGEN-M26-06"
_CONTRACT_VERSION = "0.1.0-provisional"
_AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
_AUTHORITY_SLICE = "source-manifest.yaml:9256-9296"


def run_evaluator() -> dict[str, Any]:
    service = M2606SecurityService()
    records: list[dict[str, Any]] = []
    semantic_replay_recompute = False
    self_rehashed_digest_rejected = False
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
        if result.status.value == "evaluated":
            semantic_replay_recompute = (
                service.verify(result).result_digest == result.result_digest
            )
            evidence = result.evidence[0].model_copy(update={"claim": "forged evidence"})
            candidate = result.model_copy(update={"evidence": (evidence, *result.evidence[1:])})
            forged = type(candidate).model_construct(
                **{
                    **candidate.__dict__,
                    "result_digest": result_payload_digest(candidate),
                }
            )
            try:
                service.verify(forged)
            except M2606ReplayError:
                self_rehashed_digest_rejected = True
    return {
        "module": "M26-06",
        "moduleId": _MODULE_ID,
        "contractVersion": _CONTRACT_VERSION,
        "authoritySha256": _AUTHORITY_SHA256,
        "authoritySlice": _AUTHORITY_SLICE,
        "scenario_count": len(records),
        "passed": sum(1 for record in records if record["safe"]),
        "allPassed": all(record["safe"] for record in records),
        "semanticReplayRecompute": semantic_replay_recompute,
        "selfRehashedDigestRejected": self_rehashed_digest_rejected,
        "records": records,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
