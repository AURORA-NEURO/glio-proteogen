"""Deterministic M15-03 evaluator over frozen mechanistic feature scenarios."""

# The matrix intentionally keeps protocol cases explicit.
# ruff: noqa: E501, TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m15_03 import (
    M1503_M1502_RESULT_MEDIA_TYPE,
    ConstructComplexActivityMechanisticFeaturesRequest,
    FeatureConstructorConfiguration,
    FeatureConstructorPolicy,
    FeatureKind,
    FeatureSupportStatus,
    MechanisticFeature,
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
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype.m15_03_mechanistic_feature_constructor import (
    M1503AuthorizationError,
    M1503FeatureConstructorEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M15-03"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m15_03" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "constructed_supported",
    "limited_feature_support",
    "unit_domain_abstention",
    "conflicted_feature_abstention",
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
    return sha256_digest({"m1503_fixture": label})


def _artifact(
    label: str,
    media_type: str = "application/vnd.glio-proteogen.evidence+json",
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
            claim="Frozen caller-declared mechanistic feature evidence.",
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    method: str = "mechanistic_baseline",
    unit: str = "activity",
    support_status: FeatureSupportStatus = FeatureSupportStatus.SUPPORTED,
) -> ConstructComplexActivityMechanisticFeaturesRequest:
    """Build a genuine typed request from caller-declared feature material."""

    feature = MechanisticFeature(
        feature_id="feature.pathway-alpha",
        kind=FeatureKind.PATHWAY,
        label="pathway alpha activity",
        value="0.80",
        numeric_value=0.8,
        unit=unit,
        support_status=support_status,
        source_artifacts=(_artifact("feature-source"),),
        evidence=_evidence("feature-evidence"),
    )
    configuration = FeatureConstructorConfiguration(
        configuration_id="configuration.m1503",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        units_reference=_artifact("units", "application/vnd.glio-proteogen.units+json"),
        evidence=_evidence("configuration-evidence"),
    )
    return ConstructComplexActivityMechanisticFeaturesRequest(
        request_id="request.m1503",
        context=ExecutionContext(
            request_id="request.m1503",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        longitudinal_recurrence_result=_artifact("m1502-result", M1503_M1502_RESULT_MEDIA_TYPE),
        policy=FeatureConstructorPolicy(maximum_features=8, configuration=configuration),
        candidate_features=(feature,),
        source_artifacts=(_artifact("source-proteome"), _artifact("source-transcriptome")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M15-03 fixture case IDs are not locked")
    engine = M1503FeatureConstructorEngine()
    checks: list[EvalCheck] = []
    constructed = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "constructed_supported",
            constructed.feature_object is not None,
            constructed.status.value,
        )
    )
    limited = engine.infer(build_scenario_request(support_status=FeatureSupportStatus.LIMITED))
    checks.append(
        EvalCheck(
            "limited_feature_support", limited.feature_object is not None, limited.status.value
        )
    )
    unit_abstained = engine.infer(build_scenario_request(unit="kelvin"))
    checks.append(
        EvalCheck(
            "unit_domain_abstention",
            unit_abstained.feature_object is None,
            unit_abstained.abstention_reason or "",
        )
    )
    conflicted = engine.infer(
        build_scenario_request(support_status=FeatureSupportStatus.CONFLICTED)
    )
    checks.append(
        EvalCheck(
            "conflicted_feature_abstention",
            conflicted.feature_object is None,
            conflicted.abstention_reason or "",
        )
    )
    unsupported = engine.infer(build_scenario_request(method="unregistered_method"))
    checks.append(
        EvalCheck(
            "unsupported_method_abstention",
            unsupported.feature_object is None,
            unsupported.abstention_reason or "",
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
    except M1503AuthorizationError:
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
