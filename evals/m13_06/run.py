"""Replay the locked synthetic M13-06 perturbation corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m13_06.v1 import (
    PerturbationKind,
    PerturbationPolicy,
    PerturbationScenario,
    PerturbationStatus,
    SimulateProteotypePerturbationRequest,
    SimulatorConfiguration,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    M1306AuthorizationError,
    simulate_proteotype_perturbation_sensitivity,
)

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "m13_06" / "scenarios.json"


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m1306.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1306": label}),
        media_type="application/json",
    )


def _request(case: dict[str, Any]) -> SimulateProteotypePerturbationRequest:
    def accepted(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.m1306.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}"),
        )

    controls = ContextReferences(
        approved_configuration=accepted("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.m1306.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=sha256_digest({"m1306": "identity"}),
            evidence=_artifact("control.identity"),
        ),
        provenance=accepted("provenance"),
        consent=ConsentReference(
            decision_id="decision.m1306.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.m1306.quality",
            state=UpstreamDecisionState(case.get("quality", "accepted")),
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=accepted("support"),
        intended_use=accepted("intended-use"),
    )
    context = ExecutionContext(
        request_id=f"request.m1306.{case['id']}",
        actor_id="actor.synthetic.m1306",
        occurred_at=__import__("datetime").datetime(2026, 8, 15, tzinfo=__import__("datetime").UTC),
        references=controls,
    )
    source = _artifact("source")
    evidence = EvidenceReference(
        reference=source,
        role="evidence",
        claim="Synthetic bounded perturbation fixture.",
    )
    scenario = PerturbationScenario(
        scenario_id=f"scenario.m1306.{case['id']}",
        kind=PerturbationKind(case["kind"]),
        parameter="variant-peptide.response",
        baseline_value=case["baseline"],
        perturbed_value=case["perturbed"],
        unit="fraction",
        status=PerturbationStatus(case["status"]),
        assumption="Synthetic fixture remains within the declared envelope.",
        source_artifact=source,
        evidence=(evidence,),
    )
    configuration = SimulatorConfiguration(
        configuration_id="configuration.m1306.eval",
        version="1.0.0",
        method="bounded replay",
        model_reference=_artifact("model"),
        units_reference=_artifact("units"),
    )
    return SimulateProteotypePerturbationRequest(
        request_id=context.request_id,
        context=context,
        variant_peptide_result=_artifact("variant-peptide"),
        policy=PerturbationPolicy(
            maximum_scenarios=1,
            response_lower_bound=0.0,
            response_upper_bound=1.0,
            configuration=configuration,
        ),
        scenarios=(scenario,),
        source_artifacts=(source,),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable checks.")
    args = parser.parse_args()
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []
    for case in corpus["cases"]:
        try:
            result = simulate_proteotype_perturbation_sensitivity(_request(case))
            actual = result.status.value
        except M1306AuthorizationError:
            actual = "authorization_error"
        passed = actual == case["expected"]
        checks.append(
            {
                "id": case["id"],
                "passed": passed,
                "expected": case["expected"],
                "actual": actual,
            }
        )
    payload = {
        "module_id": corpus["module_id"],
        "requirement_sha256": corpus["requirement_sha256"],
        "dossier_slice": corpus["dossier_slice"],
        "declared": len(corpus["cases"]),
        "executed": len(checks),
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    if args.json:
        sys.stdout.write(canonical_json_bytes(payload).decode() + "\n")
    else:
        sys.stdout.write(
            f"{payload['module_id']} cases={payload['executed']} passed={payload['passed']}\n"
        )
        for check in checks:
            sys.stdout.write(
                f"{check['id']}: {check['actual']} ({'PASS' if check['passed'] else 'FAIL'})\n"
            )
    return 0 if payload["passed"] and payload["declared"] == payload["executed"] else 1


if __name__ == "__main__":
    sys.exit(main())
