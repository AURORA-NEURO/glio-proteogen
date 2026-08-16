"""Genuine M11-06 perturbation and sensitivity evaluator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m11_06 import (
    M1106_M1105_INPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationSpecification,
    SensitivitySimulationConfiguration,
    SensitivitySimulationStatus,
    SimulateVariantPeptidePerturbationsRequest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_06_perturbation_sensitivity_simulator as m1106_runtime,
)

_ROOT: Final = Path(__file__).parents[2]
_FIXTURE: Final = _ROOT / "tests" / "fixtures" / "m11_06" / "scenarios.json"
_INVALID_FIXTURE: Final = "M11-06 fixture scenarios must be a list"


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m1106.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1106": label}),
        media_type=media_type,
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    decision_state = UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED

    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m1106.{role}",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )

    return ExecutionContext(
        request_id="request.synthetic.m1106",
        actor_id="actor.synthetic.m1106",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m1106.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": "synthetic-m1106"}),
                evidence=_artifact("control-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m1106.consent",
                state=ConsentState.WITHHELD if denied else ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _perturbation(case_id: str) -> PerturbationSpecification:
    kind = {
        "parameter_sweep": PerturbationKind.PARAMETER_SWEEP,
        "alternative_prior": PerturbationKind.ALTERNATIVE_PRIOR,
        "assay_perturbation": PerturbationKind.ASSAY_PERTURBATION,
        "mechanism_stress": PerturbationKind.MECHANISM_STRESS,
    }.get(case_id, PerturbationKind.IN_SILICO)
    parameter = "protein_abundance"
    perturbed = "1.2"
    if case_id == "unsupported_ood":
        perturbed = "ood"
    if case_id == "prohibited_ownership":
        parameter = "kinase_activity"
    return PerturbationSpecification(
        perturbation_id=f"scenario.synthetic.m1106.{case_id}",
        kind=kind,
        target_ids=("variant-peptide.synthetic.m1106",),
        parameter=parameter,
        baseline_value="1.0",
        perturbed_value=perturbed,
        rationale="Caller-declared perturbation for the locked M11-06 evaluator.",
        alternative_prior=(
            _artifact(f"prior-{case_id}") if kind is PerturbationKind.ALTERNATIVE_PRIOR else None
        ),
        assay_artifact=(
            _artifact(f"assay-{case_id}") if kind is PerturbationKind.ASSAY_PERTURBATION else None
        ),
    )


def build_scenario_request(
    case_id: str = "supported_in_silico",
) -> SimulateVariantPeptidePerturbationsRequest:
    negative_control = case_id != "missing_negative_control"
    return SimulateVariantPeptidePerturbationsRequest(
        request_id=f"request.synthetic.m1106.{case_id}",
        context=_context(denied=case_id == "denied_control").model_copy(
            update={"request_id": f"request.synthetic.m1106.{case_id}"}
        ),
        upstream_result=_artifact("upstream", M1106_M1105_INPUT_MEDIA_TYPE),
        configuration=SensitivitySimulationConfiguration(
            configuration_id="config.synthetic.m1106",
            version="1.0.0",
            model_family="deterministic-bounded-reference",
            reference_artifact=_artifact("configuration"),
            maximum_scenarios=8,
            negative_control_artifact=_artifact("negative-control") if negative_control else None,
        ),
        perturbations=(_perturbation(case_id),),
        source_artifacts=(_artifact(f"source-{case_id}"),),
    )


def fixture_cases() -> tuple[dict[str, object], ...]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list):
        raise TypeError(_INVALID_FIXTURE)
    return tuple(item for item in scenarios if isinstance(item, dict))


def run_evaluator() -> dict[str, object]:
    engine = m1106_runtime.M1106SensitivityEngine()
    outcomes: list[dict[str, object]] = []
    for scenario in fixture_cases():
        case_id = str(scenario["case_id"])
        expected = str(scenario["expected"])
        if case_id == "denied_control":
            try:
                engine.register(build_scenario_request(case_id))
            except m1106_runtime.M1106AuthorizationError:
                actual = "authorization_rejected"
            else:
                actual = "unexpected_success"
        else:
            result = engine.register(build_scenario_request(case_id))
            actual = result.status.value
            if expected == SensitivitySimulationStatus.SIMULATED.value:
                engine.verify(result)
        outcomes.append({"case_id": case_id, "expected": expected, "actual": actual})
    if any(item["expected"] != item["actual"] for item in outcomes):
        raise AssertionError(outcomes)
    return {
        "module_id": "GLIO-PROTEOGEN-M11-06",
        "passed": True,
        "declared": len(outcomes),
        "executed": len(outcomes),
        "failed": [],
        "outcomes": outcomes,
        "fixture_digest": sha256_digest({"scenarios": fixture_cases()}),
    }


__all__ = ["build_scenario_request", "fixture_cases", "run_evaluator"]
