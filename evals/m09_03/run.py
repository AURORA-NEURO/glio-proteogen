"""Executable M09-03 estimate, safe-failure, and replay matrix."""

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

from tests.modules.c09_complex_activity.test_m09_03_estimator import (
    _request,
    _typed_observations,
)

from glio_proteogen.modules.c09_complex_activity import (
    m09_03_mature_baseline_estimator as m0903,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    estimated_status: str
    unsupported_status: str
    ood_status: str
    missing_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    uncertainty_explicit: bool
    ownership_boundary_closed: bool
    typed_status: str
    typed_model_family: str | None
    typed_replay_verified: bool
    typed_deterministic: bool
    typed_optimization_converged: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = m0903.M0903BaselineEstimator()
    supported = engine.construct(_request())
    repeat = engine.construct(_request())
    unsupported = engine.construct(_request(marker="unsupported"))
    ood = engine.construct(_request(marker="ood"))
    missing = engine.construct(_request(marker="missing"))
    typed_request = _request().model_copy(update={"typed_observations": _typed_observations()})
    typed = engine.construct(typed_request)
    typed_repeat = engine.construct(typed_request)
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    uncertainty_explicit = all(
        getattr(supported.result.uncertainty, dimension).state.value == "estimated"
        for dimension in (
            "measurement",
            "sampling",
            "parameter",
            "model_form",
            "identification",
            "support",
            "transport",
        )
    )
    ownership_boundary_closed = (
        supported.result.parent_target == "complex_activity"
        and supported.result.emits_parent is False
        and supported.result.estimate is not None
        and all(
            marker not in supported.result.estimate.predicted_activity.casefold()
            for marker in ("kinase", "treatment", "therapy", "all_omics", "subtype")
        )
    )
    typed_optimization_converged = bool(
        typed.result.optimization_diagnostics
        and typed.result.optimization_diagnostics[0].status.value == "converged"
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-03",
        contract_version="0.1.0-provisional",
        estimated_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        ood_status=ood.result.status.value,
        missing_status=missing.result.status.value,
        replay_verified=replay,
        tamper_rejected=not tampered,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        uncertainty_explicit=uncertainty_explicit,
        ownership_boundary_closed=ownership_boundary_closed,
        typed_status=typed.result.status.value,
        typed_model_family=(
            typed.result.estimate.model_family
            if typed.result.estimate is not None
            else typed.result.model_family
        ),
        typed_replay_verified=engine.verify(typed.result, typed.canonical_bytes, typed_request),
        typed_deterministic=typed.canonical_bytes == typed_repeat.canonical_bytes,
        typed_optimization_converged=typed_optimization_converged,
        passed=(
            supported.result.status.value == "estimated"
            and unsupported.result.status.value == "abstained"
            and ood.result.status.value == "abstained"
            and missing.result.status.value == "abstained"
            and replay
            and not tampered
            and supported.canonical_bytes == repeat.canonical_bytes
            and uncertainty_explicit
            and ownership_boundary_closed
            and typed.result.status.value == "estimated"
            and typed_optimization_converged
            and engine.verify(typed.result, typed.canonical_bytes, typed_request)
            and typed.canonical_bytes == typed_repeat.canonical_bytes
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
