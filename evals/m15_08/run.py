"""Execute the locked synthetic M15-08 evaluator corpus."""

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

from tests.runtime.test_m15_08_engine import _request

from glio_proteogen.contracts.m15_08 import (
    M1508_DOSSIER_SHA256,
    M1508_DOSSIER_SLICE,
    M1508_MODULE_ID,
    AssembleComplexActivityMechanismDossierRequest,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_08_mechanism_evidence_dossier as m1508,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m15_08" / "scenarios.json"


def _candidate(kind: str) -> object:
    request = _request()
    if kind == "supported":
        return request
    payload: dict[str, Any] = request.model_dump(mode="json")
    if kind == "denied_control":
        payload["context"]["references"]["consent"]["state"] = "withheld"
    elif kind == "wrong_upstream_media":
        payload["upstream_result"]["media_type"] = "application/json"
    elif kind == "unknown_field":
        payload["unexpected"] = "reject"
    elif kind == "duplicate_source":
        payload["source_artifacts"][1] = payload["source_artifacts"][0]
    elif kind == "missing_manifest":
        payload["configuration"]["source_manifest"] = []
    elif kind == "missing_counter_input":
        payload["source_artifacts"] = []
    elif kind == "tampered_result":
        return m1508.M1508Service().execute(request).model_copy(
            update={"human_review_required": False}
        )
    return AssembleComplexActivityMechanismDossierRequest.model_validate_json(
        json.dumps(payload),
        strict=True,
    )


def _execute(kind: str) -> str:
    candidate = _candidate(kind)
    service = m1508.M1508Service()
    if kind == "tampered_result":
        service.verify(candidate)
        return "verified"
    return service.construct(candidate).status.value


def main() -> int:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    outcomes: list[dict[str, object]] = []
    for case in fixture["cases"]:
        expected = case["expected"]
        try:
            actual = _execute(case["kind"])
        except m1508.M1508AuthorizationError:
            actual = "authorization_error"
        except m1508.M1508ReplayVerificationError:
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
        "module_id": M1508_MODULE_ID,
        "dossier_slice": M1508_DOSSIER_SLICE,
        "dossier_sha256": M1508_DOSSIER_SHA256,
        "declared": len(fixture["cases"]),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
