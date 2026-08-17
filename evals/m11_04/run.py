"""Run the locked, deterministic M11-04 evaluation matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003, E501

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m11_04 import (
    M1104_M1101_RESULT_MEDIA_TYPE,
    InferVariantPeptideMechanismRequest,
    MechanismInferenceConfiguration,
    MechanismInferenceStatus,
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
from glio_proteogen.modules.c11_protein_native_subtype.m11_04_network_state_mechanism_inference import (
    M1104MechanismAuthorizationError,
    M1104MechanismEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M11-04"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m11_04" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "posterior_inference",
    "state_inference",
    "explicit_abstention",
    "unknown_method_abstention",
    "invalid_bounds_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1104_fixture": label})


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


def build_scenario_request(
    method: str = "posterior:mechanism-a:Candidate mechanism:0.80:0.70:0.90",
    *,
    accepted: bool = True,
) -> InferVariantPeptideMechanismRequest:
    """Build a genuine typed request from caller-declared references only."""

    context = ExecutionContext(
        request_id="request.m1104",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted=accepted),
    )
    config_evidence = EvidenceReference(
        reference=_artifact("configuration.evidence"),
        role="evidence",
        claim="Locked method and calibration manifest.",
    )
    configuration = MechanismInferenceConfiguration(
        configuration_id="configuration.m1104",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        calibration_reference=_artifact(
            "calibration", "application/vnd.glio-proteogen.calibration+json"
        ),
        evidence=(config_evidence,),
    )
    return InferVariantPeptideMechanismRequest(
        request_id="request.m1104",
        context=context,
        hypothesis_registry_result=_artifact("m1101-result", M1104_M1101_RESULT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact("counter-evidence"),),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M11-04 fixture case IDs are not locked")
    engine = M1104MechanismEngine()
    checks: list[EvalCheck] = []
    posterior = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "posterior_inference",
            posterior.status is MechanismInferenceStatus.INFERRED,
            posterior.status.value,
        )
    )
    state = engine.infer(build_scenario_request("state:mechanism-b:State mechanism:active"))
    checks.append(
        EvalCheck(
            "state_inference", state.status is MechanismInferenceStatus.INFERRED, state.status.value
        )
    )
    explicit = engine.infer(build_scenario_request("abstain:review"))
    checks.append(
        EvalCheck(
            "explicit_abstention",
            explicit.status is MechanismInferenceStatus.ABSTAINED,
            explicit.abstention_reason or "",
        )
    )
    unknown = engine.infer(build_scenario_request("bayesian_graph:mechanism:label"))
    checks.append(
        EvalCheck(
            "unknown_method_abstention",
            unknown.status is MechanismInferenceStatus.ABSTAINED,
            unknown.abstention_reason or "",
        )
    )
    invalid = engine.infer(build_scenario_request("posterior:mechanism-a:Candidate:0.95:0.10:0.20"))
    checks.append(
        EvalCheck(
            "invalid_bounds_abstention",
            invalid.status is MechanismInferenceStatus.ABSTAINED,
            invalid.abstention_reason or "",
        )
    )
    replay = engine.verify(posterior)
    tampered = posterior.model_copy(update={"result_digest": _digest("tampered")})
    tamper_rejected = False
    try:
        engine.verify(tampered)
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck("replay_and_tamper", replay == posterior and tamper_rejected, "replay and tamper")
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1104MechanismAuthorizationError:
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
