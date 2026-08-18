"""Run the locked, deterministic M13-08 evaluation matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003

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

from glio_proteogen.contracts.m13_08 import (
    M1308_M1307_INPUT_MEDIA_TYPE,
    AssembleProteotypeMechanismDossierRequest,
    DossierDiagnosticStatus,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
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
from glio_proteogen.modules.c13_variant_peptide.m13_08_mechanism_evidence_dossier import (
    M1308AuthorizationError,
    M1308DossierEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M13-08"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m13_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "bayesian_dossier_ready",
    "state_space_dossier_ready",
    "mechanistic_dossier_ready",
    "unsupported_family_abstention",
    "claim_ceiling_visible",
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
        digest=sha256_digest({"m1308-eval": label}),
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
    model_family: str = "bayesian_model_averaging", *, accepted: bool = True
) -> AssembleProteotypeMechanismDossierRequest:
    configuration = MechanismDossierConfiguration(
        configuration_id="configuration.m1308",
        version="1.0.0",
        model_family=model_family,
        source_manifest=(_artifact("manifest"),),
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration.evidence"),
                role="evidence",
                claim="Locked evaluator dossier configuration.",
            ),
        ),
    )
    return AssembleProteotypeMechanismDossierRequest(
        request_id="request.m1308",
        context=ExecutionContext(
            request_id="request.m1308",
            actor_id="actor.evaluator",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        upstream_result=_artifact("m1307-result", M1308_M1307_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact("source"),),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M13-08 fixture case IDs are not locked")
    engine = M1308DossierEngine()
    checks: list[EvalCheck] = []
    ready = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "bayesian_dossier_ready",
            ready.status is MechanismDossierStatus.READY and ready.dossier is not None,
            ready.status.value,
        )
    )
    state_space = engine.infer(build_scenario_request("state_space"))
    checks.append(
        EvalCheck(
            "state_space_dossier_ready",
            state_space.status is MechanismDossierStatus.READY,
            state_space.status.value,
        )
    )
    mechanistic = engine.infer(build_scenario_request("mechanistic"))
    checks.append(
        EvalCheck(
            "mechanistic_dossier_ready",
            mechanistic.status is MechanismDossierStatus.READY,
            mechanistic.status.value,
        )
    )
    unsupported = engine.infer(build_scenario_request("unknown-family"))
    checks.append(
        EvalCheck(
            "unsupported_family_abstention",
            unsupported.status is MechanismDossierStatus.ABSTAINED and unsupported.dossier is None,
            unsupported.status.value,
        )
    )
    ceiling = engine.infer(build_scenario_request("foundation_assisted"))
    checks.append(
        EvalCheck(
            "claim_ceiling_visible",
            ceiling.dossier is not None
            and bool(ceiling.dossier.claim_ceiling.prohibited_interpretations)
            and any(item.status is DossierDiagnosticStatus.PASS for item in ceiling.diagnostics),
            ceiling.status.value,
        )
    )
    replay = engine.verify(engine.infer(build_scenario_request()))
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            replay.status is MechanismDossierStatus.READY and tamper_rejected,
            "replay and tamper",
        )
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1308AuthorizationError:
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
