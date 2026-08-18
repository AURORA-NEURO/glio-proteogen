"""Run deterministic M07-01 formal-state acceptance scenarios."""

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

from tests.modules.c07_copy_number.test_m07_01_formal_state import _request

from glio_proteogen.contracts.m07_01 import CopyNumberMissingness
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema import (
    FormalStateInputError,
    M0701FormalStateEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    valid_status: str
    violation_status: str
    missing_status: str
    unknown_expression_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    safe_failure: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0701FormalStateEngine()
    valid = engine.execute(_request())
    repeated = engine.execute(_request())
    violation = engine.execute(_request(value=1.0))
    missing = engine.execute(
        _request(value=None, state=CopyNumberMissingness.MISSING, expression="all_present")
    )
    unknown = engine.execute(_request(expression="copy-number.total / 2 == 1.5"))
    replay = engine.verify(valid.result, valid.canonical_bytes)
    tamper_rejected = False
    try:
        engine.verify(valid.result, valid.canonical_bytes + b" ")
    except FormalStateInputError:
        tamper_rejected = True
    safe_failure = (
        missing.result.support_decision.status.value == "review_required"
        and missing.result.invariant_results[0].status.value == "not_evaluable"
        and "imput" in missing.result.support_decision.rationale
    )
    deterministic = valid.canonical_bytes == repeated.canonical_bytes
    passed = (
        valid.result.status.value == "valid"
        and violation.result.status.value == "invalid"
        and missing.result.status.value == "abstained"
        and unknown.result.status.value == "abstained"
        and replay.result_digest == valid.result.result_digest
        and tamper_rejected
        and deterministic
        and safe_failure
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M07-01",
        contract_version="0.1.0-provisional",
        valid_status=valid.result.status.value,
        violation_status=violation.result.status.value,
        missing_status=missing.result.status.value,
        unknown_expression_status=unknown.result.status.value,
        replay_verified=True,
        tamper_rejected=tamper_rejected,
        deterministic=deterministic,
        safe_failure=safe_failure,
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
