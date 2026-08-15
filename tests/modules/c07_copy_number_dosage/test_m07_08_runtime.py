"""Runtime, replay, plugin, and adversarial coverage for provisional M07-08."""

from __future__ import annotations

import pytest
from evals.m07_08.run import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_08 import (
    M0708_M0707_RESULT_MEDIA_TYPE,
    EvidencePublicationStatus,
    ProteotypeEvidenceBundle,
    ProteotypeEvidencePublicationResult,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherDiagnostic,
    PublisherDiagnosticStatus,
    PublishProteotypeEvidenceRequest,
    ReconstructionStatus,
    ReconstructionStep,
    canonical_request_digest,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference, SupportStatus
from glio_proteogen.modules.c07_copy_number_dosage.m07_08_evidence_explanation_publisher import (
    M0708EvidencePublisherAuthorizationError,
    M0708Plugin,
    M0708ReplayVerificationError,
    M0708Service,
    ValidatedM0708Request,
    preflight_evidence_publisher_authorization,
    publish_proteotype_evidence,
)

CONTROL_DECISION_COUNT = 7


def _artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="0.1.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def test_runtime_abstains_without_parent_or_negative_emission() -> None:
    result = M0708Service().execute(build_request())
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.bundle is None
    assert result.explanation is None
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert verify_result_digest(result)
    assert len(result.provenance.control_decisions) == CONTROL_DECISION_COUNT


def test_replay_is_transitive_and_byte_stable() -> None:
    service = M0708Service()
    first = service.execute(build_request())
    second = service.verify(first)
    assert second == first
    assert second.model_dump_json() == first.model_dump_json()
    assert canonical_request_digest(first.request) == first.request_digest
    assert service.verify(first, replay=False) == first
    assert publish_proteotype_evidence(build_request()) == first
    with pytest.raises(M0708ReplayVerificationError):
        service.verify(object())
    assert verify_result_digest({"result_digest": "not-a-digest"}) is False
    assert verify_result_digest({}) is False


def test_tampered_receipt_and_replayed_payload_are_rejected() -> None:
    service = M0708Service()
    result = service.execute(build_request())
    with pytest.raises(M0708ReplayVerificationError):
        service.verify(result.model_copy(update={"abstention_reason": "tampered"}))
    changed = result.model_copy(update={"abstention_reason": "tampered"})
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(M0708ReplayVerificationError):
        service.verify(changed)
    bad_digest = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises((M0708ReplayVerificationError, ValidationError)):
        service.verify(bad_digest)


def test_auth_controls_fail_closed_before_validation() -> None:
    with pytest.raises(M0708EvidencePublisherAuthorizationError):
        M0708Service().execute({"context": {"references": {}}, "source_artifacts": []})

    class HostileCandidate:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile access")  # noqa: TRY003

    with pytest.raises(M0708EvidencePublisherAuthorizationError):
        preflight_evidence_publisher_authorization(HostileCandidate())


def test_plugin_seals_tokens_and_parses_serialized_request_once() -> None:
    service = M0708Service()
    plugin = M0708Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M07-08"
    request = build_request()
    token = plugin.validate(request)
    assert isinstance(token, ValidatedM0708Request)
    assert plugin.run(token) == service.execute(request)
    assert plugin.verify(plugin.run(token)) == plugin.run(token)
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    assert plugin.run(plugin.validate(serialized)).status is EvidencePublicationStatus.ABSTAINED
    forged = ValidatedM0708Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    changed = token.request.model_copy(update={"request_id": "request.changed"})
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0708Request(request=changed, _seal=object()))


def test_wrong_upstream_media_type_and_duplicate_artifacts_are_rejected() -> None:
    request = build_request()
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(
            request.model_dump(mode="python")
            | {"upstream_result": _artifact("wrong", "a")},
            strict=True,
        )
    duplicated = request.model_dump(mode="python")
    duplicated["source_artifacts"] = (
        duplicated["source_artifacts"][0],
        duplicated["source_artifacts"][0],
    )
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(duplicated, strict=True)


