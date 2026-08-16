"""Run the locked synthetic M14-07 plausibility adjudication matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from glio_proteogen.contracts.m14_07 import (
    M1407_M1404_RESULT_MEDIA_TYPE,
    AdjudicateProteinSubtypePlausibilityRequest,
    ControlKind,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
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
from glio_proteogen.modules.c14_microenvironment.m14_07_plausibility_negative_control_adjudicator import (  # noqa: E501
    M1407AuthorizationError,
    M1407PlausibilityAdjudicator,
)

MODULE_ID = "GLIO-PROTEOGEN-M14-07"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m14_07" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "all_controls_pass",
    "failed_control_abstention",
    "not_evaluable_abstention",
    "explicit_abstention",
    "unresolved_conflict",
    "missing_control_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
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
        digest=sha256_digest({"m1407-eval": label}),
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
    *,
    accepted: bool = True,
    criterion: str = "consistent orthogonal evidence",
    missing_kind: bool = False,
) -> AdjudicateProteinSubtypePlausibilityRequest:
    kinds = tuple(ControlKind)
    selected = kinds[:-1] if missing_kind else kinds
    controls = tuple(
        PlausibilityControl(
            control_id=f"control.{kind.value}",
            kind=kind,
            criterion=criterion
            if kind is ControlKind.KNOWN_CONTROL
            else f"consistent {kind.value}",
            expected_direction="consistent",
            required_evidence=(
                EvidenceReference(
                    reference=_artifact(f"control.{kind.value}"),
                    role="evidence",
                    claim="Locked synthetic M14-07 control evidence.",
                ),
            ),
        )
        for kind in selected
    )
    return AdjudicateProteinSubtypePlausibilityRequest(
        request_id="request.m1407",
        context=ExecutionContext(
            request_id="request.m1407",
            actor_id="actor.evaluator",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        mechanism_inference_result=_artifact("mechanism", M1407_M1404_RESULT_MEDIA_TYPE),
        controls=controls,
        source_artifacts=(
            _artifact("proteome"),
            _artifact("genome"),
            _artifact("transcriptome"),
            _artifact("ptm"),
        ),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M14-07 fixture case IDs are not locked")
    engine = M1407PlausibilityAdjudicator()
    checks: list[EvalCheck] = []
    supported = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "all_controls_pass",
            supported.status is PlausibilityAdjudicationStatus.ADJUDICATED,
            supported.status.value,
        )
    )
    for name, request in (
        ("failed_control_abstention", build_scenario_request(criterion="fail: incompatible")),
        ("not_evaluable_abstention", build_scenario_request(criterion="unsupported domain")),
        ("explicit_abstention", build_scenario_request(criterion="abstain pending review")),
        ("unresolved_conflict", build_scenario_request(criterion="conflict: primary|alternate")),
        ("missing_control_abstention", build_scenario_request(missing_kind=True)),
    ):
        result = engine.infer(request)
        checks.append(
            EvalCheck(
                name,
                result.status is PlausibilityAdjudicationStatus.ABSTAINED,
                result.status.value,
            )
        )
    replay = engine.infer(build_scenario_request())
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(EvalCheck("replay_and_tamper", tamper_rejected, "tamper rejected"))
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1407AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    first = engine.infer(build_scenario_request())
    second = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
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
    argparse.ArgumentParser().parse_args()
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
