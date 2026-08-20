"""Adversarial and deterministic runtime tests for provisional M09-08."""

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m09_08 import (
    M0908_M0907_RESULT_MEDIA_TYPE,
    EvidencePublicationStatus,
    PublishComplexActivityEvidenceRequest,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherEvidenceSource,
    PublisherSourceKind,
    ReconstructionStep,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    M0908AuthorizationError,
    M0908EvidencePublisher,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=sha256_digest({"m0908-artifact": name}),
        media_type=media_type,
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    identity = IdentityLineageReference(
        decision_id="decision.identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=_artifact("identity-binding").digest,
        evidence=_artifact("evidence.identity"),
    )
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=identity,
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended_use"),
    )
    return ExecutionContext(
        request_id="request.m09-08",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(
    *,
    include_assumptions: bool = True,
    include_counter_evidence: bool = True,
    include_reconstruction: bool = True,
) -> PublishComplexActivityEvidenceRequest:
    upstream = _artifact("upstream", M0908_M0907_RESULT_MEDIA_TYPE)
    definitions = (
        ("source.ms", PublisherSourceKind.MASS_SPECTROMETRY_PROTEOME),
        ("source.genome", PublisherSourceKind.GENOME_TRANSCRIPTOME),
        ("source.ptm", PublisherSourceKind.PTM_ANNOTATIONS),
        ("source.activity", PublisherSourceKind.UPSTREAM_COMPLEX_ACTIVITY),
        ("source.quality", PublisherSourceKind.QUALITY_SUPPORT),
    )
    sources = tuple(
        PublisherEvidenceSource(
            source_id=source_id,
            kind=kind,
            artifact=_artifact(source_id),
            claim=f"Caller-declared {kind.value} source.",
        )
        for source_id, kind in definitions
    )
    assumptions = (
        (
            PublisherAssumption(
                assumption_id="assumption.units",
                statement="All caller-declared quantities use the approved unit convention.",
            ),
        )
        if include_assumptions
        else ()
    )
    counter_evidence = (
        (
            PublisherCounterEvidence(
                counter_evidence_id="counter.discordance",
                statement="Transcript-protein discordance remains visible for review.",
                impact="No negative finding is inferred from discordance.",
            ),
        )
        if include_counter_evidence
        else ()
    )
    steps: tuple[ReconstructionStep, ...] = ()
    if include_reconstruction:
        inputs = tuple(sorted({upstream.digest, *(item.artifact.digest for item in sources)}))
        output = sha256_digest(
            {
                "module": "GLIO-PROTEOGEN-M09-08",
                "sequence": 1,
                "operation": "assemble_evidence_bundle",
                "input_digests": sorted(inputs),
            }
        )
        steps = (
            ReconstructionStep(
                sequence=1,
                operation="assemble_evidence_bundle",
                input_digests=inputs,
                output_digest=output,
            ),
        )
    return PublishComplexActivityEvidenceRequest(
        request_id="request.m09-08",
        context=_context(),
        upstream_result=upstream,
        source_artifacts=sources,
        assumptions=assumptions,
        counter_evidence=counter_evidence,
        reconstruction_steps=steps,
    )


def test_complete_publication_is_deterministic_and_replayable() -> None:
    engine = M0908EvidencePublisher()
    first = engine.publish(_request())
    second = engine.publish(_request())

    assert first.result.status is EvidencePublicationStatus.PUBLISHED
    assert first.result.bundle is not None
    assert first.result.explanation is not None
    assert first.result.support_decision.status is SupportStatus.SUPPORTED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


@pytest.mark.parametrize(
    ("kwargs", "finding"),
    [
        ({"include_assumptions": False}, "assumptions are required"),
        ({"include_counter_evidence": False}, "counter-evidence is required"),
        ({"include_reconstruction": False}, "reconstruction chain"),
    ],
)
def test_publication_abstains_without_required_review_material(
    kwargs: dict[str, bool], finding: str
) -> None:
    result = M0908EvidencePublisher().publish(_request(**kwargs)).result
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.bundle is None
    assert result.explanation is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason is not None
    assert finding in result.abstention_reason


def test_missing_required_source_kind_abstains_without_negative_inference() -> None:
    request = _request()
    incomplete = request.model_copy(update={"source_artifacts": request.source_artifacts[:-1]})
    result = M0908EvidencePublisher().publish(incomplete).result
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert "missing" in (result.abstention_reason or "")


def test_replay_rejects_tampered_bytes_and_invalid_result() -> None:
    engine = M0908EvidencePublisher()
    built = engine.publish(_request())
    tampered = built.canonical_bytes.replace(b"discordance", b"forged").replace(
        b"No negative finding", b"forged negative"
    )
    assert not engine.verify(built.result, tampered).verified
    assert engine.verify(object()).reason.value == "invalid_result"


def test_replay_rejects_self_rehashed_explanation_mutation() -> None:
    engine = M0908EvidencePublisher()
    built = engine.publish(_request())
    assert built.result.explanation is not None
    explanation = built.result.explanation
    forged_explanation = explanation.model_copy(update={"summary": explanation.summary + " forged"})
    forged = built.result.model_copy(update={"explanation": forged_explanation})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    outcome = engine.verify(forged, canonical_json_bytes(forged.model_dump(mode="json")))

    assert outcome.content_verified is True
    assert outcome.deterministic_verified is False
    assert outcome.verified is False


def test_preflight_rejects_withheld_consent() -> None:
    request = _request()
    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            )
        }
    )
    with pytest.raises(M0908AuthorizationError):
        M0908EvidencePublisher().publish(denied)


def test_request_digest_is_bound_to_exact_request() -> None:
    request = _request()
    built = M0908EvidencePublisher().publish(request)
    assert built.result.request_digest == canonical_request_digest(request)
