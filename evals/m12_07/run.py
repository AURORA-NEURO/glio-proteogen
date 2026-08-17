"""Run the locked M12-07 plausibility and negative-control evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m12_07 import (
    M1207_M1206_RESULT_MEDIA_TYPE,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityControl,
    PlausibilityGrade,
    UnresolvedConflict,
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
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
    M1207PlausibilityAuthorizationError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-07"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m12_07" / "scenarios.json"
EXPECTED_CASE_IDS: Final = (
    "supported_high",
    "failed_control",
    "missing_observation",
    "direction_mismatch",
    "unresolved_conflict",
    "denied_quality_gate",
    "abstained_control",
    "replay_tamper",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    case_id: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    fixture_digest: str
    declared_case_ids: tuple[str, ...]
    executed_case_ids: tuple[str, ...]
    checks: tuple[EvalCheck, ...]
    passed: bool


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1207.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1207": label}),
        media_type=media_type,
    )


def _evidence(label: str, reference: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(reference=reference, role="evidence", claim=f"Evidence {label}.")


def _context(*, denied_role: str | None = None) -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.m1207.{role}",
            state=(
                UpstreamDecisionState.REJECTED
                if role == denied_role
                else UpstreamDecisionState.ACCEPTED
            ),
            policy_version="1.0.0",
            evidence=_artifact(f"context.{role}"),
        )

    return ExecutionContext(
        request_id="request.m1207.evaluator",
        actor_id="actor.m1207.evaluator",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("approved_configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1207.identity_lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "evaluator"}),
                evidence=_artifact("context.identity_lineage"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.m1207.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("context.consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended_use"),
        ),
    )


def build_scenario_request(
    case_id: str = "supported_high",
) -> AdjudicateBiomarkerPanelPlausibilityRequest:
    """Build one deterministic evaluator request without traversing artifacts."""

    evidence = _artifact("control.evidence")
    controls = [
        PlausibilityControl(
            control_id=f"control.{kind.value}",
            kind=kind,
            criterion=f"{kind.value} criterion is satisfied.",
            declared_outcome=ControlOutcome.PASSED,
            required_evidence=(_evidence(kind.value, evidence),),
        )
        for kind in ControlKind
    ]
    context = _context()
    declared_conflicts: tuple[UnresolvedConflict, ...] = ()
    if case_id in {"failed_control", "abstained_control"}:
        controls[0] = controls[0].model_copy(
            update={
                "declared_outcome": (
                    ControlOutcome.FAILED
                    if case_id == "failed_control"
                    else ControlOutcome.ABSTAINED
                )
            }
        )
    elif case_id == "missing_observation":
        controls[0] = controls[0].model_copy(update={"declared_outcome": None})
    elif case_id == "direction_mismatch":
        controls[0] = controls[0].model_copy(
            update={
                "expected_direction": "increasing",
                "declared_observed_direction": "decreasing",
            }
        )
    elif case_id == "unresolved_conflict":
        conflict_evidence = _evidence("conflict", _artifact("conflict"))
        declared_conflicts = (
            UnresolvedConflict(
                conflict_id="conflict.m1207.mechanism",
                description="Orthogonal evidence supports competing mechanisms.",
                competing_mechanisms=("mechanism.a", "mechanism.b"),
                evidence=(conflict_evidence,),
            ),
        )
    elif case_id == "denied_quality_gate":
        context = _context(denied_role="quality")
    elif case_id not in EXPECTED_CASE_IDS:
        raise ValueError(f"unknown evaluator case: {case_id}")  # noqa: TRY003
    return AdjudicateBiomarkerPanelPlausibilityRequest(
        request_id="request.m1207.evaluator",
        context=context,
        mechanism_inference_result=_artifact("mechanism", M1207_M1206_RESULT_MEDIA_TYPE),
        controls=tuple(controls),
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
        declared_conflicts=declared_conflicts,
    )


def _fixture() -> tuple[str, list[dict[str, Any]]]:
    corpus = cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))
    fixture_digest = sha256_digest(corpus)
    scenarios = cast("list[dict[str, Any]]", corpus["scenarios"])
    return fixture_digest, scenarios


def _check_case(case_id: str, expected: dict[str, Any]) -> EvalCheck:
    engine = M1207PlausibilityAdjudicatorEngine()
    if case_id == "denied_quality_gate":
        try:
            engine.adjudicate(build_scenario_request(case_id))
        except M1207PlausibilityAuthorizationError:
            return EvalCheck(
                case_id=case_id,
                passed=expected["expected"] == "authorization_denied",
                detail="authorization denied",
            )
        return EvalCheck(
            case_id=case_id,
            passed=False,
            detail="authorization unexpectedly granted",
        )
    request = build_scenario_request(case_id)
    result = engine.adjudicate(request)
    if case_id == "replay_tamper":
        replay_ok = engine.verify(request, result) == result
        tampered = result.model_copy(update={"grade": PlausibilityGrade.LOW})
        try:
            engine.verify(request, tampered)
        except ValueError:
            tamper_blocked = True
        else:
            tamper_blocked = False
        return EvalCheck(
            case_id=case_id,
            passed=replay_ok and tamper_blocked,
            detail="replay and tamper checks",
        )
    status_ok = result.status.value == expected["status"]
    grade_value = result.grade.value if result.grade is not None else None
    grade_ok = expected.get("grade") is None or grade_value == expected["grade"]
    return EvalCheck(
        case_id=case_id,
        passed=status_ok and grade_ok,
        detail=f"status={result.status.value}, grade={grade_value}",
    )


def run_evaluator() -> EvaluationReport:
    fixture_digest, scenarios = _fixture()
    declared = tuple(str(item["case_id"]) for item in scenarios)
    if declared != EXPECTED_CASE_IDS:
        raise ValueError("M12-07 fixture case IDs are not locked")  # noqa: TRY003
    checks = tuple(
        _check_case(str(item["case_id"]), cast("dict[str, Any]", item["expected"]))
        for item in scenarios
    )
    executed = tuple(item.case_id for item in checks)
    return EvaluationReport(
        module_id=MODULE_ID,
        fixture_digest=fixture_digest,
        declared_case_ids=declared,
        executed_case_ids=executed,
        checks=checks,
        passed=all(item.passed for item in checks) and executed == EXPECTED_CASE_IDS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = asdict(run_evaluator())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
