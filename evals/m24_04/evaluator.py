"""Locked M24-04 transport scenario matrix."""

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m24_04 import EvaluationStatus, TransportStatus
from glio_proteogen.modules.c21_reference_material import (
    m24_04_external_transport_evaluator as m2404,
)

from .fixture import request

_DIMENSION_COUNT = 7


def run_matrix() -> dict[str, Any]:
    service = m2404.M2404Service()
    baseline = request()
    supported = service.evaluate(baseline)
    replay = service.verify_replay(supported)
    narrowed = baseline.evaluations[0].model_copy(
        update={
            "status": TransportStatus.DOMAIN_NARROWED,
            "metric_value": 0.5,
            "rationale": "Calibration floor failed; domain narrowed.",
        }
    )
    narrowed_result = service.evaluate(
        baseline.model_copy(update={"evaluations": (narrowed, *baseline.evaluations[1:])})
    )
    scenarios = {
        "supported": supported.status is EvaluationStatus.EVALUATED,
        "seven_dimensions": supported.report is not None
        and len(supported.report.evaluations) == _DIMENSION_COUNT,
        "replay_verified": replay.result_digest == supported.result_digest,
        "domain_narrowing_abstained": narrowed_result.status is EvaluationStatus.ABSTAINED,
        "no_report_on_narrowing": narrowed_result.report is None,
    }
    return {
        "module": "M24-04",
        "scenario_count": len(scenarios),
        "scenario_ids": list(scenarios),
        "scenarios": scenarios,
        "passed": all(scenarios.values()),
        "supported_result_digest": supported.result_digest,
    }