def test_evidence_roles_are_never_silently_rewritten() -> None:
    request = build_request()
    reference = EvidenceReference(
        reference=request.source_artifacts[0].artifact,
        role="evidence",
        claim="opaque reference",
    )
    PublisherAssumption(
        assumption_id="assumption.valid",
        statement="Units are owner-approved.",
        evidence=(reference,),
    )
    counter_reference = reference.model_copy(update={"role": "counter_evidence"})
    PublisherCounterEvidence(
        counter_evidence_id="counter.valid",
        statement="A disagreement remains.",
        impact="Promotion requires review.",
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
        diagnostic_id="diagnostic.valid",
        status=PublisherDiagnosticStatus.WARNING,
        message="Review remains required.",
        evidence=(reference, counter_reference),
    )
    with pytest.raises(ValidationError):
        PublisherAssumption(
            assumption_id="assumption.bad",
            statement="Wrong role.",
            evidence=(counter_reference,),
        )
    with pytest.raises(ValidationError):
        PublisherCounterEvidence(
            counter_evidence_id="counter.bad",
            statement="Wrong role.",
            impact="Review.",
            evidence=(reference,),
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
            diagnostic_id="diagnostic.bad",
            status=PublisherDiagnosticStatus.FAIL,
            message="Invalid role.",
            evidence=(reference.model_copy(update={"role": "invalid"}),),
        )


def test_reconstruction_steps_and_identifiers_are_ordered_and_unique() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    step = payload["reconstruction_steps"][0]
    payload["reconstruction_steps"] = (step, step)
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(payload, strict=True)
    payload = request.model_dump(mode="python")
    payload["assumptions"] = (payload["assumptions"][0], payload["assumptions"][0])
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(payload, strict=True)
    payload = request.model_dump(mode="python")
    payload["counter_evidence"] = (
        payload["counter_evidence"][0],
        payload["counter_evidence"][0],
    )
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(payload, strict=True)


def test_provenance_and_controls_are_projected_without_raw_content() -> None:
    result = M0708Service().execute(build_request())
    provenance = result.provenance
    assert provenance.module_id == "GLIO-PROTEOGEN-M07-08"
    assert provenance.input_digests[0] == result.request_digest
    assert all("Opaque" not in item.state for item in provenance.control_decisions)
    assert all(item.role.value for item in provenance.control_decisions)


def test_request_context_request_id_may_not_be_rebound() -> None:
    request = build_request()
    context = request.context.model_copy(update={"request_id": "request.other"})
    with pytest.raises(ValidationError):
        PublishProteotypeEvidenceRequest.model_validate(
            request.model_dump(mode="python") | {"context": context}, strict=True
        )


def test_invalid_result_status_cannot_claim_published_bundle() -> None:
    result = M0708Service().execute(build_request())
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python")
            | {
                "status": EvidencePublicationStatus.PUBLISHED,
                "result_digest": result_payload_digest(result),
            },
            strict=True,
        )


def test_bundle_and_result_release_closures_reject_each_gap() -> None:
    service = M0708Service()
    request = build_request()
    result = service.execute(request)
    bundle = ProteotypeEvidenceBundle(
        bundle_id="bundle.m0708",
        version="0.1.0",
        upstream_result=request.upstream_result,
        sources=request.source_artifacts,
        assumptions=request.assumptions,
        counter_evidence=request.counter_evidence,
        uncertainty=result.uncertainty,
        support_decision=result.support_decision.model_copy(
            update={"status": SupportStatus.SUPPORTED, "reason_code": "supported"}
        ),
        reconstruction_status=ReconstructionStatus.COMPLETE,
        reconstruction_steps=request.reconstruction_steps,
        provenance=result.provenance,
        evidence=result.evidence,
    )
    for update in (
        {"reconstruction_status": ReconstructionStatus.PARTIAL},
        {"upstream_result": _artifact("wrong", "8")},
        {"reconstruction_steps": (request.reconstruction_steps[0],) * 2},
        {"sources": (request.source_artifacts[0], request.source_artifacts[0])},
        {"evidence": (result.evidence[0].model_copy(update={"role": "counter_evidence"}),)},
    ):
        with pytest.raises(ValidationError):
            ProteotypeEvidenceBundle.model_validate(
                bundle.model_dump(mode="python") | update,
                strict=True,
            )
    for update in (
        {"request_digest": "sha256:" + "0" * 64},
        {"result_id": "result.invalid"},
        {"evidence": ()},
        {"human_review_required": False},
        {"result_digest": "sha256:" + "0" * 64},
    ):
        with pytest.raises(ValidationError):
            ProteotypeEvidencePublicationResult.model_validate(
                result.model_dump(mode="python") | update,
                strict=True,
            )


def test_authority_media_constant_remains_provisional() -> None:
    assert M0708_M0707_RESULT_MEDIA_TYPE.endswith("+json")
    assert M0708_M0707_RESULT_MEDIA_TYPE != "application/json"
