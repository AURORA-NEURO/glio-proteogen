"""Closed synthetic baseline requests."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m08_03 import (
    M0803_M0802_RESULT_MEDIA_TYPE,
    BaselineFeatureObservation,
    BaselineFeatureState,
    BaselineMethod,
    BaselineRunConfiguration,
    EstimateProteinSubtypeBaselineRequest,
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


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() + "0" * 64)[:64],
        media_type=media_type,
    )


def request(
    *,
    values: tuple[float, ...] = (0.8, 0.4),
    feature_state: BaselineFeatureState = BaselineFeatureState.OBSERVED,
    source_name: str = "source.transcript-protein",
    consent: ConsentState = ConsentState.GRANTED,
) -> EstimateProteinSubtypeBaselineRequest:
    evidence = artifact("control-evidence")

    def accepted(name: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=name,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        )

    context = ExecutionContext(
        request_id="request.context",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("decision.config"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=evidence,
            ),
            provenance=accepted("decision.provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted("decision.quality"),
            support=accepted("decision.support"),
            intended_use=accepted("decision.intended"),
        ),
    )
    configuration = BaselineRunConfiguration(
        configuration_id="config.m0803.baseline",
        version="1.0.0",
        method=BaselineMethod.STATISTICAL_RULE_BASED,
        preprocessing_artifact=artifact("preprocessing.locked"),
        tuning_artifact=artifact("tuning.locked"),
        uncertainty_artifact=artifact("calibration.locked"),
        benchmark_artifact=artifact("benchmark.locked"),
    )
    features = tuple(
        BaselineFeatureObservation(
            feature_id=f"discordance.feature.{index}",
            state=feature_state,
            unit="z-score",
            value=value if feature_state is BaselineFeatureState.OBSERVED else None,
            evidence=(
                EvidenceReference(
                    reference=evidence,
                    role="evidence",
                    claim="synthetic baseline feature fixture",
                ),
            ),
        )
        for index, value in enumerate(values, start=1)
    )
    return EstimateProteinSubtypeBaselineRequest(
        request_id="request.m0803",
        context=context,
        representation_result=artifact("representation.m0802", M0803_M0802_RESULT_MEDIA_TYPE),
        configuration=configuration,
        features=features,
        source_artifacts=(artifact(source_name),),
    )
