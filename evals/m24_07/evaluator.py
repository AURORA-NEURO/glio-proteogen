"""Locked M24-07 scenario matrix."""

from __future__ import annotations

import json
import sys
from typing import Any

from glio_proteogen.contracts.m24_07 import (
    EvaluationStatus,
    OperationalStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_07_human_factors_operational_evaluator as m2407,
)

from .fixture import request


def run_matrix() -> dict[str, Any]:
    service = m2407.M2407Service()
    baseline = request()
    supported = service.evaluate(baseline)
    failed_metric = baseline.metrics[0].model_copy(update={"status": OperationalStatus.FAIL})
    metric_result = service.evaluate(
        baseline.model_copy(update={"metrics": (failed_metric, *baseline.metrics[1:])})
    )
    failed_fallback = baseline.fallbacks[0].model_copy(
        update={"status": OperationalStatus.FAIL, "fallback_available": False}
    )
    fallback_result = service.evaluate(
        baseline.model_copy(update={"fallbacks": (failed_fallback, *baseline.fallbacks[1:])})
    )
    support = baseline.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_context = baseline.context.model_copy(
        update={"references": baseline.context.references.model_copy(update={"support": support})}
    )
    denied = False
    try:
        service.evaluate(baseline.model_copy(update={"context": denied_context}))
    except m2407.M2407AuthorizationError:
        denied = True
    replay = service.verify_replay(supported)
    if supported.report is None or not supported.evidence:
        semantic_replay_rejected = False
    else:
        metric = supported.report.metrics[0].model_copy(update={"observed_value": 0.0})
        forged_report = supported.report.model_copy(
            update={"metrics": (metric, *supported.report.metrics[1:])}
        )
        evidence = supported.evidence[0].model_copy(update={"claim": "forged evidence"})
        forged = supported.model_copy(update={"report": forged_report, "evidence": (evidence,)})
        forged = type(forged).model_construct(
            **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
        )
        try:
            service.verify_replay(forged)
        except m2407.M2407ReplayError:
            semantic_replay_rejected = True
        else:
            semantic_replay_rejected = False
    scenarios = {
        "supported": supported.status is EvaluationStatus.EVALUATED,
        "metric_failure_abstained": metric_result.status is EvaluationStatus.ABSTAINED,
        "fallback_failure_abstained": fallback_result.status is EvaluationStatus.ABSTAINED,
        "denied_control_rejected": denied,
        "replay_verified": replay.result_digest == supported.result_digest,
        "semantic_replay_rejected": semantic_replay_rejected,
        "supported_result_digest": supported.result_digest,
    }
    scenario_ids = [key for key in scenarios if key != "supported_result_digest"]
    return {
        "module": "M24-07",
        "scenario_count": len(scenario_ids),
        "scenario_ids": scenario_ids,
        "scenarios": scenarios,
    }


def main() -> None:
    sys.stdout.write(json.dumps(run_matrix(), sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
