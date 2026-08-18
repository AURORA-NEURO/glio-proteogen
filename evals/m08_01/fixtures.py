"""Closed synthetic requests for M08-01 evaluation and benchmark use."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m08_01 import (
    FormalTranscriptProteinStateSchema,
    TranscriptProteinFeatureDefinition,
    TranscriptProteinFeatureValue,
    TranscriptProteinFeatureValueKind,
    TranscriptProteinInvariant,
    TranscriptProteinInvariantSeverity,
    TranscriptProteinMissingness,
    ValidateTranscriptProteinStateRequest,
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


def artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() + "0" * 64)[:64],
        media_type="application/json",
    )


def request(
    *,
    scalar: float = 2.0,
    missingness: TranscriptProteinMissingness = TranscriptProteinMissingness.OBSERVED,
    expression: str = "feature:discordance.scalar >= 1",
    severity: TranscriptProteinInvariantSeverity = TranscriptProteinInvariantSeverity.ERROR,
    consent: ConsentState = ConsentState.GRANTED,
) -> ValidateTranscriptProteinStateRequest:
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
    definition = TranscriptProteinFeatureDefinition(
        feature_id="discordance.scalar",
        version="1.0.0",
        value_kind=TranscriptProteinFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(
            (TranscriptProteinMissingness.OBSERVED,)
            if missingness is TranscriptProteinMissingness.OBSERVED
            else (TranscriptProteinMissingness.OBSERVED, missingness)
        ),
        domain_lower=0.0,
    )
    value = TranscriptProteinFeatureValue(
        feature_id=definition.feature_id,
        state=missingness,
        unit=definition.unit,
        scalar_value=scalar if missingness is TranscriptProteinMissingness.OBSERVED else None,
    )
    invariant = TranscriptProteinInvariant(
        invariant_id="invariant.minimum",
        expression=expression,
        severity=severity,
        feature_ids=(definition.feature_id,),
    )
    return ValidateTranscriptProteinStateRequest(
        request_id="request.m0801",
        context=context,
        state_schema=FormalTranscriptProteinStateSchema(
            schema_id="schema.discordance",
            version="1.0.0",
            features=(definition,),
            invariants=(invariant,),
        ),
        values=(value,),
        source_artifacts=(artifact("source.state"),),
    )
