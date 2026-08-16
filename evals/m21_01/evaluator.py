"""Executable M21-01 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m21_01 import CurationStatus, package_lock_digest
from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    M2101AuthorizationError,
    M2101Service,
)

from .fixture import build_request, denied_request, pending_request


def run_evaluator() -> dict[str, Any]:
    """Run deterministic supported, abstention, auth, and replay scenarios."""

    service = M2101Service()
    request = build_request()
    first = service.execute(request)
    second = service.execute(request)
    pending = service.execute(pending_request())
    authorization_failed = False
    try:
        service.execute(denied_request())
    except M2101AuthorizationError:
        authorization_failed = True
    replay = service.verify_replay(first)
    checks = {
        "curated_supported": first.status is CurationStatus.CURATED,
        "package_locked": first.package is not None
        and first.package.lock_digest == package_lock_digest(first.package),
        "pending_abstained": pending.status is CurationStatus.ABSTAINED and pending.package is None,
        "denied_fail_closed": authorization_failed,
        "deterministic_result": first.result_digest == second.result_digest,
        "replay_verified": replay.result_digest == first.result_digest,
    }
    return {
        "module": "M21-01",
        "scenario_count": len(checks),
        "passed": sum(checks.values()),
        "checks": checks,
        "fixture_request_digest": first.request_digest,
        "fixture_result_digest": first.result_digest,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_evaluator"]
