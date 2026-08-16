"""Executable M26-03 evaluator matrix.

The evaluator exercises the complete deterministic path plus safe failures at
the authorization, media-boundary, strict-input, and replay boundaries.
"""

# The evaluator intentionally uses executable assertions and a console entry
# point; it is an evidence tool rather than library production code.
# ruff: noqa: E501,S101,TRY003,T201,PLR2004

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (
    M2603AuthorizationError,
    M2603Engine,
    M2603EvaluationError,
    M2603ReplayError,
    M2603Service,
)

from .fixture import build_request, denied_request

Scenario = Callable[[], None]


def _nominal() -> None:
    result = M2603Engine().execute(build_request())
    assert result.execution_record is not None
    assert result.reproducible_package is not None
    assert len(result.execution_record.attempts) == 2


def _denied() -> None:
    try:
        M2603Engine().execute(denied_request())
    except M2603AuthorizationError:
        return
    raise AssertionError("denied controls must not execute")


def _deterministic() -> None:
    engine = M2603Engine()
    first = engine.execute(build_request())
    second = engine.execute(build_request())
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def _replay() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    assert engine.verify(result).result_digest == result.result_digest


def _tamper() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    try:
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False)
    except M2603ReplayError:
        return
    raise AssertionError("tampered digest must fail replay")


def _missing_upstream_media() -> None:
    request = build_request()
    source_artifacts = tuple(item for item in request.source_artifacts if "m26-02" not in item.media_type)
    candidate = request.model_dump(mode="json")
    candidate["source_artifacts"] = list(source_artifacts)
    try:
        M2603Service().execute(candidate)
    except (M2603EvaluationError, ValueError):
        return
    raise AssertionError("missing M26-02 media boundary must fail closed")


def _unknown_key() -> None:
    candidate: dict[str, Any] = build_request().model_dump(mode="json")
    candidate["untrusted_payload"] = "must-not-be-accepted"
    try:
        M2603Service().execute(candidate)
    except (M2603EvaluationError, ValueError):
        return
    raise AssertionError("unknown request keys must fail strict parsing")


SCENARIOS: tuple[tuple[str, Scenario], ...] = (
    ("nominal_completed_package", _nominal),
    ("denied_control_abstention", _denied),
    ("deterministic_repeated_execution", _deterministic),
    ("canonical_replay", _replay),
    ("tamper_rejection", _tamper),
    ("missing_m26_02_media_boundary", _missing_upstream_media),
    ("strict_unknown_key_rejection", _unknown_key),
)


def run_evaluator() -> dict[str, object]:
    """Run the locked M26-03 scenario matrix and return audit JSON."""

    outcomes: list[dict[str, object]] = []
    for name, scenario in SCENARIOS:
        scenario()
        outcomes.append({"name": name, "passed": True})
    return {
        "module_id": "GLIO-PROTEOGEN-M26-03",
        "fixture_digest": sha256_digest(build_request()),
        "scenario_count": len(outcomes),
        "passed": len(outcomes),
        "scenarios": outcomes,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()


__all__ = ["SCENARIOS", "main", "run_evaluator"]
