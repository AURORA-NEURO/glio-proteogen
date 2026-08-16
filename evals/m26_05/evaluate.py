"""Executable M26-05 evaluator covering emission, abstention, controls, and replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m26_05 import TelemetryMetricKind
from glio_proteogen.contracts.m26_05.canonical import canonical_request_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605AuthorizationError,
    M2605ObservabilityService,
    M2605ReplayError,
)

from .fixture import make_request

SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m26_05" / "scenarios.json"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:9212-9252"
EXPECTED_CASE_IDS = (
    "complete_emission",
    "canonical_replay",
    "deterministic_digest",
    "missing_signal_abstention",
    "failed_control_rejection",
    "drift_review_alert",
    "tamper_rejection",
)


def evaluate() -> dict[str, Any]:
    """Run deterministic positive, negative, and adversarial telemetry scenarios."""

    service = M2605ObservabilityService()
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M26-05 fixture case IDs are not locked")  # noqa: TRY003
    request = make_request()
    result = service.execute(request)
    scenarios: list[dict[str, object]] = []

    scenarios.append(
        {
            "id": "complete_emission",
            "passed": result.status.value == "emitted" and result.telemetry_stream is not None,
        }
    )
    replay = service.verify(result)
    scenarios.append(
        {
            "id": "canonical_replay",
            "passed": replay.result_digest == result.result_digest,
        }
    )
    second = service.execute(request)
    scenarios.append(
        {"id": "deterministic_digest", "passed": second.result_digest == result.result_digest}
    )
    missing = request.model_copy(
        update={
            "requested_metrics": (*request.requested_metrics, TelemetryMetricKind.REVIEWER_ACTIONS)
        }
    )
    abstained = service.execute(missing)
    scenarios.append(
        {
            "id": "missing_signal_abstention",
            "passed": abstained.status.value == "abstained"
            and abstained.safe_failure_report is not None,
        }
    )
    failed_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"quality": failed_quality}
                    )
                }
            )
        }
    )
    try:
        service.execute(denied)
    except M2605AuthorizationError:
        authorization_passed = True
    else:
        authorization_passed = False
    scenarios.append({"id": "failed_control_rejection", "passed": authorization_passed})
    drifted = request.model_copy(
        update={
            "samples": tuple(
                item.model_copy(update={"value": 0.6})
                if item.metric is TelemetryMetricKind.DRIFT
                else item
                for item in request.samples
            )
        }
    )
    alert = service.execute(drifted).alert
    scenarios.append(
        {"id": "drift_review_alert", "passed": alert is not None and alert.state.value == "open"}
    )
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        service.verify(tampered)
    except M2605ReplayError:
        tamper_passed = True
    else:
        tamper_passed = False
    scenarios.append({"id": "tamper_rejection", "passed": tamper_passed})

    passed = sum(bool(item["passed"]) for item in scenarios)
    return {
        "moduleId": "GLIO-PROTEOGEN-M26-05",
        "contractVersion": "0.1.0-provisional",
        "authoritySha256": AUTHORITY_SHA256,
        "authoritySlice": AUTHORITY_SLICE,
        "fixtureDigest": canonical_request_digest(request),
        "scenarioCount": len(scenarios),
        "fixtureFileDigest": "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest(),
        "caseIds": list(case_ids),
        "passed": passed,
        "total": len(scenarios),
        "allPassed": passed == len(scenarios),
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.write(json.dumps(evaluate(), sort_keys=True, indent=2) + "\n")


__all__ = ["evaluate"]
