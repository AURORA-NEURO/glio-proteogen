"""Executable hard/soft/support/replay matrix for provisional M09-05."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.modules.c09_complex_activity.test_m09_05_integrator import _request

from glio_proteogen.contracts.m09_05 import (
    ConstraintEvidenceObservation,
    ConstraintObservationState,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905ConstraintIntegrator,
)

_MEASURED_VALUE = 0.7
_MEASURED_STANDARD_ERROR = 0.1
_CENSORING_LIMIT = 0.4


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    supported_status: str
    hard_violation_status: str
    soft_conflict_status: str
    unsupported_status: str
    estimate_count: int
    report_count: int
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    soft_ablation_visible: bool
    measured_status: str
    measured_value_used: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0905ConstraintIntegrator()
    supported = engine.integrate(_request("conservation_hold"))
    repeat = engine.integrate(_request("conservation_hold"))
    hard = engine.integrate(_request("force_violation"))
    soft = engine.integrate(_request("soft force_violation"))
    unsupported = engine.integrate(_request("unsupported ontology"))
    measured = engine.integrate(
        _request("conservation_hold").model_copy(
            update={
                "observations": (
                    ConstraintEvidenceObservation(
                        feature_id="feature.1",
                        value=_MEASURED_VALUE,
                        standard_error=_MEASURED_STANDARD_ERROR,
                    ),
                    ConstraintEvidenceObservation(
                        feature_id="feature.2",
                        state=ConstraintObservationState.LEFT_CENSORED,
                        standard_error=_MEASURED_STANDARD_ERROR,
                        censoring_limit=_CENSORING_LIMIT,
                    ),
                )
            }
        )
    )
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    soft_report = soft.result.satisfaction_report[0]
    passed = (
        supported.result.status.value == "estimated"
        and hard.result.status.value == "abstained"
        and soft.result.status.value == "estimated"
        and unsupported.result.status.value == "abstained"
        and bool(supported.result.estimates)
        and bool(supported.result.satisfaction_report)
        and replay.verified
        and not tampered.verified
        and supported.canonical_bytes == repeat.canonical_bytes
        and soft_report.ablation_effect is not None
        and measured.result.status.value == "estimated"
        and measured.result.estimates[0].estimate_value == _MEASURED_VALUE
        and measured.result.estimates[1].upper_bound == _CENSORING_LIMIT
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-05",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        hard_violation_status=hard.result.status.value,
        soft_conflict_status=soft.result.status.value,
        unsupported_status=unsupported.result.status.value,
        estimate_count=len(supported.result.estimates),
        report_count=len(supported.result.satisfaction_report),
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        soft_ablation_visible=soft_report.ablation_effect is not None,
        measured_status=measured.result.status.value,
        measured_value_used=(
            bool(measured.result.estimates)
            and measured.result.estimates[0].estimate_value == _MEASURED_VALUE
        ),
        passed=passed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EvaluationReport", "evaluate", "main"]
