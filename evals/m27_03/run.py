"""Executable M27-03 evaluator matrix."""

# Support both `python -m evals.m27_03.run` and direct file execution.
# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m27_03 import PipelineStatus
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    M2703Engine,
    M2703Plugin,
)

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.m27_03.fixtures import request
else:
    from .fixtures import request


def run_evaluation() -> dict[str, Any]:
    engine = M2703Engine()
    supported = engine.execute(request())
    rejected = engine.execute(request(support=UpstreamDecisionState.REJECTED))
    replay = engine.verify(supported)
    plugin = M2703Plugin()
    token = plugin.validate(request().model_dump_json())
    plugin_result = plugin.run(token)
    return {
        "supported_executed": supported.status is PipelineStatus.EXECUTED,
        "supported_replay": replay.result_digest == supported.result_digest,
        "rejected_abstained": rejected.status is PipelineStatus.ABSTAINED,
        "rejected_no_package": rejected.result_package is None,
        "plugin_parity": plugin_result.model_dump(mode="json") == supported.model_dump(mode="json"),
        "scenario_count": 5,
    }


def main() -> int:
    report = run_evaluation()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if all(value for key, value in report.items() if key != "scenario_count") else 1


if __name__ == "__main__":
    raise SystemExit(main())
