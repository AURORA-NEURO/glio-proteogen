# ruff: noqa: E501, T201
"""Run the M10-02 evaluator matrix without external artifact traversal."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from glio_proteogen.contracts.m10_02 import (
    ConstructProteinRnaRepresentationRequest,
    RepresentationConfiguration,
    RepresentationFeatureValueKind,
    RepresentationInputFeature,
    RepresentationMethod,
    RepresentationMissingness,
    TransformationStep,
)
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
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (
    construct_protein_rna_representation,
    verify_result_replay,
)


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{hashlib.sha256(name.encode()).hexdigest()}",
        media_type=media_type,
    )


def upstream(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact(f"ev{name}"),
    )


def request(
    state: RepresentationMissingness, operation: str = "identity"
) -> ConstructProteinRnaRepresentationRequest:
    source = artifact("source")
    return ConstructProteinRnaRepresentationRequest(
        request_id="request.m1002.eval",
        context=ExecutionContext(
            request_id="request.m1002.eval",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
            references=ContextReferences(
                approved_configuration=upstream("configuration"),
                identity_lineage=IdentityLineageReference(
                    decision_id="decision.identity",
                    state=IdentityLineageState.RESOLVED,
                    policy_version="1.0.0",
                    binding_digest=artifact("identity").digest,
                    evidence=artifact("identityev"),
                ),
                provenance=upstream("provenance"),
                consent=ConsentReference(
                    decision_id="decision.consent",
                    state=ConsentState.GRANTED,
                    policy_version="1.0.0",
                    evidence=artifact("consentev"),
                ),
                quality=upstream("quality"),
                support=upstream("support"),
                intended_use=upstream("intended"),
            ),
        ),
        formal_state_schema=artifact("formal", "application/vnd.glio-proteogen.m10-01+json"),
        configuration=RepresentationConfiguration(
            configuration_id="config.m1002.eval",
            version="1.0.0",
            method=RepresentationMethod.ELASTIC_NET_CONSEQUENCE,
            transformations=(
                TransformationStep(
                    transformation_id="transform.eval",
                    operation=operation,
                    input_feature_ids=("protein.alpha",),
                    output_feature_ids=("representation.alpha",),
                    fit_scope="none",
                ),
            ),
        ),
        input_features=(
            RepresentationInputFeature(
                feature_id="protein.alpha",
                value_kind=RepresentationFeatureValueKind.SCALAR,
                state=state,
                unit="log2_ratio",
                scalar_value=1.5 if state is RepresentationMissingness.OBSERVED else None,
            ),
        ),
        source_artifacts=(source,),
    )


def evaluate() -> dict[str, Any]:
    supported = construct_protein_rna_representation(request(RepresentationMissingness.OBSERVED))
    abstained = construct_protein_rna_representation(request(RepresentationMissingness.UNSUPPORTED))
    unsupported_operation = construct_protein_rna_representation(
        request(RepresentationMissingness.OBSERVED, "not-a-method")
    )
    replay = verify_result_replay(supported)
    return {
        "module": "GLIO-PROTEOGEN-M10-02",
        "contract_version": "0.1.0-provisional",
        "cases": {
            "supported_constructed": supported.status.value == "constructed",
            "unsupported_abstained": abstained.status.value == "abstained",
            "unsupported_operation_abstained": unsupported_operation.status.value == "abstained",
            "lineage_complete": bool(
                supported.representation and supported.representation.lineage_complete
            ),
            "replay_verified": replay,
            "parent_not_emitted": supported.emits_parent is False,
        },
    }


def main() -> int:
    report = evaluate()
    if not all(report["cases"].values()):
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
