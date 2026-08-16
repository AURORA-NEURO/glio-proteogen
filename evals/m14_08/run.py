"""Deterministic M14-08 evaluator over frozen mechanism dossier scenarios."""

# Evaluator matrix intentionally keeps protocol cases explicit.
# ruff: noqa: E501, TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m14_08 import (
    M1408_M1407_RESULT_MEDIA_TYPE,
    ClaimLevel,
    DossierConfiguration,
    DossierStatus,
    EvidenceDisposition,
    EvidenceLink,
    EvidenceLinkKind,
    MechanismClaim,
    MechanismEvidenceDossier,
    PublishProteinSubtypeMechanismDossierRequest,
    ValidationRoute,
    ValidationRouteKind,
    ValidationRouteStatus,
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
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_08_mechanism_evidence_dossier import (
    M1408DossierAuthorizationError,
    M1408DossierEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M14-08"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m14_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "review_ready",
    "counter_evidence_chain",
    "validation_required_abstention",
    "unresolved_link_abstention",
    "unsupported_method_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1408_fixture": label})


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


def _evidence(label: str, role: str = "evidence") -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role=role,
            claim="Frozen caller-declared mechanism dossier evidence.",
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    method: str = "evidence_graph",
    route_status: ValidationRouteStatus = ValidationRouteStatus.COMPLETE,
    disposition: EvidenceDisposition = EvidenceDisposition.SUPPORTED,
) -> PublishProteinSubtypeMechanismDossierRequest:
    """Build a genuine typed request from caller-declared references only."""

    link_input = EvidenceLink(
        link_id="link.input",
        kind=EvidenceLinkKind.INPUT,
        source_artifact=_artifact("input"),
        target_id="mechanism.alpha",
        claim="Input proteogenomic context is bound to the mechanism claim.",
        disposition=disposition,
        counter_evidence=_evidence("counter.input", "counter_evidence"),
        evidence=_evidence("evidence.input"),
    )
    link_mechanism = EvidenceLink(
        link_id="link.mechanism",
        kind=EvidenceLinkKind.MECHANISM,
        source_artifact=_artifact("mechanism"),
        target_id="mechanism.alpha",
        claim="Mechanism link is preserved for reviewer reconstruction.",
        disposition=disposition,
        counter_evidence=_evidence("counter.mechanism", "counter_evidence"),
        evidence=_evidence("evidence.mechanism"),
    )
    claim = MechanismClaim(
        claim_id="claim.alpha",
        mechanism_id="mechanism.alpha",
        statement="Mechanism alpha is supported within the declared evidence ceiling.",
        level=ClaimLevel.SUPPORTED_MECHANISM,
        claim_ceiling="Review-ready mechanism hypothesis; no treatment recommendation.",
        required_link_ids=("link.input", "link.mechanism"),
        counter_evidence=_evidence("counter.claim", "counter_evidence"),
        evidence=_evidence("evidence.claim"),
    )
    route = ValidationRoute(
        route_id="route.orthogonal",
        kind=ValidationRouteKind.ORTHOGONAL_ASSAY,
        objective="Confirm mechanism alpha using an orthogonal assay.",
        next_experiment="Run the preregistered orthogonal assay.",
        status=route_status,
        evidence=_evidence("evidence.route"),
    )
    dossier = MechanismEvidenceDossier(
        dossier_id="dossier.m1408",
        version="1.0.0",
        links=(link_input, link_mechanism),
        claims=(claim,),
        validation_routes=(route,),
        material_assumptions=("Caller-declared references are immutable and not traversed.",),
        claim_ceiling="Review-ready mechanism evidence only; treatment is prohibited.",
        evidence=_evidence("evidence.dossier"),
    )
    configuration = DossierConfiguration(
        configuration_id="configuration.m1408",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        evidence=_evidence("evidence.configuration"),
    )
    return PublishProteinSubtypeMechanismDossierRequest(
        request_id="request.m1408",
        context=ExecutionContext(
            request_id="request.m1408",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        upstream_mechanism_result=_artifact("m1407-result", M1408_M1407_RESULT_MEDIA_TYPE),
        configuration=configuration,
        dossier=dossier,
        source_artifacts=(_artifact("counter-source"),),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M14-08 fixture case IDs are not locked")
    engine = M1408DossierEngine()
    checks: list[EvalCheck] = []
    ready = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck("review_ready", ready.status is DossierStatus.REVIEW_READY, ready.status.value)
    )
    chain = engine.infer(build_scenario_request(disposition=EvidenceDisposition.LIMITED))
    checks.append(
        EvalCheck(
            "counter_evidence_chain", chain.status is DossierStatus.REVIEW_READY, chain.status.value
        )
    )
    required = engine.infer(build_scenario_request(route_status=ValidationRouteStatus.REQUIRED))
    checks.append(
        EvalCheck(
            "validation_required_abstention",
            required.status is DossierStatus.ABSTAINED,
            required.abstention_reason or "",
        )
    )
    unresolved = engine.infer(build_scenario_request(disposition=EvidenceDisposition.UNRESOLVED))
    checks.append(
        EvalCheck(
            "unresolved_link_abstention",
            unresolved.status is DossierStatus.ABSTAINED,
            unresolved.abstention_reason or "",
        )
    )
    unsupported = engine.infer(build_scenario_request(method="unregistered_method"))
    checks.append(
        EvalCheck(
            "unsupported_method_abstention",
            unsupported.status is DossierStatus.ABSTAINED,
            unsupported.abstention_reason or "",
        )
    )
    replay = engine.verify(ready)
    tamper_rejected = False
    try:
        engine.verify(ready.model_copy(update={"result_digest": _digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck("replay_and_tamper", replay == ready and tamper_rejected, "replay and tamper")
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1408DossierAuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(c.passed for c in checks),
        "total_cases": len(checks),
        "passed": all(c.passed for c in checks),
    }


def main() -> int:
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
