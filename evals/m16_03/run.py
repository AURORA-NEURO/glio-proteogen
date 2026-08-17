"""Execute the locked synthetic M16-03 evaluator corpus."""

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

from tests.runtime.test_m16_03_engine import _request

from glio_proteogen.contracts.m16_03 import (
    M1603_DOSSIER_SHA256,
    M1603_DOSSIER_SLICE,
    M1603_MODULE_ID,
    FuseProteinRnaDiscordanceEvidenceRequest,
)
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    m16_03_fusion_aggregation_engine as m1603,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m16_03" / "scenarios.json"


def _candidate(kind: str) -> object:
    request = _request()
    if kind == "supported":
        return request
    payload: dict[str, Any] = request.model_dump(mode="json")
    if kind == "low_reliability":
        payload["contributions"][0]["reliability_score"] = 0.2
        payload["contributions"][0]["reliability_band"] = "low"
    elif kind == "not_evaluable":
        payload["contributions"][0]["reliability_score"] = 0.0
        payload["contributions"][0]["reliability_band"] = "not_evaluable"
    elif kind == "denied_control":
        payload["context"]["references"]["consent"]["state"] = "withheld"
    elif kind == "wrong_upstream_media":
        payload["alignment_result"]["media_type"] = "application/json"
    elif kind == "unknown_field":
        payload["unexpected"] = "reject"
    elif kind == "duplicate_source":
        payload["contributions"][1]["source_id"] = payload["contributions"][0]["source_id"]
    elif kind == "tampered_result":
        return m1603.M1603Service().execute(request).model_copy(
            update={"human_review_required": False}
        )
    return FuseProteinRnaDiscordanceEvidenceRequest.model_validate_json(
        json.dumps(payload),
        strict=True,
    )


def _execute(kind: str) -> str:
    candidate = _candidate(kind)
    service = m1603.M1603Service()
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
        except m1603.M1603AuthorizationError:
            actual = "authorization_error"
        except m1603.M1603ReplayVerificationError:
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
        "module_id": M1603_MODULE_ID,
        "dossier_slice": M1603_DOSSIER_SLICE,
        "dossier_sha256": M1603_DOSSIER_SHA256,
        "declared": len(fixture["cases"]),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
