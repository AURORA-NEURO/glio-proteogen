"""Executable M12-06 sensitivity evaluation against the public runtime seam."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m12_06 import (
    PerturbationKind,
    PerturbationPolicy,
    PerturbationScenario,
    PerturbationStatus,
    SimulateBiomarkerPanelPerturbationRequest,
    SimulatorConfiguration,
)
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
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator import (  # noqa: E501
    M1206AuthorizationError,
    M1206Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-06"
CONTRACT_VERSION: Final = "0.1.0-provisional"
SCENARIO_PATH: Final = Path("tests/fixtures/m12_06/scenarios.json")


@dataclass(frozen=True, slots=True)
class EvalCheck:
    case_id: str
    passed: bool
    detail: str


def _artifact(name: str, ordinal: int) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=f"sha256:{ordinal:064x}",
        media_type="application/json",
    )


def _context(*, denied: str | None = None) -> ExecutionContext:
    upstream = {
        "approved_configuration": UpstreamDecisionState.REJECTED
        if denied == "approved_configuration"
        else UpstreamDecisionState.ACCEPTED,
        "provenance": UpstreamDecisionState.REJECTED
        if denied == "provenance"
        else UpstreamDecisionState.ACCEPTED,
        "quality": UpstreamDecisionState.REJECTED
        if denied == "quality"
        else UpstreamDecisionState.ACCEPTED,
        "support": UpstreamDecisionState.REJECTED
        if denied == "support"
        else UpstreamDecisionState.ACCEPTED,
        "intended_use": UpstreamDecisionState.REJECTED
        if denied == "intended_use"
        else UpstreamDecisionState.ACCEPTED,
    }
    return ExecutionContext(
        request_id="m1206-eval-request",
        actor_id="m1206-eval-actor",
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="eval-config",
                state=upstream["approved_configuration"],
                policy_version="1.0.0",
                evidence=_artifact("control.config", 10),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="eval-identity",
                state=IdentityLineageState.CONFLICTED
                if denied == "identity_lineage"
                else IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("subject", 11).digest,
                evidence=_artifact("control.identity", 11),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="eval-provenance",
                state=upstream["provenance"],
                policy_version="1.0.0",
                evidence=_artifact("control.provenance", 12),
            ),
            consent=ConsentReference(
                decision_id="eval-consent",
                state=ConsentState.WITHHELD if denied == "consent" else ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent", 13),
            ),
            quality=UpstreamDecisionReference(
                decision_id="eval-quality",
                state=upstream["quality"],
                policy_version="1.0.0",
                evidence=_artifact("control.quality", 14),
            ),
            support=UpstreamDecisionReference(
                decision_id="eval-support",
                state=upstream["support"],
                policy_version="1.0.0",
                evidence=_artifact("control.support", 15),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="eval-use",
                state=upstream["intended_use"],
                policy_version="1.0.0",
                evidence=_artifact("control.use", 16),
            ),
        ),
    )


def build_request(
    *,
    denied: str | None = None,
    status: PerturbationStatus = PerturbationStatus.SUPPORTED,
    value: float = 0.3,
) -> SimulateBiomarkerPanelPerturbationRequest:
    evidence = EvidenceReference(
        reference=_artifact("scenario.evidence", 22),
        role="evidence",
        claim="Scenario evidence is reviewed.",
    )
    scenario = PerturbationScenario(
        scenario_id="eval-scenario-1",
        kind=PerturbationKind.IN_SILICO,
        parameter="panel.signal",
        baseline_value=value,
        perturbed_value=value + 0.1,
        unit="relative",
        status=status,
        assumption="Local perturbation remains bounded.",
        source_artifact=_artifact("scenario.source", 21),
        evidence=(evidence,) if status is PerturbationStatus.SUPPORTED else (),
    )
    config = SimulatorConfiguration(
        configuration_id="eval-config",
        version="1.0.0",
        method="bounded-deterministic-reference",
        model_reference=_artifact("model", 30),
        units_reference=_artifact("units", 31),
        evidence=(evidence,),
    )
    return SimulateBiomarkerPanelPerturbationRequest(
        request_id="m1206-eval-request",
        context=_context(denied=denied),
        upstream_consequence_result=_artifact("upstream", 20),
        policy=PerturbationPolicy(
            maximum_scenarios=4,
            response_lower_bound=0.0,
            response_upper_bound=1.0,
            configuration=config,
        ),
        scenarios=(scenario,),
        source_artifacts=(_artifact("source", 23),),
    )


def _fixture() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def run_evaluation() -> dict[str, object]:
    """Run all fixture cases and report every case explicitly."""

    cases = cast("list[dict[str, object]]", _fixture()["cases"])
    service = M1206Service()
    checks: list[EvalCheck] = []
    for case in cases:
        case_id = cast("str", case["case_id"])
        kind = cast("str", case["kind"])
        try:
            request = (
                build_request(denied=kind.removeprefix("denied:"))
                if kind.startswith("denied:")
                else build_request(
                    status=PerturbationStatus.UNSUPPORTED
                    if kind == "unsupported"
                    else PerturbationStatus.SUPPORTED,
                    value=1.2 if kind == "out_of_bounds" else 0.3,
                )
            )
            result = service.execute(request)
            expected = cast("str", case["expected_status"])
            checks.append(
                EvalCheck(
                    case_id,
                    result.status.value == expected,
                    f"status={result.status.value};expected={expected}",
                )
            )
            if kind == "supported":
                replay_ok = service.verify(request, result) == result
                checks.append(
                    EvalCheck(f"{case_id}:replay", replay_ok, "exact request/result replay")
                )
        except M1206AuthorizationError:
            expected = cast("str", case["expected_status"])
            checks.append(
                EvalCheck(
                    case_id,
                    expected == "authorization_rejected",
                    "authorization rejected before payload traversal",
                )
            )
    declared = [cast("str", case["case_id"]) for case in cases]
    executed = [check.case_id for check in checks if ":replay" not in check.case_id]
    return {
        "module_id": MODULE_ID,
        "contract_version": CONTRACT_VERSION,
        "fixture": str(SCENARIO_PATH),
        "declared_case_count": len(declared),
        "executed_case_count": len(executed),
        "checks": [asdict(item) for item in checks],
        "passed": len(executed) == len(declared) and all(item.passed for item in checks),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


__all__ = ["build_request", "main", "run_evaluation"]

if __name__ == "__main__":
    raise SystemExit(main())
