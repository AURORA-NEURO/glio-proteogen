"""Executable evaluator for the M20-02 alignment matrix."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m20_02.fixture import build_synthetic_request
from glio_proteogen.contracts.m20_02 import (
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteinSubtypeSourcesRequest,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002Engine,
)

RequestFactory = Callable[..., AlignProteinSubtypeSourcesRequest]


def run_evaluation(
    factory: RequestFactory = build_synthetic_request,
) -> dict[str, object]:
    """Run the locked supported/conflict/not-evaluable scenario matrix."""

    engine = M2002Engine()
    scenarios = (
        ("aligned", factory()),
        ("conflicted", factory(status=AlignmentObservationStatus.CONFLICTED)),
        ("not_evaluable", factory(status=AlignmentObservationStatus.NOT_EVALUABLE)),
    )
    records: list[dict[str, object]] = []
    for label, request in scenarios:
        result = engine.resolve(request)
        expected = AlignmentStatus.ALIGNED if label == "aligned" else AlignmentStatus.ABSTAINED
        passed = result.status is expected and (
            (label == "aligned" and result.aligned_bundle is not None)
            or (label != "aligned" and result.aligned_bundle is None)
        )
        records.append(
            {
                "scenario": label,
                "passed": passed,
                "status": result.status.value,
                "result_digest": result.result_digest,
                "finding_count": len(result.findings),
                "replay_verified": engine.replay(result) == result,
            }
        )
    passed_count = sum(bool(record["passed"]) for record in records)
    replay_count = sum(bool(record["replay_verified"]) for record in records)
    return {
        "module": "GLIO-PROTEOGEN-M20-02",
        "scenario_count": len(records),
        "passed_count": passed_count,
        "replay_count": replay_count,
        "passed": passed_count == len(records) and replay_count == len(records),
        "scenarios": records,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the self-contained evaluator and optionally write its JSON report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_evaluation"]
