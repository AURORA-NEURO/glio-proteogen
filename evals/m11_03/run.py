"""Fixture-bound M11-03 evaluator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m11_03 import (
    M1103_M1102_INPUT_MEDIA_TYPE,
    ConstructVariantPeptideMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticValueKind,
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
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor import (  # noqa: E501
    M1103AuthorizationError,
    construct_variant_peptide_mechanistic_features,
    verify_m1103_replay,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "m11_03" / "scenarios.json"


def _artifact(name: str, media: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() * 64)[:64],
        media_type=media,
    )


def request_for(case: dict[str, Any]) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    evidence = _artifact("evidence.control")
    controls = case.get("controls", {})
    refs = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_artifact("identity.binding").digest,
            evidence=evidence,
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState(controls.get("consent", ConsentState.GRANTED)),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=controls.get("quality", UpstreamDecisionState.ACCEPTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.use",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
    )
    context = ExecutionContext(
        request_id="request.m1103.evaluator",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )
    source = _artifact(case.get("source_id", "source.proteome"))
    feature = MechanisticFeature(
        feature_id="pathway.activity",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit=case.get("unit", "activity"),
        scalar_value=0.75,
        lineage=MechanisticFeatureLineage(
            feature_id="pathway.activity",
            source_artifacts=(source,),
            claim="Evaluator pathway feature.",
            transformation_ids=("transform.scale",),
        ),
    )
    config = MechanisticFeatureConfiguration(
        configuration_id="config.m1103.evaluator",
        version="1.0.0",
        model_family="curated-mechanistic-baseline",
        transformation_ids=("transform.scale",),
        topology_reference=_artifact(case.get("topology_id", "topology.reference")),
        negative_control_artifacts=(_artifact(case.get("negative_id", "negative.control")),),
    )
    return ConstructVariantPeptideMechanisticFeaturesRequest(
        request_id=context.request_id,
        context=context,
        upstream_result=_artifact(
            case.get("upstream_id", "result.m1102.supported"), M1103_M1102_INPUT_MEDIA_TYPE
        ),
        configuration=config,
        source_artifacts=(source,),
        declared_features=() if case.get("no_features", False) else (feature,),
    )


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    request = request_for(case)
    if case["case_id"] == "denied_control":
        try:
            construct_variant_peptide_mechanistic_features(request)
        except M1103AuthorizationError:
            return {"case_id": case["case_id"], "passed": True, "outcome": "authorization_rejected"}
        return {
            "case_id": case["case_id"],
            "passed": False,
            "outcome": "authorization_not_rejected",
        }
    result = construct_variant_peptide_mechanistic_features(request)
    expected_status = case["expected_status"]
    status_ok = result.status.value == expected_status
    findings = {item.value for item in result.findings}
    expected_findings = set(case.get("expected_findings", []))
    replay_ok = verify_m1103_replay(result, request)
    tampered_ok = True
    if case["case_id"] == "replay_tamper":
        tampered = request.model_copy(update={"request_id": "request.m1103.tampered"})
        tampered_ok = not verify_m1103_replay(result, tampered)
    passed = status_ok and expected_findings <= findings and replay_ok and tampered_ok
    return {
        "case_id": case["case_id"],
        "passed": passed,
        "status": result.status.value,
        "findings": sorted(findings),
        "replay_verified": replay_ok,
        "tamper_rejected": tampered_ok,
    }


def run_evaluator() -> dict[str, Any]:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    outcomes = [_evaluate_case(case) for case in cases]
    return {
        "module_id": fixture["module_id"],
        "fixture_id": fixture["fixture_id"],
        "fixture_digest": sha256_digest(fixture),
        "declared_case_ids": [case["case_id"] for case in cases],
        "executed_case_ids": [outcome["case_id"] for outcome in outcomes],
        "declared_cases": len(cases),
        "executed_cases": len(outcomes),
        "passed_cases": sum(1 for outcome in outcomes if outcome["passed"]),
        "passed": all(outcome["passed"] for outcome in outcomes),
        "cases": outcomes,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), indent=2, sort_keys=True))  # noqa: T201
