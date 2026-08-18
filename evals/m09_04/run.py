"""Executable supported/abstention/replay matrix for provisional M09-04."""

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

from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request

from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    M0904ProbabilisticEstimator,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    supported_status: str
    unsupported_status: str
    ood_status: str
    nonconverged_status: str
    estimate_count: int
    diagnostic_count: int
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    uncertainty_explicit: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0904ProbabilisticEstimator()
    supported = engine.build(_request("stable_support"))
    repeat = engine.build(_request("stable_support"))
    unsupported = engine.build(_request("unsupported PTM"))
    ood = engine.build(_request("OOD transport"))
    nonconverged = engine.build(_request("non_converged objective"))
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    uncertainty_explicit = all(
        item.state.value == "estimated"
        for item in (
            supported.result.uncertainty.measurement,
            supported.result.uncertainty.sampling,
            supported.result.uncertainty.parameter,
            supported.result.uncertainty.model_form,
            supported.result.uncertainty.identification,
            supported.result.uncertainty.support,
            supported.result.uncertainty.transport,
        )
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-04",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        ood_status=ood.result.status.value,
        nonconverged_status=nonconverged.result.status.value,
        estimate_count=len(supported.result.estimates),
        diagnostic_count=len(supported.result.diagnostics),
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        uncertainty_explicit=uncertainty_explicit,
        passed=(
            supported.result.status.value == "estimated"
            and unsupported.result.status.value == "abstained"
            and ood.result.status.value == "abstained"
            and nonconverged.result.status.value == "abstained"
            and bool(supported.result.estimates)
            and bool(supported.result.diagnostics)
            and replay.verified
            and not tampered.verified
            and uncertainty_explicit
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
