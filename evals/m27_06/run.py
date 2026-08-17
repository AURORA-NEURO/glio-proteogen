"""Run the locked M27-06 security/access evaluator matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glio_proteogen.contracts.m27_06 import SecurityAssessmentStatus
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import (
    M2706Plugin,
    M2706ReplayError,
    M2706Service,
    SecuritySubmission,
    evaluate_complex_activity_security_access,
)

if __package__:
    from .fixture import build_request
else:
    from evals.m27_06.fixture import build_request

_FIXTURE_DIGEST = "sha256:d2c363d30f8ea21b745f5e2f7e1597c1ae3489156eeb00469840538d3c0f3585"


def run() -> dict[str, object]:
    supported = evaluate_complex_activity_security_access(build_request())
    denied = evaluate_complex_activity_security_access(build_request(action="deny-read"))
    missing = evaluate_complex_activity_security_access(build_request(with_consent=False))
    unsupported = evaluate_complex_activity_security_access(
        build_request(upstream_media_type="application/json")
    )
    service = M2706Service()
    plugin = M2706Plugin()
    token = plugin.validate(SecuritySubmission(build_request()))
    plugin_result = plugin.run(token)
    replay = service.replay(supported)
    forged = supported.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    tamper_rejected = False
    try:
        service.replay(forged)
    except (M2706ReplayError, ValueError):
        tamper_rejected = True
    checks = {
        "supported_evaluated": supported.status is SecurityAssessmentStatus.EVALUATED,
        "supported_allow": supported.access_decision is not None
        and supported.access_decision.state.value == "allow",
        "denied_critical": denied.access_decision is not None
        and denied.access_decision.state.value == "deny"
        and denied.security_posture is not None
        and denied.security_posture.status.value == "critical",
        "missing_consent_abstained": missing.status is SecurityAssessmentStatus.ABSTAINED,
        "unsupported_abstained": unsupported.status is SecurityAssessmentStatus.ABSTAINED,
        "plugin_parity": plugin_result == supported,
        "replay": replay == supported,
        "tamper_rejected": tamper_rejected,
    }
    return {
        "module_id": "GLIO-PROTEOGEN-M27-06",
        "checks": checks,
        "checks_declared": len(checks),
        "checks_passed": sum(checks.values()),
        "fixture_digest": _FIXTURE_DIGEST,
        "passed": all(checks.values()),
    }


def main() -> int:
    report = run()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
