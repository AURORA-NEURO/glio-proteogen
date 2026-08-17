"""Executable evaluator and adversarial evidence for M18-08."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m18_08_monitoring import _request

from glio_proteogen.contracts.m18_08 import (
    MonitorBiomarkerPanelTranslationHealthRequest,
    ObservationStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c18_spatial_proteomics import (
    m18_08_translation_monitoring_service as m1808,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m18_08" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M18-08"
EXPECTED_SCENARIOS: Final = 8
EXPECTED_ADVERSARIAL_CASES: Final = 8


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    scenario_count: int
    adversarial_case_count: int
    adversarial_passed_count: int
    adversarial_coverage_percent: float
    target_percent: int
    checks: tuple[EvalCheck, ...]
    passed: bool


def _consent_denied_request() -> MonitorBiomarkerPanelTranslationHealthRequest:
    request = _request()
    context = request.context
    references = context.references.model_copy(
        update={
            "consent": context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    return request.model_copy(
        update={"context": context.model_copy(update={"references": references})}
    )


def _scenario(name: str) -> MonitorBiomarkerPanelTranslationHealthRequest:  # noqa: PLR0911
    if name == "healthy":
        return _request()
    if name == "degraded":
        return _request(telemetry_status=ObservationStatus.WARNING)
    if name == "rollback_required":
        return _request(telemetry_status=ObservationStatus.FAIL, threshold=1)
    if name == "suspended_discrepancy":
        return _request(discrepancy_resolved=False)
    if name == "not_evaluable_abstention":
        return _request(telemetry_status=ObservationStatus.NOT_EVALUABLE)
    if name == "control_denied":
        return _consent_denied_request()
    if name == "upstream_media_rejected":
        return _request(upstream_media_type="application/json")
    if name == "replay_tamper":
        return _request()
    raise ValueError(f"unknown M18-08 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = m1808.M1808TranslationMonitoringEngine()
    scenario_oracles_passed = True
    for name in names:
        try:
            result = engine.adapt(_scenario(name))
        except (m1808.M1808AuthorizationError, ValidationError):
            scenario_oracles_passed &= name in {"control_denied", "upstream_media_rejected"}
        else:
            scenario_oracles_passed &= (
                name not in {"control_denied", "upstream_media_rejected"}
                and result.parent_target == "biomarker panel"
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )

    healthy = engine.adapt(_scenario("healthy"))
    checks.extend(
        (
            EvalCheck(
                "healthy.bounded_state",
                healthy.status.value == "monitored"
                and healthy.health_report is not None
                and healthy.emits_parent is False,
                "healthy input emits only a bounded translation-health report",
            ),
            EvalCheck(
                "healthy.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        healthy.uncertainty.measurement,
                        healthy.uncertainty.sampling,
                        healthy.uncertainty.parameter,
                        healthy.uncertainty.model_form,
                        healthy.uncertainty.identification,
                        healthy.uncertainty.support,
                        healthy.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    rollback = engine.adapt(_scenario("rollback_required"))
    checks.append(
        EvalCheck(
            "rollback.critical_drift",
            rollback.health_report is not None
            and rollback.health_report.rollback_decision.value == "rollback"
            and rollback.human_review_required,
            "critical drift produces an auditable rollback decision",
        )
    )
    tampered = engine.adapt(_scenario("replay_tamper")).model_copy(
        update={"human_review_required": True}
    )
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1808.M1808ReplayVerificationError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    for request, expected_state in (
        (_request(telemetry_status=ObservationStatus.FAIL, threshold=1), "rollback_required"),
        (_request(support_status=ObservationStatus.FAIL, threshold=1), "rollback_required"),
        (_request(workflow_status=ObservationStatus.FAIL, threshold=1), "rollback_required"),
        (_request(discrepancy_resolved=False), "suspended"),
        (_request(telemetry_status=ObservationStatus.NOT_EVALUABLE), "abstained"),
    ):
        result = engine.adapt(request)
        observed = (
            result.status.value
            if result.status.value == "abstained"
            else result.health_report.health_state.value
            if result.health_report is not None
            else "missing"
        )
        adversarial_passed += int(observed == expected_state)
    try:
        engine.adapt(_consent_denied_request())
    except m1808.M1808AuthorizationError:
        adversarial_passed += 1
    try:
        engine.adapt(_scenario("upstream_media_rejected"))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except m1808.M1808ReplayVerificationError:
        adversarial_passed += 1
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={adversarial_passed}/{EXPECTED_ADVERSARIAL_CASES}",
        )
    )
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=metadata["dossier_sha256"],
        dossier_slice=metadata["dossier_slice"],
        scenario_count=len(names),
        adversarial_case_count=EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed_count=adversarial_passed,
        adversarial_coverage_percent=adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100,
        target_percent=metadata["coverage_target_percent"],
        checks=tuple(checks),
        passed=all(check.passed for check in checks),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rendered = json.dumps(asdict(evaluate()), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if json.loads(rendered)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
