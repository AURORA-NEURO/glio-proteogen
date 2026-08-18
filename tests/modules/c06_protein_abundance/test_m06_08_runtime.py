"""Runtime, replay, and adversarial coverage for provisional M06-08."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m06_08 import (
    M0608_M0607_RESULT_MEDIA_TYPE,
    M0608_OUTPUT_MEDIA_TYPE,
    EvidencePublicationStatus,
    ProteinAbundanceEvidenceBundle,
    ProteinAbundanceEvidencePublicationResult,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherDiagnostic,
    PublisherDiagnosticStatus,
    PublishProteinAbundanceEvidenceRequest,
    ReconstructionStatus,
    ReconstructionStep,
    canonical_request_digest,
    canonical_result_digest,
    normalized_request,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608EvidencePublisherAuthorizationError,
    M0608Plugin,
    M0608ReplayVerificationError,
    M0608Service,
    ValidatedM0608Request,
    preflight_evidence_publisher_authorization,
    publish_protein_abundance_evidence,
)


def _artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="0.1.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    controls = _artifact("control", "a")
    identity = _artifact("identity", "b")
    return ExecutionContext(
        request_id="request.m0608",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.config",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity.digest,
                evidence=identity,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("provenance", "c"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent", "d"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("quality", "e"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("support", "f"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("intended", "0"),
            ),
        ),
    )


def request() -> PublishProteinAbundanceEvidenceRequest:
    upstream = _artifact("m0607.result", "1", M0608_M0607_RESULT_MEDIA_TYPE)
    source = _artifact("proteome.source", "2")
    evidence = _artifact("evidence.source", "3")
    return PublishProteinAbundanceEvidenceRequest(
        request_id="request.m0608",
        context=_context(),
        upstream_result=upstream,
        source_artifacts=(source,),
        assumptions=(
            PublisherAssumption(
                assumption_id="assumption.normalization",
                statement="Input intensity values use the approved normalized scale.",
                evidence=(),
            ),
        ),
        counter_evidence=(
            PublisherCounterEvidence(
                counter_evidence_id="counter.batch",
                statement="A batch effect remains possible.",
                impact="The claim must remain reviewable.",
                evidence=(),
            ),
        ),
        reconstruction_steps=(
            ReconstructionStep(
                sequence=1,
                operation="bind_upstream_result",
                input_digests=(upstream.digest, source.digest),
                output_digest=evidence.digest,
                evidence=(),
            ),
        ),
    )


def test_runtime_abstains_without_masquerading_as_negative() -> None:
    result = M0608Service().execute(request())
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.bundle is None
    assert result.explanation is None
    assert result.support_decision.status.value == "review_required"
    assert result.evidence
    assert result.human_review_required
    assert verify_result_digest(result)


def test_replay_verification_is_transitive_and_deterministic() -> None:
    service = M0608Service()
    first = service.execute(request())
    second = service.verify(first)
    assert second == first
    assert second.model_dump_json() == first.model_dump_json()
    assert canonical_request_digest(first.request) == first.request_digest
    assert service.verify(first, replay=False) == first
    assert publish_protein_abundance_evidence(request()) == first
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(object())


def test_tampered_digest_and_payload_are_rejected() -> None:
    service = M0608Service()
    result = service.execute(request())
    tampered = result.model_copy(update={"abstention_reason": "changed"})
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(tampered)
    bad_digest = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises((M0608ReplayVerificationError, ValidationError)):
        service.verify(bad_digest)


def test_receipt_verifier_reports_each_untrusted_model_mutation() -> None:
    service = M0608Service()
    result = service.execute(request())
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    mismatched_request = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    mismatched_request = mismatched_request.model_copy(
        update={"result_digest": result_payload_digest(mismatched_request)}
    )
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(mismatched_request)
    replay_differs = result.model_copy(update={"abstention_reason": "replay differs"})
    replay_differs = replay_differs.model_copy(
        update={"result_digest": result_payload_digest(replay_differs)}
    )
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(replay_differs)
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(replay_differs, replay=False)


def test_canonical_helpers_accept_mapping_projections() -> None:
    result = M0608Service().execute(request())
    projection = result.model_dump(mode="json")
    assert normalized_request(projection["request"])["request_id"] == "request.m0608"
    assert canonical_result_digest(projection) == projection["result_digest"]
    assert verify_result_digest(projection)
    assert not verify_result_digest({"result_digest": "not-a-digest"})


def test_auth_controls_fail_closed_before_validation() -> None:
    candidate = {"context": {"references": {}}, "source_artifacts": []}
    with pytest.raises(M0608EvidencePublisherAuthorizationError):
        M0608Service().execute(candidate)

    class HostileCandidate:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile access")  # noqa: TRY003

    with pytest.raises(M0608EvidencePublisherAuthorizationError):
        preflight_evidence_publisher_authorization(HostileCandidate())


def test_duplicate_sources_and_invalid_media_are_rejected() -> None:
    base = request()
    source = base.source_artifacts[0]
    with pytest.raises(ValidationError):
        base.model_copy(update={"source_artifacts": (source, source)}).model_validate(
            base.model_copy(update={"source_artifacts": (source, source)}), strict=True
        )
    with pytest.raises(ValidationError):
        base.model_copy(update={"upstream_result": _artifact("wrong", "9")}).model_validate(
            base.model_copy(update={"upstream_result": _artifact("wrong", "9")}), strict=True
        )


def test_counter_evidence_role_is_not_silently_rewritten() -> None:
    with pytest.raises(ValidationError):
        PublisherCounterEvidence(
            counter_evidence_id="counter.invalid",
            statement="A conflicting signal exists.",
            impact="Requires review.",
            evidence=(
                {
                    "reference": _artifact("counter", "8"),
                    "role": "evidence",
                    "claim": "wrong role",
                },
            ),
        )


def test_output_media_type_is_not_an_upstream_claim() -> None:
    assert M0608_OUTPUT_MEDIA_TYPE.endswith("+json")


def test_plugin_parse_once_token_and_verification_boundary() -> None:
    service = M0608Service()
    plugin = M0608Plugin(service)
    candidate = request()
    token = plugin.validate(candidate)
    assert isinstance(token, ValidatedM0608Request)
    assert plugin.run(token) == service.execute(candidate)
    assert plugin.verify(plugin.run(token)) == plugin.run(token)
    forged = plugin.run(token).model_copy(update={"abstention_reason": "forged replay"})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(M0608ReplayVerificationError):
        plugin.verify(forged, replay=False)
    serialized = canonical_json_bytes(candidate.model_dump(mode="json"))
    assert plugin.run(plugin.validate(serialized)).status is EvidencePublicationStatus.ABSTAINED
    forged = ValidatedM0608Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    changed = token.request.model_copy(update={"request_id": "request.changed"})
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0608Request(request=changed, _seal=object()))


def test_explicit_evidence_roles_and_diagnostic_statuses_are_preserved() -> None:
    reference = EvidenceReference(
        reference=_artifact("role", "7"),
        role="evidence",
        claim="role-bound source",
    )
    PublisherAssumption(
        assumption_id="assumption.evidence",
        statement="An approved unit normalization is assumed.",
        evidence=(reference,),
    )
    counter_reference = reference.model_copy(update={"role": "counter_evidence"})
    PublisherCounterEvidence(
        counter_evidence_id="counter.evidence",
        statement="A disagreement is present.",
        impact="Review remains required.",
        evidence=(counter_reference,),
    )
    ReconstructionStep(
        sequence=1,
        operation="reconstruct",
        input_digests=(reference.reference.digest,),
        output_digest=reference.reference.digest,
        evidence=(reference,),
    )
    PublisherDiagnostic(
        diagnostic_id="diagnostic.warning",
        status=PublisherDiagnosticStatus.WARNING,
        message="Counter-evidence remains reviewable.",
        evidence=(reference, counter_reference),
    )
    with pytest.raises(ValidationError):
        PublisherAssumption(
            assumption_id="assumption.bad-role",
            statement="Wrong role is rejected.",
            evidence=(counter_reference,),
        )
    with pytest.raises(ValidationError):
        PublisherDiagnostic(
            diagnostic_id="diagnostic.bad-role",
            status=PublisherDiagnosticStatus.FAIL,
            message="Invalid evidence role.",
            evidence=(reference.model_copy(update={"role": "bad"}),),
        )
    with pytest.raises(ValidationError):
        ReconstructionStep(
            sequence=2,
            operation="wrong-role",
            input_digests=(reference.reference.digest,),
            output_digest=reference.reference.digest,
            evidence=(counter_reference,),
        )
    with pytest.raises(ValidationError):
        PublisherDiagnostic(
            diagnostic_id="diagnostic.constructed-bad-role",
            status=PublisherDiagnosticStatus.FAIL,
            message="Invalid constructed role.",
            evidence=(
                EvidenceReference.model_construct(
                    reference=reference.reference,
                    role="invalid",
                    claim="bad",
                ),
            ),
        )


def test_request_order_and_identifier_invariants_are_adversarial() -> None:
    base = request()
    payload = base.model_dump(mode="python")
    step = payload["reconstruction_steps"][0]
    payload["reconstruction_steps"] = (step, step)
    with pytest.raises(ValidationError):
        PublishProteinAbundanceEvidenceRequest.model_validate(payload, strict=True)
    payload = base.model_dump(mode="python")
    payload["assumptions"] = (payload["assumptions"][0], payload["assumptions"][0])
    with pytest.raises(ValidationError):
        PublishProteinAbundanceEvidenceRequest.model_validate(payload, strict=True)
    payload = base.model_dump(mode="python")
    payload["counter_evidence"] = (
        payload["counter_evidence"][0],
        payload["counter_evidence"][0],
    )
    with pytest.raises(ValidationError):
        PublishProteinAbundanceEvidenceRequest.model_validate(payload, strict=True)


def test_complete_bundle_validator_rejects_partial_or_ambiguous_closure() -> None:
    service = M0608Service()
    result = service.execute(request())
    bundle = ProteinAbundanceEvidenceBundle(
        bundle_id="bundle.m0608",
        version="0.1.0",
        upstream_result=request().upstream_result,
        sources=result.evidence,
        assumptions=request().assumptions,
        counter_evidence=request().counter_evidence,
        uncertainty=result.uncertainty,
        support_decision=result.support_decision.model_copy(
            update={"status": SupportStatus.SUPPORTED, "reason_code": "supported"}
        ),
        reconstruction_status=ReconstructionStatus.COMPLETE,
        reconstruction_steps=request().reconstruction_steps,
        provenance=result.provenance,
    )
    assert bundle.reconstruction_status is ReconstructionStatus.COMPLETE
    for update in (
        {"reconstruction_status": ReconstructionStatus.PARTIAL},
        {"upstream_result": _artifact("wrong", "8")},
        {"reconstruction_steps": (request().reconstruction_steps[0],) * 2},
        {"sources": (result.evidence[0].model_copy(update={"role": "counter_evidence"}),)},
        {"sources": (*result.evidence, result.evidence[0])},
        {"assumptions": request().assumptions * 2},
        {"counter_evidence": request().counter_evidence * 2},
    ):
        with pytest.raises(ValidationError):
            ProteinAbundanceEvidenceBundle.model_validate(
                bundle.model_dump(mode="python") | update,
                strict=True,
            )


def test_result_validator_rejects_each_release_closure_gap() -> None:
    result = M0608Service().execute(request())
    updates = (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "result.invalid"}),
        result.model_copy(update={"evidence": ()}),
        result.model_copy(update={"status": EvidencePublicationStatus.PUBLISHED}),
        result.model_copy(
            update={
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.SUPPORTED}
                )
            }
        ),
        result.model_copy(update={"human_review_required": False}),
        result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
    )
    for update in updates:
        with pytest.raises(ValidationError):
            ProteinAbundanceEvidencePublicationResult.model_validate(update, strict=True)
