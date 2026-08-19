"""Locked M24-02 generation and replay scenario matrix."""

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m24_02 import result_payload_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_generator as m2402,
)

from .fixture import request

_CASE_COUNT = 5


def run_matrix() -> dict[str, Any]:
    service = m2402.M2402Service()
    baseline = request()
    supported = service.evaluate(baseline)
    replay = service.verify_replay(supported)
    changed = supported.corpus.cases[0].model_copy(update={"truth_values": ("9.999999",)})  # type: ignore[union-attr]
    forged_corpus = supported.corpus.model_copy(
        update={"cases": (changed, *supported.corpus.cases[1:])}  # type: ignore[union-attr]
    )
    forged = supported.model_copy(update={"corpus": forged_corpus})
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )
    tamper_rejected = False
    try:
        service.verify_replay(forged)
    except m2402.M2402ReplayError:
        tamper_rejected = True
    support = baseline.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = baseline.model_copy(
        update={
            "context": baseline.context.model_copy(
                update={
                    "references": baseline.context.references.model_copy(
                        update={"support": support}
                    )
                }
            )
        }
    )
    denied_rejected = False
    try:
        service.evaluate(denied)
    except m2402.AuthorizationError:
        denied_rejected = True
    scenarios = {
        "generated": supported.status.value == "generated",
        "five_cases": supported.corpus is not None and len(supported.corpus.cases) == _CASE_COUNT,
        "replay_verified": replay.result_digest == supported.result_digest,
        "self_rehashed_tamper_rejected": tamper_rejected,
        "denied_control_rejected": denied_rejected,
    }
    return {
        "module": "M24-02",
        "scenario_count": len(scenarios),
        "scenario_ids": list(scenarios),
        "scenarios": scenarios,
        "passed": all(scenarios.values()),
        "supported_result_digest": supported.result_digest,
    }
