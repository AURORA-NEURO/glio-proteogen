"""Executable M25-01 evaluator matrix."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

from glio_proteogen.contracts.m25_01 import CurationStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    M2501AuthorizationError,
    M2501Plugin,
    M2501ReferenceTruthBenchmarkCurator,
    M2501Service,
    ReferenceTruthSubmission,
)

from .fixture import (
    build_request,
    denied_request,
    pending_request,
    rejected_included_request,
)


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    passed: bool
    detail: str


def run_evaluator() -> dict[str, Any]:
    engine = M2501ReferenceTruthBenchmarkCurator()
    service = M2501Service(engine)
    scenarios: list[ScenarioResult] = []

    curated = engine.curate(build_request())
    scenarios.append(
        ScenarioResult(
            "locked_package",
            curated.status is CurationStatus.CURATED and curated.package is not None,
            "supported request produces a locked package",
        )
    )
    scenarios.append(
        ScenarioResult(
            "parent_ceiling",
            curated.parent_target == "proteotype" and curated.emits_parent is False,
            "result remains below the proteotype parent output ceiling",
        )
    )
    pending = engine.curate(pending_request())
    scenarios.append(
        ScenarioResult(
            "pending_abstention",
            pending.status is CurationStatus.ABSTAINED and pending.package is None,
            "pending adjudication is withheld",
        )
    )
    rejected = engine.curate(rejected_included_request())
    scenarios.append(
        ScenarioResult(
            "rejected_included_abstention",
            rejected.status is CurationStatus.ABSTAINED and rejected.package is None,
            "rejected included material cannot be locked",
        )
    )
    try:
        engine.curate(denied_request())
    except M2501AuthorizationError:
        denied = True
    else:
        denied = False
    scenarios.append(
        ScenarioResult("control_denial", denied, "denied support fails before traversal")
    )
    replayed = engine.verify_replay(curated)
    scenarios.append(
        ScenarioResult(
            "replay",
            replayed.result_digest == curated.result_digest,
            "canonical result and package lock replay exactly",
        )
    )
    repeated = engine.curate(build_request())
    scenarios.append(
        ScenarioResult(
            "determinism",
            repeated == curated,
            "same request produces byte-equivalent result",
        )
    )
    plugin = M2501Plugin(service)
    token = plugin.validate(ReferenceTruthSubmission(canonical_json_bytes(build_request())))
    plugin_result = plugin.run(token)
    scenarios.append(
        ScenarioResult(
            "plugin_parity",
            plugin_result == curated,
            "strict plugin path matches service result",
        )
    )
    passed = all(scenario.passed for scenario in scenarios)
    return {
        "module_id": "GLIO-PROTEOGEN-M25-01",
        "scenario_count": len(scenarios),
        "passed_count": sum(scenario.passed for scenario in scenarios),
        "passed": passed,
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "fixture_request_digest": str(curated.request_digest),
        "fixture_result_digest": str(curated.result_digest),
    }


def main() -> int:
    report = run_evaluator()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
