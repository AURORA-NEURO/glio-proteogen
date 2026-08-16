"""Adversarial runtime and replay tests for M10-08."""

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m10_08.v1 import (
    EvidencePublicationStatus,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherEvidenceSource,
    PublisherSourceKind,
    PublishProteinRnaEvidenceRequest,
    ReconstructionStep,
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
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(identifier: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _decision(identifier: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=identifier,
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{identifier}"),
    )


def _request(
    *,
    complete: bool = True,
    accepted: bool = True,
) -> PublishProteinRnaEvidenceRequest:
    references = ContextReferences(
        approved_configuration=_decision("configuration")
        if accepted
        else _decision("configuration").model_copy(
            update={"state": UpstreamDecisionState.REJECTED}
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="lineage",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=_artifact("evidence.lineage"),
        ),
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended-use"),
    )
    context = ExecutionContext(
        request_id="request.m1008",
        actor_id="actor.m1008",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=references,
    )
    evidence = EvidenceReference(
        reference=_artifact("evidence.publisher"),
        role="evidence",
        claim="Caller-declared evidence receipt.",
    )
    sources = tuple(
        PublisherEvidenceSource(
            source_id=f"source.{index}",
            kind=kind,
            artifact=_artifact(f"source-artifact.{index}"),
            claim="Caller-declared source; external authority is not inferred.",
            evidence=(evidence,),
        )
        for index, kind in enumerate(PublisherSourceKind)
    )
    return PublishProteinRnaEvidenceRequest(
        request_id="request.m1008",
        context=context,
        upstream_result=_artifact(
            "upstream.m1007",
            "application/vnd.glio-proteogen.m10-07+json",
        ),
        source_artifacts=sources,
        assumptions=(
            (
                PublisherAssumption(
                    assumption_id="assumption.units",
                    statement="Caller declares units are already reviewed.",
                    evidence=(evidence,),
                ),
            )
            if complete
            else ()
        ),
        counter_evidence=(
            (
                PublisherCounterEvidence(
                    counter_evidence_id="counter.discordance",
                    statement="Caller declares discordant evidence remains visible.",
                    impact="Requires human review.",
                    evidence=(evidence,),
                ),
            )
            if complete
            else ()
        ),
        reconstruction_steps=(
            (
                ReconstructionStep(
                    sequence=1,
                    operation="bind-caller-evidence",
                    input_digests=(_DIGEST,),
                    output_digest=_DIGEST,
                    evidence=(evidence,),
                ),
            )
            if complete
            else ()
        ),
    )


def test_complete_publication_is_closed_and_replayable() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    assert result.status is EvidencePublicationStatus.PUBLISHED
    assert result.bundle is not None
    assert result.explanation is not None
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert m1008_runtime.verify_publication_result(result)
    assert result.model_dump(mode="json") == m1008_runtime.publish_protein_rna_evidence(
        _request()
    ).model_dump(mode="json")


def test_incomplete_publication_abstains_without_bundle() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request(complete=False))
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.bundle is None
    assert result.explanation is None
    assert result.human_review_required is True
    assert "missing_attribution" in {item.value for item in result.findings}
    assert m1008_runtime.verify_publication_result(result)


def test_unaccepted_control_fails_before_publication() -> None:
    with pytest.raises(m1008_runtime.M1008AuthorizationError):
        m1008_runtime.publish_protein_rna_evidence(_request(accepted=False))


def test_tampered_result_is_rejected() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    assert not m1008_runtime.M1008EvidencePublisherService.verify(tampered)


def test_plugin_is_parse_once_and_rejects_duplicate_json() -> None:
    request_json = _request().model_dump_json()
    plugin = m1008_runtime.M1008EvidencePublisherPlugin(
        m1008_runtime.M1008EvidencePublisherService()
    )
    validated = plugin.validate(request_json)
    assert isinstance(validated, m1008_runtime.ValidatedM1008Request)
    assert plugin.run(validated).result_id.startswith("result.m1008.")
    with pytest.raises(StrictJsonError):
        strict_json_loads('{"request_id":"one","request_id":"two"}')


def test_wrong_upstream_media_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="provisional M10-07"):
        m1008_runtime.publish_protein_rna_evidence(
            _request().model_copy(
                update={"upstream_result": _artifact("wrong", "application/json")}
            )
        )
