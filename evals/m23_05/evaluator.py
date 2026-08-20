"""Executable M23-05 evaluator matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

if __package__ in {None, ""}:  # pragma: no cover - direct script invocation.
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m23_05 import (
    SubgroupDimension,
    VariantPeptideSubgroupEvaluationResult,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    M2305AuthorizationError,
    M2305ReplayError,
    M2305Service,
)

if __package__ in {None, ""}:  # pragma: no cover - direct script invocation.
    from evals.m23_05.fixture import (
        build_request,
        denied_request,
        restricted_request,
        unsupported_request,
    )
else:
    from .fixture import build_request, denied_request, restricted_request, unsupported_request

_CONTROL_COUNT = 7


def run_evaluator() -> dict[str, Any]:
    service = M2305Service()
    request = build_request()
    result = service.evaluate(request)
    repeated = service.evaluate(request)
    abstained = service.evaluate(unsupported_request())
    restricted = service.evaluate(restricted_request())
    checks: dict[str, bool] = {
        "evaluated": result.status.value == "evaluated",
        "report_present": result.report is not None,
        "all_required_dimensions": (
            result.report is not None
            and set(result.report.configuration.required_dimensions) == set(SubgroupDimension)
            and len(result.report.performance) == len(SubgroupDimension)
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "explicit_abstention": abstained.status.value == "abstained"
        and abstained.report is None
        and abstained.human_review_required,
        "restricted_abstention": restricted.status.value == "abstained"
        and restricted.report is None
        and restricted.human_review_required,
        "seven_control_provenance": len(result.provenance.control_decisions) == _CONTROL_COUNT,
        "parent_boundary": result.emits_parent is False
        and result.parent_target == "variant peptide",
    }
    try:
        service.evaluate(denied_request())
    except M2305AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.replay(tampered)
    except M2305ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    if result.report is None:
        checks["semantic_replay_rejects_self_rehash"] = False
    else:
        performance = result.report.performance[0].model_copy(update={"value": 0.71})
        forged_report = result.report.model_copy(
            update={"performance": (performance, *result.report.performance[1:])}
        )
        forged = result.model_copy(update={"report": forged_report})
        try:
            forged = VariantPeptideSubgroupEvaluationResult.model_validate_json(
                canonical_json_bytes(
                    forged.model_copy(update={"result_digest": result_payload_digest(forged)})
                ),
                strict=True,
            )
        except ValidationError:
            checks["semantic_replay_rejects_self_rehash"] = True
        else:
            try:
                service.replay(forged)
            except M2305ReplayError:
                checks["semantic_replay_rejects_self_rehash"] = True
            else:
                checks["semantic_replay_rejects_self_rehash"] = False
    return {
        "module": "M23-05",
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
