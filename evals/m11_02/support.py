"""Synthetic non-clinical request factory shared by M11-02 evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m11_02 import (
    M1102_HYPOTHESIS_MEDIA_TYPE,
    ContextDimension,
    ContextObservation,
    ContextStratificationPolicy,
    ContextStratificationRule,
    StratifyVariantPeptideContextRequest,
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

_DIGEST = "sha256:" + ("a" * 64)
_WHEN = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(reference=artifact(name), role="evidence", claim="synthetic evidence")


def decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact(role),
    )


def context(consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    return ExecutionContext(
        request_id="request.context.synthetic",
        actor_id="actor.m1102.synthetic",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def rule(
    name: str, dimension: ContextDimension, allowed: tuple[str, ...]
) -> ContextStratificationRule:
    return ContextStratificationRule(
        rule_id=f"rule.{name}",
        dimension=dimension,
        criterion=f"declared {dimension.value} is supported",
        allowed_values=allowed,
        prohibited_proxies=("postcode",) if dimension is ContextDimension.DISEASE_CLASS else (),
        evidence=(evidence(f"rule.{name}"),),
    )


def observation(dimension: ContextDimension, value: str, score: float = 0.95) -> ContextObservation:
    return ContextObservation(
        dimension=dimension,
        value=value,
        source_artifact=artifact(f"observation.{dimension.value}"),
        support_score=score,
        evidence=(evidence(f"observation.{dimension.value}"),),
    )


def request(
    disease: str = "glioma",
    disease_score: float = 0.95,
    *,
    include_subtype: bool = True,
    subtype: str = "astrocytoma",
    consent: ConsentState = ConsentState.GRANTED,
) -> StratifyVariantPeptideContextRequest:
    dimensions = [ContextDimension.DISEASE_CLASS]
    rules = [rule("disease", ContextDimension.DISEASE_CLASS, ("glioma",))]
    observations = [observation(ContextDimension.DISEASE_CLASS, disease, disease_score)]
    if include_subtype:
        dimensions.append(ContextDimension.SUBTYPE)
        rules.append(
            rule("subtype", ContextDimension.SUBTYPE, ("astrocytoma", "oligodendroglioma"))
        )
        observations.append(observation(ContextDimension.SUBTYPE, subtype))
    return StratifyVariantPeptideContextRequest(
        request_id="request.m1102.synthetic",
        context=context(consent),
        hypothesis_registry=ArtifactReference(
            artifact_id="artifact.hypotheses",
            version="0.1.0-provisional",
            digest=_DIGEST,
            media_type=M1102_HYPOTHESIS_MEDIA_TYPE,
        ),
        policy=ContextStratificationPolicy(
            policy_id="policy.m1102.synthetic",
            version="1.0.0",
            dimensions=tuple(dimensions),
            rules=tuple(rules),
            minimum_support_score=0.8,
            evidence=(evidence("policy"),),
        ),
        observations=tuple(observations),
        source_artifacts=(artifact("mass-spec"), artifact("genome"), artifact("transcriptome")),
    )
