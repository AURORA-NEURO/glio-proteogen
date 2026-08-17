"""Deterministic M16-04 evaluator over frozen intended-use scenarios."""

# ruff: noqa: TRY003, T201

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

from glio_proteogen.contracts.m16_04 import (
    M1604_M1601_RESULT_MEDIA_TYPE,
    AdapterConfiguration,
    AdapterStatus,
    AdaptProteinRnaDiscordanceIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantic,
    EvidenceTier,
    IntendedUseAudience,
    IntendedUseContext,
    IntendedUsePolicy,
    PolicyDecisionStatus,
    canonical_request_digest,
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
from glio_proteogen.modules.c16_protein_rna_discordance.m16_04_intended_use_adapter import (
    M1604AuthorizationError,
    M1604IntendedUseAdapterEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M16-04"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m16_04" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "adapted_validated_policy",
    "qualified_exploratory_policy",
    "prohibited_claim_abstention",
    "hidden_display_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1604_fixture": label})


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
            claim="Frozen caller-declared M16-04 intended-use evidence.",
        ),
    )


def _policy(
    *,
    tier: EvidenceTier = EvidenceTier.VALIDATED,
    ceiling: ClaimCeiling = ClaimCeiling.DESCRIPTIVE,
    display: DisplaySemantic = DisplaySemantic.QUALIFIED,
    permitted: tuple[str, ...] = ("Describe protein-RNA discordance for scientific review.",),
) -> IntendedUsePolicy:
    return IntendedUsePolicy(
        policy_id="policy.m1604",
        version="1.0.0",
        context=IntendedUseContext.SCIENTIFIC_VALIDATION,
        audience=IntendedUseAudience.SCIENTIFIC_REVIEWER,
        minimum_evidence_tier=tier,
        maximum_claim_ceiling=ceiling,
        display_semantic=display,
        permitted_claims=permitted,
        prohibited_claims=(
            "Do not infer kinase activity.",
            "Do not recommend treatment.",
            "Do not infer identity or consent.",
        ),
        configuration=AdapterConfiguration(
            configuration_id="configuration.m1604",
            version="1.0.0",
            method="typed_service_oriented_integration",
            model_reference=_artifact(
                "model",
                "application/vnd.glio-proteogen.model+json",
            ),
            evidence=_evidence("configuration"),
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    policy: IntendedUsePolicy | None = None,
) -> AdaptProteinRnaDiscordanceIntendedUseRequest:
    return AdaptProteinRnaDiscordanceIntendedUseRequest(
        request_id="request.m1604",
        context=ExecutionContext(
            request_id="request.m1604",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        upstream_resolution_result=_artifact(
            "upstream-resolution", M1604_M1601_RESULT_MEDIA_TYPE
        ),
        policy=policy or _policy(),
        source_artifacts=(_artifact("source-proteome"), _artifact("source-transcriptome")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M16-04 fixture case IDs are not locked")
    engine = M1604IntendedUseAdapterEngine()
    checks: list[EvalCheck] = []
    adapted = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "adapted_validated_policy",
            adapted.status is AdapterStatus.ADAPTED
            and adapted.intended_use_object is not None
            and adapted.policy_decision.status is PolicyDecisionStatus.ALLOWED,
            adapted.status.value,
        )
    )
    qualified = engine.infer(
        build_scenario_request(policy=_policy(tier=EvidenceTier.EXPLORATORY))
    )
    checks.append(
        EvalCheck(
            "qualified_exploratory_policy",
            qualified.status is AdapterStatus.ADAPTED
            and qualified.policy_decision.status is PolicyDecisionStatus.QUALIFIED,
            qualified.policy_decision.status.value,
        )
    )
    forbidden = engine.infer(
        build_scenario_request(
            policy=_policy(permitted=("Recommend treatment for this patient.",))
        )
    )
    checks.append(
        EvalCheck(
            "prohibited_claim_abstention",
            forbidden.status is AdapterStatus.ABSTAINED
            and forbidden.intended_use_object is None,
            forbidden.abstention_reason or "",
        )
    )
    hidden = engine.infer(
        build_scenario_request(
            policy=_policy(ceiling=ClaimCeiling.ABSTAIN, display=DisplaySemantic.HIDDEN)
        )
    )
    checks.append(
        EvalCheck(
            "hidden_display_abstention",
            hidden.status is AdapterStatus.ABSTAINED
            and hidden.human_review_required,
            hidden.abstention_reason or "",
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
    except M1604AuthorizationError:
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
        "request_digest": canonical_request_digest(build_scenario_request()),
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
