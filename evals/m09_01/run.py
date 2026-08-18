"""Executable valid/invalid/abstention/replay matrix for provisional M09-01."""

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

from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import _request

from glio_proteogen.contracts.m09_01 import ComplexActivityMissingness
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    M0901FormalStateEngine,
    M0901Service,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    valid_status: str
    invalid_status: str
    missing_status: str
    unknown_expression_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    invariant_count: int
    passed: bool


def evaluate() -> EvaluationReport:
    service = M0901Service()
    valid = service.execute(_request())
    repeat = service.execute(_request())
    invalid = service.execute(_request(value=0.1))
    missing = service.execute(_request(value=None, state=ComplexActivityMissingness.MISSING))
    unknown = service.execute(_request(expression="unsupported:complex.activity"))
    replay = M0901FormalStateEngine.verify(valid.result, valid.canonical_bytes)
    tampered = M0901FormalStateEngine.verify(valid.result, valid.canonical_bytes + b" ")
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-01",
        contract_version="0.1.0-provisional",
        valid_status=valid.result.status.value,
        invalid_status=invalid.result.status.value,
        missing_status=missing.result.status.value,
        unknown_expression_status=unknown.result.status.value,
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=valid.canonical_bytes == repeat.canonical_bytes,
        invariant_count=len(valid.result.invariant_results),
        passed=(
            valid.result.status.value == "valid"
            and invalid.result.status.value == "invalid"
            and missing.result.status.value == "abstained"
            and unknown.result.status.value == "abstained"
            and bool(valid.result.invariant_results)
            and replay.verified
            and not tampered.verified
            and valid.canonical_bytes == repeat.canonical_bytes
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
