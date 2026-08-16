"""Execute the locked synthetic M15-05 evaluator corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tests.runtime.test_m15_05_engine import _request

from glio_proteogen.contracts.m15_05 import (
    M1505_DOSSIER_SHA256,
    M1505_DOSSIER_SLICE,
    M1505_MODULE_ID,
    ModelComplexActivityLongitudinalEvolutionRequest,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_05" / "scenarios.json"


def _candidate(kind: str) -> object:
    request = _request()
    if kind == "supported":
        return request
    payload: dict[str, Any] = request.model_dump(mode="json")
    if kind == "denied_control":
        payload["context"]["references"]["consent"]["state"] = "withheld"
    elif kind == "out_of_order":
        payload["observations"] = list(reversed(payload["observations"]))
    elif kind == "insufficient_history":
        payload["policy"]["minimum_observations"] = 3
    elif kind == "wrong_upstream_media":
        payload["network_state_result"]["media_type"] = "application/json"
    elif kind == "unknown_field":
        payload["unexpected"] = "reject"
    elif kind == "duplicate_observation":
        payload["observations"][1]["observation_id"] = payload["observations"][0]["observation_id"]
    elif kind == "tampered_result":
        return (
            m1505.M1505EvolutionEngine()
            .construct(request)
            .model_copy(update={"human_review_required": False})
        )
    return ModelComplexActivityLongitudinalEvolutionRequest.model_validate_json(
        json.dumps(payload),
        strict=True,
    )


def _execute(kind: str) -> str:
    candidate = _candidate(kind)
    engine = m1505.M1505EvolutionEngine()
    if kind == "tampered_result":
        engine.verify(candidate)
        return "verified"
    result = engine.construct(candidate)
    return result.status.value


def main() -> int:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    outcomes: list[dict[str, object]] = []
    for case in fixture["cases"]:
        expected = case["expected"]
        try:
            actual = _execute(case["kind"])
        except m1505.M1505AuthorizationError:
            actual = "authorization_error"
        except m1505.M1505ReplayVerificationError:
            actual = "replay_error"
        except (ValidationError, TypeError, ValueError):
            actual = "validation_error"
        outcomes.append(
            {
                "id": case["id"],
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )
    report = {
        "module_id": M1505_MODULE_ID,
        "dossier_slice": M1505_DOSSIER_SLICE,
        "dossier_sha256": M1505_DOSSIER_SHA256,
        "declared": len(fixture["cases"]),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
