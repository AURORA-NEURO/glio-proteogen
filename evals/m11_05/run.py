"""Executable evaluator for the provisional M11-05 trajectory baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m11_05 import (
    M1105_M1104_RESULT_MEDIA_TYPE,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelVariantPeptideLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    contract_json_schema,
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
from glio_proteogen.modules.c11_protein_native_subtype.m11_05_longitudinal_evolution import (
    M1105AuthorizationError,
    M1105ReplayVerificationError,
    M1105Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M11-05"
SCENARIO_PATH: Final = Path(__file__).parents[2] / "tests/fixtures/m11_05/scenarios.json"
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000
TWO_STATES: Final = 2
ONE_CHANGE_POINT: Final = 1


@dataclass(frozen=True, slots=True)
class EvalCheck:
    case_id: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    fixture_sha256: str
    declared_case_count: int
    executed_case_count: int
    passed_case_count: int
    checks: tuple[EvalCheck, ...]
    passed: bool


def _artifact(name: str, letter: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.{name}",
        version="1.0.0",
        digest=sha256_digest({"m1105": name, "letter": letter}),
        media_type=media_type,
    )


def build_request(
    *,
    transition: bool = True,
    denied: bool = False,
) -> ModelVariantPeptideLongitudinalEvolutionRequest:
    """Build an opaque-reference request without reading any external artifact."""

    evidence = _artifact("control", "a")
    state = UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED
    controls = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=evidence,
        )
        for role in (
            "approved_configuration",
            "provenance",
            "quality",
            "support",
            "intended_use",
        )
    }
    references = ContextReferences(
        approved_configuration=controls["approved_configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity_lineage",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=sha256_digest("subject.m1105"),
            evidence=evidence,
        ),
        provenance=controls["provenance"],
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.WITHHELD if denied else ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=controls["quality"],
        support=controls["support"],
        intended_use=controls["intended_use"],
    )
    context = ExecutionContext(
        request_id="request.m1105.evaluator",
        actor_id="actor.m1105.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=references,
    )
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration.m1105.evaluator",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective="deterministic longitudinal state baseline",
        model_reference=_artifact("model", "b", "application/model"),
    )
    policy = TrajectoryPolicy(
        dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TREATMENT_ERA),
        minimum_observations=2,
        configuration=configuration,
    )
    labels = (("primary", "baseline"), ("recurrent", "post-treatment"))
    if not transition:
        labels = (("primary", "baseline"), ("primary", "baseline"))
    observations = tuple(
        TimePointObservation(
            observation_id=f"observation.{index + 1}",
            sequence=index,
            observed_at=datetime(2026, index + 1, 1, tzinfo=UTC),
            territory=territory,
            treatment_era=treatment_era,
            feature_artifact=_artifact(f"feature.{index + 1}", chr(99 + index)),
            evidence=(
                EvidenceReference(
                    reference=evidence,
                    role="evidence",
                    claim="synthetic evaluator observation",
                ),
            ),
        )
        for index, (territory, treatment_era) in enumerate(labels)
    )
    return ModelVariantPeptideLongitudinalEvolutionRequest(
        request_id=context.request_id,
        context=context,
        network_state_result=_artifact("m1104-result", "d", M1105_M1104_RESULT_MEDIA_TYPE),
        policy=policy,
        observations=observations,
        source_artifacts=(evidence,),
    )


def _fixture() -> dict[str, object]:
    raw = SCENARIO_PATH.read_bytes()
    return cast("dict[str, object]", json.loads(raw))


def _check(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(case_id=case_id, passed=passed, detail=detail)


def run_evaluator() -> EvaluationReport:
    raw = SCENARIO_PATH.read_bytes()
    fixture = _fixture()
    scenario_ids = cast("list[str]", fixture["scenario_ids"])
    expected = cast("dict[str, str]", fixture["scenario_expectations"])
    service = M1105Service()
    checks: list[EvalCheck] = []

    result = service.execute(build_request(transition=True))
    checks.append(
        _check(
            "modeled_transition",
            passed=result.status.value == "modeled"
            and len(result.trajectory) == TWO_STATES
            and len(result.change_points) == ONE_CHANGE_POINT,
            detail=expected["modeled_transition"],
        )
    )
    no_change = service.execute(build_request(transition=False))
    checks.append(
        _check(
            "modeled_no_transition",
            passed=len(no_change.trajectory) == 1 and not no_change.change_points,
            detail=expected["modeled_no_transition"],
        )
    )
    try:
        service.execute(build_request(denied=True))
    except M1105AuthorizationError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        _check(
            "control_denied_before_traversal",
            passed=denied_passed,
            detail=expected["control_denied_before_traversal"],
        )
    )
    unordered = build_request().model_copy(
        update={"observations": tuple(reversed(build_request().observations))}
    )
    try:
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate(unordered, strict=True)
    except (ValidationError, ValueError):
        order_passed = True
    else:
        order_passed = False
    checks.append(
        _check(
            "temporal_order_rejected",
            passed=order_passed,
            detail=expected["temporal_order_rejected"],
        )
    )
    replay = service.execute(build_request())
    checks.append(
        _check(
            "exact_replay_verified",
            passed=service.verify(replay).model_dump(mode="json") == replay.model_dump(mode="json"),
            detail=expected["exact_replay_verified"],
        )
    )
    tampered = replay.model_dump(mode="json")
    cast("dict[str, object]", tampered)["result_id"] = "result.tampered"
    try:
        service.verify(tampered, replay=False)
    except M1105ReplayVerificationError:
        tamper_passed = True
    else:
        tamper_passed = False
    checks.append(
        _check(
            "tampered_result_rejected",
            passed=tamper_passed,
            detail=expected["tampered_result_rejected"],
        )
    )
    wrong_parent = build_request().model_copy(
        update={"network_state_result": _artifact("wrong-parent", "e", "application/json")}
    )
    try:
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate(wrong_parent, strict=True)
    except (ValidationError, ValueError):
        parent_passed = True
    else:
        parent_passed = False
    checks.append(
        _check(
            "upstream_media_type_rejected",
            passed=parent_passed,
            detail=expected["upstream_media_type_rejected"],
        )
    )
    schema = contract_json_schema("output")
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    checks.append(
        _check(
            "strict_schema_metadata",
            passed=metadata["strict"] is True and metadata["provisionalAbi"] is True,
            detail=expected["strict_schema_metadata"],
        )
    )
    passed_count = sum(check.passed for check in checks)
    declared = cast("int", fixture["expected_case_count"])
    passed = len(checks) == declared == len(scenario_ids) and passed_count == declared
    return EvaluationReport(
        module_id=MODULE_ID,
        fixture_sha256=hashlib.sha256(raw).hexdigest(),
        declared_case_count=declared,
        executed_case_count=len(checks),
        passed_case_count=passed_count,
        checks=tuple(checks),
        passed=passed,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluator()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["EvaluationReport", "build_request", "main", "run_evaluator"]


if __name__ == "__main__":
    raise SystemExit(main())
