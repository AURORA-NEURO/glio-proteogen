"""Locked M27-02 executable evaluation matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m27_02 import (
    M2702_M2701_INPUT_MEDIA_TYPE,
    LineageStatus,
    ResolveComplexActivityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702LineageResolver,
    M2702Plugin,
    M2702Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M27-02"
_SCENARIOS = Path(__file__).with_name("scenarios.json")


class EvaluationFixtureError(RuntimeError):
    """The locked M27-02 fixture is malformed or incomplete."""


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2702.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2702": label}),
        media_type=media_type,
    )


def _decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2702.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"control.{role}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m2702.evaluator",
        actor_id="actor.m2702.evaluator",
        occurred_at=datetime(2026, 8, 16, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2702.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "evaluator"}),
                evidence=_artifact("control.identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.m2702.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended_use"),
        ),
    )


def build_request(*, duplicate_source: bool = False) -> ResolveComplexActivityLineageRequest:
    upstream = _artifact("upstream", M2702_M2701_INPUT_MEDIA_TYPE)
    secondary = _artifact("secondary")
    source_artifacts = (
        (upstream, secondary, upstream) if duplicate_source else (upstream, secondary)
    )
    return ResolveComplexActivityLineageRequest(
        request_id="request.m2702.evaluator",
        context=_context(),
        upstream_result=upstream,
        root_object_id="activity.m2702.evaluator.root",
        source_artifacts=source_artifacts,
    )


def _load_scenarios() -> tuple[dict[str, object], ...]:
    payload = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise EvaluationFixtureError
    return tuple(payload)


def run_evaluation(output: Path | None = None) -> dict[str, object]:
    scenarios = _load_scenarios()
    resolver = M2702LineageResolver()
    plugin = M2702Plugin(M2702Service())
    scenario_results: list[dict[str, object]] = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        request = build_request(duplicate_source=bool(scenario["duplicate_source"]))
        result = resolver.resolve(request)
        replay = resolver.resolve(request)
        if result != replay:
            raise EvaluationFixtureError
        expected_status = LineageStatus(str(scenario["expected_status"]))
        if result.status is not expected_status:
            raise EvaluationFixtureError
        expected_finding_count = cast("int", scenario["expected_finding_count"])
        if len(result.findings) != expected_finding_count:
            raise EvaluationFixtureError
        if result.status is LineageStatus.RESOLVED:
            token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))
            if plugin.run(token) != result:
                raise EvaluationFixtureError
            if (
                result.lineage_graph is None
                or not result.lineage_graph.reproducibility_bundle.manifest_digest
            ):
                raise EvaluationFixtureError
        scenario_results.append(
            {
                "scenario_id": scenario_id,
                "status": result.status.value,
                "finding_count": len(result.findings),
                "replay_equal": True,
                "plugin_equal": result.status is LineageStatus.RESOLVED,
            }
        )
    adversarial = {
        "duplicate_source_abstains": scenario_results[1]["status"] == "abstained",
        "resolved_has_no_parent_claim": not bool(resolver.resolve(build_request()).emits_parent),
        "resolved_has_no_biological_claim": all(
            value is False for value in [resolver.resolve(build_request()).emits_parent]
        ),
        "result_digest_replayed": resolver.resolve(build_request()).result_digest
        == resolver.resolve(build_request()).result_digest,
    }
    passed = len(scenario_results) == len(scenarios) and all(
        bool(item["replay_equal"]) for item in scenario_results
    )
    fixture_digest = hashlib.sha256(_SCENARIOS.read_bytes()).hexdigest()
    report: dict[str, object] = {
        "module_id": MODULE_ID,
        "fixture_sha256": fixture_digest,
        "scenario_count": len(scenario_results),
        "scenarios": scenario_results,
        "adversarial": adversarial,
        "adversarial_count": len(adversarial),
        "passed": passed and all(adversarial.values()),
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run_evaluation(arguments.output)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
