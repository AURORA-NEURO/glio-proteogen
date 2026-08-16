"""Run the locked M16-06 evaluator corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tests.runtime.test_m16_06_queue import _request

from glio_proteogen.contracts.m16_06 import (
    M1606_DOSSIER_SHA256,
    M1606_DOSSIER_SLICE,
    M1606_M1605_INPUT_MEDIA_TYPE,
    ReviewDecision,
)
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    M1606AuthorizationError,
    M1606Engine,
    M1606ReplayError,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m16_06" / "scenarios.json"


def _case(case_id: str) -> tuple[str, Any]:  # noqa: PLR0911
    if case_id == "supported-immutable-review":
        return "recorded", _request()
    if case_id == "deferred-review-abstention":
        return "abstained", _request(decision=ReviewDecision.DEFER)
    if case_id == "withheld-consent":
        return "authorization_error", _request(consent=ConsentState.WITHHELD)
    if case_id == "conflicted-identity":
        request = _request()
        identity = request.context.references.identity_lineage.model_copy(
            update={"state": IdentityLineageState.CONFLICTED}
        )
        references = request.context.references.model_copy(update={"identity_lineage": identity})
        context = request.context.model_copy(update={"references": references})
        return "authorization_error", request.model_copy(update={"context": context})
    if case_id == "wrong-upstream-media":
        bad_upstream = _request().upstream_result.model_copy(
            update={"media_type": "application/bad+json"}
        )
        return "validation_error", _request().model_copy(
            update={"upstream_result": bad_upstream}
        )
    if case_id == "unknown-field":
        return "validation_error", {**_request().model_dump(mode="json"), "unknown": True}
    if case_id == "duplicate-discrepancy":
        return "validation_error", {**_request().model_dump(mode="json"), "entries": [
            *_request().model_dump(mode="json")["entries"],
            *_request().model_dump(mode="json")["entries"],
        ]}
    if case_id == "tampered-result":
        result = M1606Engine().adjudicate(_request())
        return "replay_error", result.model_copy(update={"result_digest": "sha256:" + "2" * 64})
    raise ValueError(f"unknown evaluator case: {case_id}")  # noqa: TRY003


def _execute(case_id: str) -> str:
    _expected, payload = _case(case_id)
    try:
        if case_id == "tampered-result":
            M1606Engine().replay(payload)
            return "unexpected_success"
        result = M1606Engine().adjudicate(payload)
        return result.status.value  # noqa: TRY300
    except M1606AuthorizationError:
        return "authorization_error"
    except M1606ReplayError:
        return "replay_error"
    except (ValidationError, ValueError):
        return "validation_error"


def main() -> dict[str, object]:
    scenarios = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    outcomes = []
    for scenario in scenarios:
        actual = _execute(scenario["id"])
        outcomes.append(
            {
                "id": scenario["id"],
                "expected": scenario["expected"],
                "actual": actual,
                "passed": actual == scenario["expected"],
            }
        )
    return {
        "module_id": "GLIO-PROTEOGEN-M16-06",
        "dossier_sha256": M1606_DOSSIER_SHA256,
        "dossier_slice": M1606_DOSSIER_SLICE,
        "upstream_media_type": M1606_M1605_INPUT_MEDIA_TYPE,
        "declared": len(scenarios),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(item["passed"] for item in outcomes),
    }


if __name__ == "__main__":
    report = main()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    raise SystemExit(0 if report["passed"] else 1)
