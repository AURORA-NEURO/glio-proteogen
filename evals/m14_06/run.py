"""Deterministic M14-06 evaluator over frozen perturbation scenarios."""

# Evaluator matrix intentionally keeps long case descriptions and constructor
# parameters visible; it also prints a machine-readable report when invoked.
# ruff: noqa: E501, PLR0913, TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m14_06 import (
    M1406_M1405_INPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationSpecification,
    SensitivitySimulationConfiguration,
    SensitivitySimulationStatus,
    SimulateProteinSubtypePerturbationsRequest,
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
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_06_perturbation_sensitivity_simulator import (
    M1406SensitivityAuthorizationError,
    M1406SensitivityEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M14-06"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m14_06" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "bounded_simulation",
    "alternative_prior",
    "assay_perturbation",
    "unsupported_model_abstention",
    "missing_value_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1406_fixture": label})


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


def _perturbation(
    scenario_id: str,
    *,
    kind: PerturbationKind = PerturbationKind.IN_SILICO,
    baseline: str = "1.0",
    perturbed: str = "1.2",
    alternative_prior: ArtifactReference | None = None,
    assay_artifact: ArtifactReference | None = None,
) -> PerturbationSpecification:
    return PerturbationSpecification(
        perturbation_id=scenario_id,
        kind=kind,
        target_ids=("protein.target",),
        parameter="abundance",
        baseline_value=baseline,
        perturbed_value=perturbed,
        rationale="Measure bounded sensitivity to a caller-declared perturbation.",
        alternative_prior=alternative_prior,
        assay_artifact=assay_artifact,
        evidence=(
            EvidenceReference(
                reference=_artifact(f"evidence.{scenario_id}"),
                role="evidence",
                claim="Frozen perturbation scenario evidence.",
            ),
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    model_family: str = "curated_rule",
    perturbations: tuple[PerturbationSpecification, ...] | None = None,
) -> SimulateProteinSubtypePerturbationsRequest:
    """Build a genuine typed request from caller-declared references only."""

    context = ExecutionContext(
        request_id="request.m1406",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted=accepted),
    )
    configuration = SensitivitySimulationConfiguration(
        configuration_id="configuration.m1406",
        version="1.0.0",
        model_family=model_family,
        reference_artifact=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        maximum_scenarios=8,
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration.evidence"),
                role="evidence",
                claim="Locked sensitivity model and unit manifest.",
            ),
        ),
    )
    selected = perturbations or (_perturbation("scenario.base"),)
    return SimulateProteinSubtypePerturbationsRequest(
        request_id="request.m1406",
        context=context,
        upstream_result=_artifact("m1405-result", M1406_M1405_INPUT_MEDIA_TYPE),
        configuration=configuration,
        perturbations=selected,
        source_artifacts=(_artifact("counter-evidence"),),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M14-06 fixture case IDs are not locked")
    engine = M1406SensitivityEngine()
    checks: list[EvalCheck] = []
    base = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "bounded_simulation",
            base.status is SensitivitySimulationStatus.SIMULATED,
            base.status.value,
        )
    )
    prior = engine.infer(
        build_scenario_request(
            perturbations=(
                _perturbation(
                    "scenario.prior",
                    kind=PerturbationKind.ALTERNATIVE_PRIOR,
                    alternative_prior=_artifact("prior"),
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "alternative_prior",
            prior.status is SensitivitySimulationStatus.SIMULATED,
            prior.status.value,
        )
    )
    assay = engine.infer(
        build_scenario_request(
            perturbations=(
                _perturbation(
                    "scenario.assay",
                    kind=PerturbationKind.ASSAY_PERTURBATION,
                    assay_artifact=_artifact("assay"),
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "assay_perturbation",
            assay.status is SensitivitySimulationStatus.SIMULATED,
            assay.status.value,
        )
    )
    unsupported = engine.infer(build_scenario_request(model_family="unregistered_model"))
    checks.append(
        EvalCheck(
            "unsupported_model_abstention",
            unsupported.status is SensitivitySimulationStatus.ABSTAINED,
            unsupported.abstention_reason or "",
        )
    )
    missing = engine.infer(
        build_scenario_request(perturbations=(_perturbation("scenario.missing", baseline="N/A"),))
    )
    checks.append(
        EvalCheck(
            "missing_value_abstention",
            missing.status is SensitivitySimulationStatus.ABSTAINED,
            missing.abstention_reason or "",
        )
    )
    replay = engine.verify(base)
    tampered = base.model_copy(update={"result_digest": _digest("tampered")})
    tamper_rejected = False
    try:
        engine.verify(tampered)
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck("replay_and_tamper", replay == base and tamper_rejected, "replay and tamper")
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1406SensitivityAuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail} for check in checks
        ],
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(check.passed for check in checks),
        "total_cases": len(checks),
        "passed": all(check.passed for check in checks),
    }


def main() -> int:
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
