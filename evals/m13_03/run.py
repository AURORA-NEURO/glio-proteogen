"""Fixture-bound M13-03 evaluator."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m13_03 import (
    M1303_M1302_INPUT_MEDIA_TYPE,
    ConstructProteotypeMechanisticFeaturesRequest,
    MechanisticFeatureConfiguration,
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
    m13_03_mechanistic_feature_constructor as m1303,
)

MechanisticFeatureAuthorizationError = m1303.MechanisticFeatureAuthorizationError
construct_proteotype_mechanistic_features = m1303.construct_proteotype_mechanistic_features
verify_mechanistic_feature_replay = m1303.verify_mechanistic_feature_replay

FIXTURE_PATH: Final = Path(__file__).parents[2] / "tests" / "fixtures" / "m13_03" / "scenarios.json"


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m13-03": label}),
        media_type=media_type,
    )


def _upstream(
    label: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{label}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{label}"),
    )


def build_request(
    *,
    source_label: str = "source.proteome",
    negative_label: str = "negative.control",
    control_state: str = "accepted",
) -> ConstructProteotypeMechanisticFeaturesRequest:
    quality = _upstream("quality", UpstreamDecisionState(control_state))
    references = ContextReferences(
        approved_configuration=_upstream("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=sha256_digest({"subject": "opaque"}),
            evidence=_artifact("evidence.identity"),
        ),
        provenance=_upstream("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=quality,
        support=_upstream("support"),
        intended_use=_upstream("intended-use"),
    )
    context = ExecutionContext(
        request_id="context.m1303",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=references,
    )
    configuration = MechanisticFeatureConfiguration(
        configuration_id="configuration.m1303",
        version="1.0.0",
        model_family="curated-rule",
        transformation_ids=("transform.normalize",),
        pathway_reference=_artifact("pathway.reference"),
        negative_control_artifacts=(_artifact(negative_label),),
    )
    return ConstructProteotypeMechanisticFeaturesRequest(
        request_id="request.m1303.evaluator",
        context=context,
        upstream_result=_artifact("upstream", M1303_M1302_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact(source_label),),
    )


def run_evaluator(fixture_path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    scenarios = fixture["scenarios"]
    results: list[dict[str, object]] = []
    for scenario in scenarios:
        case_id = scenario["id"]
        if case_id == "replay_tamper":
            result = construct_proteotype_mechanistic_features(build_request())
            tampered = result.model_copy(update={"findings": ()})
            try:
                verify_mechanistic_feature_replay(tampered)
            except ValueError:
                passed = True
            else:
                passed = False
            results.append({"id": case_id, "passed": passed, "observed": "tamper_rejected"})
            continue
        request = build_request(
            source_label=scenario["source_label"],
            negative_label=scenario["negative_label"],
            control_state=scenario.get("control_state", "accepted"),
        )
        try:
            result = construct_proteotype_mechanistic_features(request)
        except MechanisticFeatureAuthorizationError:
            observed = "authorization_failed"
        else:
            observed = result.status.value
        results.append(
            {"id": case_id, "passed": observed == scenario["expected_status"], "observed": observed}
        )
    fixture_digest = sha256_digest(fixture)
    passed_cases = sum(bool(item["passed"]) for item in results)
    return {
        "module_id": "GLIO-PROTEOGEN-M13-03",
        "fixture_digest": fixture_digest,
        "declared_cases": len(scenarios),
        "executed_cases": len(results),
        "passed_cases": passed_cases,
        "all_passed": passed_cases == len(results),
        "cases": results,
    }
