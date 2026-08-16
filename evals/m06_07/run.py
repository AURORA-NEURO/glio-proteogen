"""Executable M06-07 evaluation scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c06_protein_abundance.test_m06_07_calibration import _request

from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    M0607CalibrationEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    calibrated_status: str
    upstream_abstained_status: str
    coverage_abstained_status: str
    selected_estimate: bool
    prediction_set_present: bool
    replay_verified: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0607CalibrationEngine()
    first = engine.calibrate(_request())
    second = engine.calibrate(_request())
    upstream_abstained = engine.calibrate(_request(upstream_decomposed=False))
    coverage_abstained = engine.calibrate(_request(calibration_error=0.5))
    replay = engine.verify(first.result, first.canonical_bytes)
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M06-07",
        contract_version="0.1.0-provisional",
        calibrated_status=first.result.status.value,
        upstream_abstained_status=upstream_abstained.result.status.value,
        coverage_abstained_status=coverage_abstained.result.status.value,
        selected_estimate=bool(first.result.estimates)
        and first.result.estimates[0].selection_status.value == "selected",
        prediction_set_present=bool(first.result.prediction_sets),
        replay_verified=replay.verified,
        deterministic=first.canonical_bytes == second.canonical_bytes,
        passed=(
            first.result.status.value == "calibrated"
            and upstream_abstained.result.status.value == "abstained"
            and coverage_abstained.result.status.value == "abstained"
            and bool(first.result.estimates)
            and bool(first.result.prediction_sets)
            and replay.verified
            and first.canonical_bytes == second.canonical_bytes
        ),
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
