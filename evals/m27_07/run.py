"""Run the locked M27-07 change-control evaluator matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glio_proteogen.contracts.m27_07 import ChangeControlStatus
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import (
    ChangeControlSubmission,
    M2707Plugin,
    M2707Service,
)

if __package__:
    from .fixture import build_request
else:
    from evals.m27_07.fixture import build_request

_FIXTURE_DIGEST = "sha256:b3c941e8f9e98a63a78f3a4d2ed827822e2a75e61a69b1123e3631186b193bcf"


def run() -> dict[str, object]:
    service = M2707Service()
    approved = service.execute(build_request())
    abstained = service.execute(build_request(challenger_regression=True))
    plugin = M2707Plugin()
    token = plugin.validate(ChangeControlSubmission(build_request("m2707.request.plugin")))
    plugin_result = plugin.run(token)
    replay = service.replay(approved)
    forged = approved.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    tamper_rejected = not service.verify(forged)
    checks = {
        "approved": approved.status is ChangeControlStatus.APPROVED,
        "package_present": approved.approved_change_package is not None,
        "rollback_bound": approved.approved_change_package is not None
        and approved.approved_change_package.rollback_point.tested,
        "regression_abstained": abstained.status is ChangeControlStatus.ABSTAINED,
        "regression_review": abstained.human_review_required,
        "plugin_parity": plugin_result.status is ChangeControlStatus.APPROVED,
        "replay": replay == approved,
        "tamper_rejected": tamper_rejected,
    }
    return {
        "module_id": "GLIO-PROTEOGEN-M27-07",
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
