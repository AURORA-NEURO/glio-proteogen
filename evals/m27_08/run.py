"""M27-08 executable evaluator."""

# Evaluator scripts intentionally print machine-readable reports.
# ruff: noqa: T201

from __future__ import annotations

import hashlib
import json

from evals.m27_08.fixture import build_request
from glio_proteogen.contracts.m27_08 import RetirementRunStatus
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import M2708Service


def main() -> int:
    service = M2708Service()
    approved = service.execute(build_request())
    review = service.execute(build_request(incomplete=True))
    denied = False
    try:
        service.execute(build_request(consent=ConsentState.WITHHELD))
    except ValueError:
        denied = True
    checks = {
        "executed": approved.status is RetirementRunStatus.EXECUTED
        and approved.package is not None,
        "abstained": review.status is RetirementRunStatus.ABSTAINED and review.package is None,
        "safe_failure": review.human_review_required and bool(review.findings),
        "authorization_denied": denied,
        "replay": service.verify(approved),
        "tamper_rejected": not service.verify(
            approved.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        ),
        "deterministic": approved.result_digest == service.execute(build_request()).result_digest,
    }
    fixture_digest = (
        "sha256:" + hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest()
    )
    payload = {
        "module_id": "GLIO-PROTEOGEN-M27-08",
        "checks": checks,
        "checks_declared": len(checks),
        "checks_passed": sum(checks.values()),
        "fixture_digest": fixture_digest,
        "passed": all(checks.values()),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
