"""Negative and adversarial M09-08 contract/runtime coverage."""

# Long import paths and assertions retain module ownership in this focused suite.
# ruff: noqa: E501

import pytest
from pydantic import ValidationError

import glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher.engine as engine_module
from glio_proteogen.contracts.m09_08 import (
    ComplexActivityEvidenceBundle,
    ComplexActivityEvidencePublicationVerification,
    ComplexActivityExplanation,
    PublicationReplayReason,
    PublishComplexActivityEvidenceRequest,
    PublisherEvidenceSource,
    PublisherSourceKind,
    ReconstructionStatus,
)
from glio_proteogen.contracts.m09_08.canonical import canonical_request_digest
from glio_proteogen.kernel.models import (
    EvidenceReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    BuiltM0908Result,
    M0908EvidencePublisher,
)
from tests.modules.c09_complex_stoichiometry.test_m09_08_publisher import _artifact, _request


def test_request_rejects_duplicate_source_artifact_digests() -> None:
    request = _request()
    duplicate = PublisherEvidenceSource(
        source_id="source.duplicate",
        kind=PublisherSourceKind.QUALITY_SUPPORT,
        artifact=request.source_artifacts[0].artifact,
        claim="Duplicate artifact should be rejected.",
    )
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts, duplicate)
    with pytest.raises(ValueError, match="artifact digests"):
        type(request).model_validate(payload)


def test_wrong_reconstruction_digest_abstains() -> None:
    request = _request()
    step = request.reconstruction_steps[0].model_copy(
        update={"output_digest": _artifact("wrong").digest}
    )
    result = (
        M0908EvidencePublisher()
        .publish(request.model_copy(update={"reconstruction_steps": (step,)}))
        .result
    )
    assert result.status.value == "abstained"
    assert "reconstruction" in (result.abstention_reason or "")


def test_critical_counter_evidence_requires_human_review() -> None:
    request = _request()
    counter = request.counter_evidence[0].model_copy(
        update={"statement": "Critical unresolved biological conflict remains."}
    )
    result = (
        M0908EvidencePublisher()
        .publish(request.model_copy(update={"counter_evidence": (counter,)}))
        .result
    )
    assert result.status.value == "published"
    assert result.human_review_required
    assert result.explanation is not None
    diagnostic = next(
        item
        for item in result.explanation.diagnostics
        if item.diagnostic_id == "diagnostic.counter-evidence"
    )
    assert diagnostic.status.value == "warning"


def test_verify_rejects_wrong_canonical_type_and_oversized_bytes() -> None:
    engine = M0908EvidencePublisher()
    result = engine.publish(_request())
    wrong_type = engine.verify(result.result, bytearray(result.canonical_bytes))
    oversized = engine.verify(result.result, b"x" * (8 * 1024 * 1024 + 1))
    assert wrong_type.reason is PublicationReplayReason.NON_CANONICAL
    assert oversized.reason is PublicationReplayReason.OVERSIZED
    assert not wrong_type.verified
    assert not oversized.verified


def test_verification_flags_cannot_claim_digest_for_failure() -> None:
    with pytest.raises(ValueError, match="digest"):
        ComplexActivityEvidencePublicationVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=_artifact("digest").digest,
            reason=PublicationReplayReason.INVALID_RESULT,
        )
    with pytest.raises(ValueError, match="verified"):
        ComplexActivityEvidencePublicationVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=_artifact("digest").digest,
            reason=PublicationReplayReason.VERIFIED,
        )


def test_canonical_projection_accepts_mapping_and_explanation_duplicates_fail() -> None:
    request = _request()
    assert canonical_request_digest({"request_id": request.request_id}).startswith("sha256:")
    explanation = M0908EvidencePublisher().publish(request).result.explanation
    assert explanation is not None
    payload = explanation.model_dump(mode="python")
    payload["assumptions"] = ("assumption.units", "assumption.units")
    with pytest.raises(ValidationError, match="assumption identifiers"):
        ComplexActivityExplanation.model_validate(payload)
    payload = explanation.model_dump(mode="python")
    payload["counter_evidence"] = ("counter.discordance", "counter.discordance")
    with pytest.raises(ValidationError, match="counter-evidence identifiers"):
        ComplexActivityExplanation.model_validate(payload)


def test_bundle_closures_reject_invalid_media_duplicates_and_partial_state() -> None:
    bundle = M0908EvidencePublisher().publish(_request()).result.bundle
    assert bundle is not None

    cases = [
        ({"upstream_result": _artifact("wrong", "application/wrong")}, "media type"),
        ({"sources": (bundle.sources[0], bundle.sources[0])}, "identifiers"),
        (
            {
                "sources": (
                    bundle.sources[0].model_copy(
                        update={
                            "evidence": (
                                EvidenceReference(
                                    reference=bundle.sources[0].artifact,
                                    role="evidence",
                                    claim="duplicate",
                                ),
                            )
                        }
                    ),
                )
            },
            "sources",
        ),
        ({"reconstruction_status": ReconstructionStatus.PARTIAL}, "complete reconstruction"),
        ({"evidence": ()}, "bundle evidence"),
    ]
    for updates, expected_match in cases:
        match_pattern = expected_match
        if expected_match == "sources":
            source = bundle.sources[0].model_copy(
                update={
                    "evidence": (
                        EvidenceReference(
                            reference=bundle.sources[0].artifact,
                            role="evidence",
                            claim="duplicate",
                        ),
                    )
                }
            )
            source = source.model_copy(
                update={"evidence": (source.evidence[0], source.evidence[0])}
            )
            candidate = bundle.model_copy(update={"sources": (source, *bundle.sources[1:])})
            match_pattern = "references"
        else:
            candidate = bundle.model_copy(update=updates)
        with pytest.raises(ValidationError, match=match_pattern):
            ComplexActivityEvidenceBundle.model_validate(candidate)
    first = bundle.reconstruction_steps[0]
    unsorted = bundle.model_copy(
        update={
            "reconstruction_steps": (
                first.model_copy(update={"sequence": 2}),
                first.model_copy(update={"sequence": 1}),
            )
        }
    )
    with pytest.raises(ValidationError, match="ordered sequences"):
        ComplexActivityEvidenceBundle.model_validate(unsorted)


