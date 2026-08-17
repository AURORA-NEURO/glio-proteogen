"""Deterministic M15-06 evaluator over frozen perturbation scenarios."""

# The matrix intentionally keeps safety and abstention cases explicit.
# ruff: noqa: E501, TRY003, T201

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m15_06 import (
    M1506_M1505_INPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivitySimulationConfiguration,
    SensitivitySimulationStatus,
    SimulateComplexActivityPerturbationsRequest,
    contract_json_schemas,
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
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_06_perturbation_sensitivity_simulator import (
    M1506AuthorizationError,
    M1506SensitivitySimulatorEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M15-06"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m15_06" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "simulated_bounded",
    "multi_scenario_surface",
    "input_incomplete_abstention",
    "negative_control_abstention",
    "out_of_envelope_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1506_fixture": label})


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=_digest(label),
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
            binding_digest=_digest("identity.binding"),
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
            decision_id="decision.intended-use",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended-use"),
        ),
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M15-06 perturbation evidence.",
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    perturbations: tuple[PerturbationSpecification, ...] | None = None,
    model_family: str = "mechanistic_baseline",
) -> SimulateComplexActivityPerturbationsRequest:
    if perturbations is None:
        perturbations = (
            PerturbationSpecification(
                perturbation_id="scenario.in-silico",
                kind=PerturbationKind.IN_SILICO,
                target_ids=("target.complex-activity",),
                parameter="activity",
                baseline_value="1.0",
                perturbed_value="1.2",
                rationale="Bounded in-silico sensitivity scenario.",
                evidence=_evidence("perturbation.in-silico"),
            ),
        )
    configuration = SensitivitySimulationConfiguration(
        configuration_id="configuration.m1506",
        version="1.0.0",
        model_family=model_family,
        reference_artifact=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        maximum_scenarios=8,
        evidence=_evidence("configuration"),
    )
    return SimulateComplexActivityPerturbationsRequest(
        request_id="request.m1506",
        context=ExecutionContext(
            request_id="request.m1506",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        upstream_result=_artifact("m1505-result", M1506_M1505_INPUT_MEDIA_TYPE),
        configuration=configuration,
        perturbations=perturbations,
        source_artifacts=(
            _artifact("source-proteome"),
            _artifact("source-transcriptome"),
        ),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M15-06 fixture case IDs are not locked")
    engine = M1506SensitivitySimulatorEngine()
    checks: list[EvalCheck] = []
    simulated = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "simulated_bounded",
            simulated.status is SensitivitySimulationStatus.SIMULATED
            and simulated.surface is not None
            and all(
                item.status is PerturbationResponseStatus.BOUNDED
                for item in simulated.surface.responses
            ),
            simulated.status.value,
        )
    )
    multi = build_scenario_request(
        perturbations=(
            PerturbationSpecification(
                perturbation_id="scenario.a",
                kind=PerturbationKind.IN_SILICO,
                target_ids=("target.a",),
                parameter="activity",
                baseline_value="1.0",
                perturbed_value="1.2",
                rationale="one",
                evidence=_evidence("a"),
            ),
            PerturbationSpecification(
                perturbation_id="scenario.b",
                kind=PerturbationKind.PARAMETER_SWEEP,
                target_ids=("target.b",),
                parameter="activity",
                baseline_value="1.0",
                perturbed_value="0.7",
                rationale="two",
                evidence=_evidence("b"),
            ),
        )
    )
    multi_result = engine.infer(multi)
    checks.append(
        EvalCheck(
            "multi_scenario_surface",
            multi_result.surface is not None
            and len(multi_result.surface.responses) == len(multi.perturbations),
            "one response per scenario",
        )
    )
    nonnumeric = engine.infer(
        build_scenario_request(
            perturbations=(
                PerturbationSpecification(
                    perturbation_id="scenario.bad",
                    kind=PerturbationKind.IN_SILICO,
                    target_ids=("target.a",),
                    parameter="activity",
                    baseline_value="missing",
                    perturbed_value="1.0",
                    rationale="missing numeric input",
                    evidence=_evidence("bad"),
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "input_incomplete_abstention",
            nonnumeric.status is SensitivitySimulationStatus.ABSTAINED,
            nonnumeric.abstention_reason or "",
        )
    )
    stress = PerturbationSpecification(
        perturbation_id="scenario.stress",
        kind=PerturbationKind.MECHANISM_STRESS,
        target_ids=("target.a",),
        parameter="activity",
        baseline_value="1.0",
        perturbed_value="0.8",
        rationale="stress without required gate",
        evidence=_evidence("stress"),
    )
    stress_result = engine.infer(build_scenario_request(perturbations=(stress,)))
    checks.append(
        EvalCheck(
            "negative_control_abstention",
            stress_result.status is SensitivitySimulationStatus.ABSTAINED,
            stress_result.abstention_reason or "",
        )
    )
    envelope = PerturbationSpecification(
        perturbation_id="scenario.large",
        kind=PerturbationKind.IN_SILICO,
        target_ids=("target.a",),
        parameter="activity",
        baseline_value="0",
        perturbed_value="11",
        rationale="out of envelope",
        evidence=_evidence("large"),
    )
    envelope_result = engine.infer(build_scenario_request(perturbations=(envelope,)))
    checks.append(
        EvalCheck(
            "out_of_envelope_abstention",
            envelope_result.status is SensitivitySimulationStatus.ABSTAINED,
            envelope_result.abstention_reason or "",
        )
    )
    replay = engine.infer(build_scenario_request())
    replay_ok = engine.verify(replay) == replay
    tampered = replay.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.verify(tampered)
    except Exception:  # noqa: BLE001
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(
        EvalCheck("replay_and_tamper", replay_ok and tamper_rejected, "replay and tamper")
    )
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1506AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail} for item in checks
        ],
        "passed": len(checks) == len(case_ids) and all(item.passed for item in checks),
        "schema_count": len(contract_json_schemas()),
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
