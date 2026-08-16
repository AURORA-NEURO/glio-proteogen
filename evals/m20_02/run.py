"""Executable evaluator for the M20-02 alignment matrix."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.contracts.m20_02 import (
    AlignmentObservationStatus,
    AlignmentStatus,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002Engine,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def run_evaluation(factory: Callable[..., Any]) -> dict[str, object]:
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
    return {
        "module": "GLIO-PROTEOGEN-M20-02",
        "scenario_count": len(records),
        "passed_count": sum(bool(record["passed"]) for record in records),
        "replay_count": sum(bool(record["replay_verified"]) for record in records),
        "scenarios": records,
    }


__all__ = ["run_evaluation"]