def test_request_and_result_closures_reject_wrong_bindings() -> None:
    request = _request()
    invalid_request = request.model_dump(mode="python")
    invalid_request["upstream_result"] = _artifact("wrong", "application/wrong")
    with pytest.raises(ValidationError, match="M09-07"):
        PublishComplexActivityEvidenceRequest.model_validate(invalid_request)
    invalid_request = request.model_dump(mode="python")
    invalid_request["source_artifacts"] = (
        request.source_artifacts[0],
        request.source_artifacts[0].model_copy(update={"artifact": _artifact("source.other")}),
    )
    with pytest.raises(ValidationError, match="identifiers"):
        PublishComplexActivityEvidenceRequest.model_validate(invalid_request)
    invalid_request = request.model_dump(mode="python")
    invalid_request["reconstruction_steps"] = (
        request.reconstruction_steps[0],
        request.reconstruction_steps[0],
    )
    with pytest.raises(ValidationError, match="ordered sequences"):
        PublishComplexActivityEvidenceRequest.model_validate(invalid_request)

    built = M0908EvidencePublisher().publish(request)
    result = built.result
    bad_bundle_id = result.bundle.model_copy(update={"bundle_id": "bundle.other"})
    bad_bundle_sources = result.bundle.model_copy(update={"sources": result.bundle.sources[:-1]})
    bad_assumptions = result.explanation.model_copy(update={"assumptions": ("assumption.other",)})
    bad_counter = result.explanation.model_copy(update={"counter_evidence": ("counter.other",)})
    cases = (
        (result.model_copy(update={"request_digest": _artifact("wrong").digest}), "exact request"),
        (result.model_copy(update={"bundle": bad_bundle_id}), "bind"),
        (result.model_copy(update={"bundle": bad_bundle_sources}), "every request"),
        (result.model_copy(update={"explanation": bad_assumptions}), "every assumption"),
        (result.model_copy(update={"explanation": bad_counter}), "counter-evidence"),
    )
    for candidate, message in cases:
        with pytest.raises(ValidationError, match=message):
            type(result).model_validate(candidate)
    with pytest.raises(ValidationError, match="bundle and explanation"):
        type(result).model_validate(result.model_copy(update={"bundle": None, "explanation": None}))
    with pytest.raises(ValidationError, match="result digest"):
        type(result).model_validate(
            result.model_copy(update={"result_digest": _artifact("wrong").digest})
        )


def test_abstained_result_cannot_claim_supported_status() -> None:
    result = M0908EvidencePublisher().publish(_request(include_assumptions=False)).result
    payload = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.SUPPORTED}
            )
        }
    )
    with pytest.raises(ValidationError, match="safe status"):
        type(result).model_validate(payload)


def test_runtime_edge_paths_and_public_operation(monkeypatch) -> None:
    engine = M0908EvidencePublisher()
    engine_module.preflight_m0908_authorization(object())
    with pytest.raises(TypeError):
        engine_module._evidence_for_source(object())
    with pytest.raises(ValueError, match="valid dictionary"):
        engine.publish(object())
    assert (
        engine_module.publish_complex_activity_evidence(_request()).result.status.value
        == "published"
    )

    monkeypatch.setattr(engine_module, "M0908_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(engine_module.M0908InputError, match="byte limit"):
        engine.publish(_request())


def test_runtime_reconstruction_authorization_and_envelope_failures() -> None:
    request = _request()
    engine = M0908EvidencePublisher()
    missing_upstream = request.reconstruction_steps[0].model_copy(
        update={"input_digests": (request.source_artifacts[0].artifact.digest,)}
    )
    assert (
        engine.publish(
            request.model_copy(update={"reconstruction_steps": (missing_upstream,)})
        ).result.status.value
        == "abstained"
    )
    second = request.reconstruction_steps[0].model_copy(update={"sequence": 2})
    two_steps = request.model_copy(
        update={"reconstruction_steps": (request.reconstruction_steps[0], second)}
    )
    assert engine.publish(two_steps).result.status.value == "abstained"
    refs = request.context.references
    with pytest.raises(engine_module.M0908AuthorizationError):
        engine.publish(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": refs.model_copy(
                                update={
                                    "identity_lineage": refs.identity_lineage.model_copy(
                                        update={"state": IdentityLineageState.UNRESOLVED}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        )
    with pytest.raises(engine_module.M0908AuthorizationError):
        engine.publish(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": refs.model_copy(
                                update={
                                    "quality": refs.quality.model_copy(
                                        update={"state": UpstreamDecisionState.REJECTED}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        )
    built = engine.publish(request)
    with pytest.raises(engine_module.M0908InputError, match="digest"):
        BuiltM0908Result(
            result=built.result.model_copy(update={"result_digest": _artifact("wrong").digest}),
            canonical_bytes=built.canonical_bytes,
        )
    with pytest.raises(engine_module.M0908InputError, match="not canonical"):
        BuiltM0908Result(result=built.result, canonical_bytes=b"{}")
