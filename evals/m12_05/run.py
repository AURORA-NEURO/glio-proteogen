"""Run the locked, deterministic M12-05 evaluation matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003, PLR2004

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m12_05 import (
    M1205_M1204_RESULT_MEDIA_TYPE,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelBiomarkerPanelLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    TrajectoryStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_05_longitudinal_evolution import (
    M1205AuthorizationError,
    M1205LongitudinalEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-05"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m12_05" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "stable_trajectory",
    "alternating_trajectory",
    "change_point",
    "unknown_objective_abstention",
    "out_of_support_change_point",
    "replay_and_tamper",
    "authorization_gate",
)
_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1205-eval": label}),
        media_type=media_type,
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def build_scenario_request(
    objective: str = "stable", *, accepted: bool = True
) -> ModelBiomarkerPanelLongitudinalEvolutionRequest:
    observations = tuple(
        TimePointObservation(
            observation_id=f"observation.{index}",
            sequence=index,
            observed_at=_WHEN + timedelta(days=index),
            territory="core" if index < 2 else "rim",
            treatment_era="pre" if index < 2 else "post",
            feature_artifact=_artifact(f"feature.{index}"),
            evidence=(
                EvidenceReference(
                    reference=_artifact(f"observation-evidence.{index}"),
                    role="evidence",
                    claim="Locked evaluator observation.",
                ),
            ),
        )
        for index in range(3)
    )
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration.m1205",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective=objective,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration-evidence"),
                role="evidence",
                claim="Locked evaluator configuration.",
            ),
        ),
    )
    return ModelBiomarkerPanelLongitudinalEvolutionRequest(
        request_id="request.m1205",
        context=ExecutionContext(
            request_id="request.m1205",
            actor_id="actor.evaluator",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        network_state_result=_artifact("m1204-result", M1205_M1204_RESULT_MEDIA_TYPE),
        policy=TrajectoryPolicy(
            dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.STATE_TRANSITION),
            minimum_observations=2,
            configuration=configuration,
        ),
        observations=observations,
        source_artifacts=(_artifact("source"),),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M12-05 fixture case IDs are not locked")
    engine = M1205LongitudinalEngine()
    checks: list[EvalCheck] = []
    stable = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "stable_trajectory",
            stable.status is TrajectoryStatus.MODELED and len(stable.trajectory) == 3,
            stable.status.value,
        )
    )
    alternating = engine.infer(build_scenario_request("alternating"))
    checks.append(
        EvalCheck(
            "alternating_trajectory",
            alternating.status is TrajectoryStatus.MODELED
            and alternating.trajectory[0].label != alternating.trajectory[1].label,
            alternating.status.value,
        )
    )
    change = engine.infer(build_scenario_request("change_point:2:before:after"))
    checks.append(
        EvalCheck(
            "change_point",
            change.status is TrajectoryStatus.MODELED and len(change.change_points) == 1,
            change.status.value,
        )
    )
    unknown = engine.infer(build_scenario_request("unknown:model"))
    checks.append(
        EvalCheck(
            "unknown_objective_abstention",
            unknown.status is TrajectoryStatus.NOT_EVALUABLE
            and unknown.human_review_required
            and not unknown.trajectory,
            unknown.status.value,
        )
    )
    outside = engine.infer(build_scenario_request("change_point:99:before:after"))
    checks.append(
        EvalCheck(
            "out_of_support_change_point",
            outside.status is TrajectoryStatus.NOT_EVALUABLE
            and outside.support_decision.status.value == "review_required",
            outside.status.value,
        )
    )
    replay = engine.verify(engine.infer(build_scenario_request("territory")))
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            replay.status is TrajectoryStatus.MODELED and tamper_rejected,
            "replay and tamper",
        )
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1205AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": sha256_digest(fixture),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": passed,
        "total_cases": len(checks),
        "passed": passed == len(checks),
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
