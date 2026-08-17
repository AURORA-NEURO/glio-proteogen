"""Execute the locked synthetic M15-02 evaluator corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m15_02_engine import _request

from glio_proteogen.contracts.m15_02 import (
    M1502_DOSSIER_SHA256,
    M1502_DOSSIER_SLICE,
    M1502_MODULE_ID,
    StratifyContextAndSubtypeRequest,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_02_context_subtype_stratifier as m1502,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_02" / "scenarios.json"


def _candidate(kind: str) -> object:
    request = _request()
    if kind == "supported":
        return request
    payload: dict[str, Any] = request.model_dump(mode="json")
    if kind == "inferred":
        payload["attributes"][0]["status"] = "inferred"
    elif kind == "prohibited_proxy":
        payload["mechanisms"][0]["mechanism_class"] = "kinase activity"
    elif kind == "denied_control":
        payload["context"]["references"]["consent"]["state"] = "withheld"
    elif kind == "wrong_upstream_media":
        payload["upstream_result"]["media_type"] = "application/json"
    elif kind == "unknown_field":
        payload["unexpected"] = "reject"
    elif kind == "duplicate_attribute":
        payload["attributes"].append(payload["attributes"][0])
    elif kind == "tampered_result":
        return (
            m1502.M1502ContextStratifierEngine()
            .construct(request)
            .model_copy(update={"human_review_required": False})
        )
    return StratifyContextAndSubtypeRequest.model_validate_json(json.dumps(payload), strict=True)


def _execute(kind: str) -> str:
    candidate = _candidate(kind)
    engine = m1502.M1502ContextStratifierEngine()
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
        except m1502.M1502AuthorizationError:
            actual = "authorization_error"
        except m1502.M1502ReplayVerificationError:
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
        "module_id": M1502_MODULE_ID,
        "dossier_slice": M1502_DOSSIER_SLICE,
        "dossier_sha256": M1502_DOSSIER_SHA256,
        "declared": len(fixture["cases"]),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
