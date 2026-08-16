"""Executable M25-04 external transport evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m25_04 import (
    M2504_DOSSIER_SHA256,
    M2504_DOSSIER_SLICE,
    EvaluationStatus,
    TransportDimension,
    TransportStatus,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504AuthorizationError,
    M2504Plugin,
    M2504ReplayError,
    M2504Service,
    TransportSubmission,
)

from .fixture import build_request, denied_request, not_evaluable_request

EXPECTED_CONTROL_COUNT = 7


def run_evaluator() -> dict[str, Any]:
    service = M2504Service()
    request = build_request()
    supported = service.execute(request)
    repeated = service.execute(request)
    narrowed = service.execute(build_request(status=TransportStatus.DOMAIN_NARROWED))
    abstained = service.execute(not_evaluable_request())
    checks: dict[str, bool] = {
        "supported_report": (
            supported.status is EvaluationStatus.EVALUATED and supported.report is not None
        ),
        "all_seven_dimensions": (
            supported.report is not None
            and {item.dimension for item in supported.report.evaluations} == set(TransportDimension)
        ),
        "narrowed_support_visible": (
            narrowed.report is not None
            and narrowed.report.support_domain.status is TransportStatus.DOMAIN_NARROWED
            and narrowed.support_decision.status.value == "limited"
        ),
        "not_evaluable_abstention": (
            abstained.status is EvaluationStatus.ABSTAINED
            and abstained.report is None
            and abstained.support_decision.status.value == "review_required"
        ),
        "deterministic_repeat": supported.result_digest == repeated.result_digest,
        "replay_supported": (
            service.verify_replay(supported).result_digest == supported.result_digest
        ),
        "replay_abstained": (
            service.verify_replay(abstained).result_digest == abstained.result_digest
        ),
        "parent_boundary": supported.parent_target == "proteotype" and not supported.emits_parent,
        "provenance_controls": (
            len(supported.provenance.control_decisions) == EXPECTED_CONTROL_COUNT
        ),
    }
    try:
        service.execute(denied_request())
    except M2504AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    plugin = M2504Plugin(service)
    token = plugin.validate(TransportSubmission(canonical_json_bytes(request)))
    checks["plugin_parity"] = plugin.run(token) == supported
    tampered = supported.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.verify_replay(tampered)
    except (M2504ReplayError, ValueError):
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "adversarial_case_count": len(checks),
        "adversarial_passed_count": sum(checks.values()),
        "checks": checks,
        "dossier_sha256": M2504_DOSSIER_SHA256,
        "dossier_slice": M2504_DOSSIER_SLICE,
        "fixture_digest": sha256_digest(request),
        "fixture_result_digest": supported.result_digest,
        "module_id": "GLIO-PROTEOGEN-M25-04",
        "parent_target": "proteotype",
        "passed": all(checks.values()),
        "scenario_count": len(checks),
        "upstream_dependency": "M25-02 and M25-03 caller-declared media only",
    }


def main() -> int:
    report = run_evaluator()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
