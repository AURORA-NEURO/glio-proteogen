"""Executable M23-02 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m23_02 import FixtureKind, TruthRepresentation
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m23_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2302AuthorizationError,
    M2302ReplayError,
    M2302Service,
)

from .fixture import build_request, denied_request

_EXPECTED_PER_KIND = 2
_EXPECTED_CONTROLS = 7


def run_evaluator() -> dict[str, Any]:
    """Run the locked generated, boundary, determinism, and tamper matrix."""

    service = M2302Service()
    request = build_request()
    first = service.execute(request)
    second = service.execute(request)
    cases = first.corpus.cases if first.corpus is not None else ()
    fixture_counts = {
        kind.value: sum(case.fixture_kind is kind for case in cases) for kind in FixtureKind
    }
    analytic_kinds = {FixtureKind.NORMAL, FixtureKind.EDGE}
    semi_synthetic_kinds = {
        FixtureKind.MISSING,
        FixtureKind.SHIFTED,
        FixtureKind.ADVERSARIAL,
    }
    checks: dict[str, bool] = {
        "generated_status": first.status.value == "generated",
        "requested_count": len(cases) == request.requested_case_count,
        "all_fixture_kinds": set(fixture_counts) == {kind.value for kind in FixtureKind},
        "two_each_fixture_kind": all(
            value == _EXPECTED_PER_KIND for value in fixture_counts.values()
        ),
        "analytic_representations": all(
            case.representation is TruthRepresentation.ANALYTIC
            for case in cases
            if case.fixture_kind in analytic_kinds
        ),
        "semi_synthetic_representations": all(
            case.representation is TruthRepresentation.SEMI_SYNTHETIC
            for case in cases
            if case.fixture_kind in semi_synthetic_kinds
        ),
        "manifest_reproducible": (
            first.manifest is not None
            and first.manifest.reproducibility_digest != "sha256:" + ("0" * 64)
        ),
        "deterministic_result": first.result_digest == second.result_digest,
        "replay_verified": service.verify(first).result_digest == first.result_digest,
        "parent_boundary": first.parent_target == "variant peptide" and not first.emits_parent,
        "seven_controls_provenanced": (
            len(first.provenance.control_decisions) == _EXPECTED_CONTROLS
        ),
    }
    try:
        service.execute(denied_request())
    except M2302AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = first.model_copy(update={"result_digest": sha256_digest("m2302.tampered")})
    try:
        service.verify(tampered)
    except M2302ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M23-02",
        "fixture_request_digest": sha256_digest(request),
        "fixture_result_digest": first.result_digest,
        "fixture_counts": fixture_counts,
        "checks": checks,
        "passed": sum(checks.values()),
        "scenario_count": len(checks),
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_evaluator"]
