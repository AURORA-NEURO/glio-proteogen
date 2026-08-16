"""Executable M22-01 reference-truth curation evaluator matrix."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from glio_proteogen.contracts.m22_01 import CurationStatus, reference_truth_package_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_01_reference_truth_benchmark_curator import (
    M2201AuthorizationError,
    M2201ReplayError,
    M2201Service,
)

from .fixture import build_request, pending_request

if TYPE_CHECKING:
    from glio_proteogen.contracts.m22_01 import CurateProteinRnaDiscordanceReferenceTruthRequest

_REFERENCE_COUNT = 2
_CONTROL_COUNT = 1


def _denied_request() -> CurateProteinRnaDiscordanceReferenceTruthRequest:
    request = build_request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    return request.model_copy(update={"context": context})


def run_evaluator() -> dict[str, Any]:
    service = M2201Service()
    request = build_request()
    result = service.curate(request)
    repeated = service.curate(request)
    pending = service.curate(pending_request())
    package = result.package
    checks: dict[str, bool] = {
        "curated_status": result.status is CurationStatus.CURATED,
        "locked_package_present": package is not None and package.locked,
        "endpoint_parent_closed": (
            package is not None and package.endpoint.target == "protein-RNA discordance"
        ),
        "reference_control_partition": (
            package is not None
            and len(package.references) == _REFERENCE_COUNT
            and len(package.controls) == _CONTROL_COUNT
        ),
        "challenge_set_explicit": (
            package is not None and package.challenge_set_ids == ("m2201.challenge",)
        ),
        "adjudications_locked": (
            package is not None
            and all(item.status.value == "locked" for item in package.adjudications)
        ),
        "lock_digest_closed": (
            package is not None and package.lock_digest == reference_truth_package_digest(package)
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.verify_replay(result).result_digest == result.result_digest,
        "pending_abstains_safely": (
            pending.status is CurationStatus.ABSTAINED
            and pending.package is None
            and pending.abstention_reason is not None
        ),
        "parent_boundary_closed": result.emits_parent is False,
    }
    try:
        service.curate(_denied_request())
    except M2201AuthorizationError:
        checks["controls_fail_closed"] = True
    else:
        checks["controls_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.verify_replay(tampered)
    except M2201ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M22-01",
        "checks": checks,
        "fixture_request_digest": sha256_digest(request),
        "fixture_result_digest": result.result_digest,
        "passed": sum(checks.values()),
        "scenario_count": len(checks),
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
