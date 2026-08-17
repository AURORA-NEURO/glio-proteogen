"""Executable hard/soft/support/replay matrix for provisional M08-05."""

# ruff: noqa: E501

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

from tests.modules.c08_transcript_protein_discordance.test_m08_05_integrator import _request

from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805ConstraintIntegrator,
)


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
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0805ConstraintIntegrator()
    supported = engine.integrate(_request("conservation_hold"))
    repeat = engine.integrate(_request("conservation_hold"))
    hard = engine.integrate(_request("force_violation"))
    soft = engine.integrate(_request("soft force_violation"))
    unsupported = engine.integrate(_request("unsupported ontology"))
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M08-05",
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
        passed=(
            supported.result.status.value == "estimated"
            and hard.result.status.value == "abstained"
            and soft.result.status.value == "estimated"
            and unsupported.result.status.value == "abstained"
            and bool(supported.result.estimates)
            and bool(supported.result.satisfaction_report)
            and replay.verified
            and not tampered.verified
            and supported.canonical_bytes == repeat.canonical_bytes
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
