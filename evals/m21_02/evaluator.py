"""Executable M21-02 synthetic-truth evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m21_02 import FixtureKind, GenerationStatus
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2102AuthorizationError,
    M2102Service,
)

from .fixture import build_request, denied_request


def run_evaluator() -> dict[str, Any]:
    service = M2102Service()
    request = build_request()
    first = service.generate(request)
    second = service.generate(request)
    authorization_failed = False
    try:
        service.generate(denied_request())
    except M2102AuthorizationError:
        authorization_failed = True
    replay = service.replay(first)
    cases = first.corpus.cases if first.corpus is not None else ()
    checks = {
        "generated_status": first.status is GenerationStatus.GENERATED,
        "requested_count": len(cases) == request.requested_case_count,
        "all_fixture_kinds": {case.fixture_kind for case in cases}
        == set(request.configuration.requested_fixture_kinds),
        "analytically_recoverable": all(case.analytically_recoverable for case in cases),
        "deterministic_result": first.result_digest == second.result_digest,
        "replay_verified": replay.result_digest == first.result_digest,
        "denied_fail_closed": authorization_failed,
        "parent_boundary": first.parent_target == "complex activity" and not first.emits_parent,
    }
    return {
        "module": "M21-02",
        "scenario_count": len(checks),
        "passed": sum(checks.values()),
        "checks": checks,
        "fixture_kinds": [kind.value for kind in FixtureKind],
        "fixture_request_digest": first.request_digest,
        "fixture_result_digest": first.result_digest,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_evaluator"]
