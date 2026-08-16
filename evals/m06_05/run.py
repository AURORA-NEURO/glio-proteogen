"""Executable M06-05 evaluation scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c06_protein_abundance.test_m06_05_constraint_integrator import _request

from glio_proteogen.contracts.m06_01 import FormalStateMissingness
from glio_proteogen.contracts.m06_05 import (
    ConstraintEvaluationOutcome,
    ConstraintIntegrationStatus,
)
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    M0605MechanismConstraintEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    integrated_status: str
    abstained_status: str
    unsupported_status: str
    replay_verified: bool
    ablation_present: bool
    hard_violation_reported: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0605MechanismConstraintEngine()
    first = engine.integrate(_request())
    second = engine.integrate(_request())
    replay = engine.verify(first.result, first.canonical_bytes)
    violated = engine.integrate(_request(expression="protein.abundance >= 2"))
    unsupported = engine.integrate(_request(state=FormalStateMissingness.UNSUPPORTED))
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M06-05",
        contract_version="0.1.0-provisional",
        integrated_status=first.result.status.value,
        abstained_status=violated.result.status.value,
        unsupported_status=unsupported.result.status.value,
        replay_verified=replay.verified,
        ablation_present=bool(first.result.ablations),
        hard_violation_reported=(
            violated.result.evaluations[0].outcome is ConstraintEvaluationOutcome.VIOLATED
        ),
        deterministic=first.canonical_bytes == second.canonical_bytes,
        passed=(
            first.result.status is ConstraintIntegrationStatus.INTEGRATED
            and violated.result.status is ConstraintIntegrationStatus.ABSTAINED
            and unsupported.result.status is ConstraintIntegrationStatus.ABSTAINED
            and replay.verified
            and bool(first.result.ablations)
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
