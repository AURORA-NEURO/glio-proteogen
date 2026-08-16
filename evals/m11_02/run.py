"""Executable M11-02 evaluator matrix over synthetic non-clinical inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).parents[2]))

from evals.m11_02.support import request as _request
from glio_proteogen.contracts.m11_02 import ContextStratificationStatus
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c11_protein_native_subtype.m11_02_context_subtype_stratifier import (
    M1102AuthorizationError,
    M1102ContextEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m11_02" / "scenarios.json"


def _missing_dimension_request() -> object:
    request = _request()
    return request.model_copy(update={"observations": (request.observations[0],)})


def _proxy_request() -> object:
    return _request(disease="postcode")


def run() -> dict[str, Any]:
    """Run all declared evaluator scenarios and return JSON evidence."""

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    engine = M1102ContextEngine()
    checks: list[dict[str, object]] = []

    supported = engine.stratify(_request())
    checks.append(
        {
            "id": "supported_context_stratifies",
            "passed": supported.status is ContextStratificationStatus.STRATIFIED,
            "status": supported.status.value,
        }
    )
    low_support = engine.stratify(_request(disease_score=0.2))
    checks.append(
        {
            "id": "low_support_abstains",
            "passed": (
                low_support.status is ContextStratificationStatus.ABSTAINED
                and low_support.profile is None
                and low_support.human_review_required
            ),
            "status": low_support.status.value,
        }
    )
    missing = engine.stratify(_missing_dimension_request())
    checks.append(
        {
            "id": "missing_context_abstains",
            "passed": missing.status is ContextStratificationStatus.ABSTAINED,
            "status": missing.status.value,
        }
    )
    proxy = engine.stratify(_proxy_request())
    checks.append(
        {
            "id": "prohibited_proxy_abstains",
            "passed": proxy.status is ContextStratificationStatus.ABSTAINED,
            "status": proxy.status.value,
        }
    )
    replayed = engine.verify(supported)
    checks.append(
        {
            "id": "replay_is_exact",
            "passed": replayed.model_dump(mode="json") == supported.model_dump(mode="json"),
            "status": "verified",
        }
    )
    altered = supported.model_copy(update={"abstention_reason": "tamper"})
    tamper_rejected = False
    try:
        engine.verify(altered)
    except (ValueError, TypeError):
        tamper_rejected = True
    checks.append({"id": "tamper_is_rejected", "passed": tamper_rejected, "status": "rejected"})
    denied = False
    try:
        engine.stratify(_request(consent=ConsentState.WITHHELD))
    except M1102AuthorizationError:
        denied = True
    checks.append({"id": "denied_consent_fails_closed", "passed": denied, "status": "denied"})
    deterministic = engine.stratify(_request()).model_dump(mode="json") == supported.model_dump(
        mode="json"
    )
    checks.append({"id": "repeat_is_deterministic", "passed": deterministic, "status": "stable"})
    passed = all(bool(item["passed"]) for item in checks)
    return {
        "module_id": "GLIO-PROTEOGEN-M11-02",
        "contract_version": "0.1.0-provisional",
        "fixture": fixture,
        "checks": checks,
        "passed": passed,
        "check_count": len(checks),
    }


if __name__ == "__main__":
    import sys

    sys.stdout.write(json.dumps(run(), indent=2, sort_keys=True) + "\n")
