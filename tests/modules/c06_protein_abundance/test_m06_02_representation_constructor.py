"""Lifecycle, replay and safe-abstention tests for M06-02."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m06_02 import (
    BuildProteinRepresentationRequest,
    FeatureLineageRole,
    FeatureLineageStep,
    RepresentationConstructorStatus,
    RepresentationFeature,
    RepresentationFeatureKind,
    RepresentationObservationState,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    BuiltProteinRepresentation,
    M0602Plugin,
    M0602RepresentationEngine,
    M0602Service,
    RepresentationAuthorizationError,
    RepresentationInputError,
    RepresentationSubmission,
    construct_protein_representation,
)
from tests.contract.test_m06_02_contract import _request


def _with_feature_state(state: RepresentationObservationState) -> BuildProteinRepresentationRequest:
    request = _request()
    source = ArtifactReference(
        artifact_id="evidence.m0602.second-source",
        version="1.0.0",
        digest="sha256:" + "e" * 64,
        media_type="application/json",
    )
    lineage = FeatureLineageStep(
        lineage_id="lineage.m0602.second",
        role=FeatureLineageRole.SOURCE,
        operation="source-feature",
        transformation_version="1.0.0",
        input_digests=(source.digest,),
        output_feature_ids=("feature.second",),
    )
    feature = RepresentationFeature(
        feature_id="feature.second",
        version="1.0.0",
        kind=RepresentationFeatureKind.SCALAR,
        state=state,
        unit="normalized-abundance",
        lineage_id=lineage.lineage_id,
        source_digest=source.digest,
    )
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts, source)
    payload["lineage"] = (*request.lineage, lineage)
    payload["features"] = (*request.features, feature)
    return BuildProteinRepresentationRequest.model_validate(payload, strict=True)


def test_construct_is_deterministic_and_preserves_declared_feature_lineage() -> None:
    engine = M0602RepresentationEngine()
    first = engine.construct(_request())
    second = engine.construct(_request())

    assert first.result.status is RepresentationConstructorStatus.CONSTRUCTED
    assert first.result.features == _request().features
    assert first.result.lineage == _request().lineage
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.result_digest == second.result.result_digest
    assert first.result.leakage_checked is True
    assert first.result.infers_kinase_activity is False


def test_replay_verification_accepts_canonical_result_and_rejects_tamper() -> None:
    engine = M0602RepresentationEngine()
    built = engine.construct(_request())

    verified = engine.verify(built.result, built.canonical_bytes)
    tampered_bytes = built.canonical_bytes[:-1] + bytes([built.canonical_bytes[-1] ^ 1])
    tampered = engine.verify(built.result, tampered_bytes)

    assert verified.verified is True
    assert tampered.verified is False
    assert tampered.content_verified is False
    assert tampered.result_digest is None


@pytest.mark.parametrize(
    ("state", "support"),
    [
        (RepresentationObservationState.MISSING, SupportStatus.REVIEW_REQUIRED),
        (RepresentationObservationState.NOT_APPLICABLE, SupportStatus.REVIEW_REQUIRED),
        (RepresentationObservationState.UNSUPPORTED, SupportStatus.UNSUPPORTED),
    ],
)
def test_non_observed_features_abstain_with_explicit_masks(
    state: RepresentationObservationState,
    support: SupportStatus,
) -> None:
    built = M0602RepresentationEngine().construct(_with_feature_state(state))

    assert built.result.status is RepresentationConstructorStatus.ABSTAINED
    assert built.result.support_decision.status is support
    mask = next(item for item in built.result.masks if item.feature_id == "feature.second")
    assert mask.state is state
    assert built.result.features[-1].scalar_value is None


def test_execute_alias_and_service_boundary_are_replayable() -> None:
    request = _request()
    service = M0602Service()
    built = service.execute(request)
    alias = M0602RepresentationEngine().execute(request)

    assert built.canonical_bytes == alias.canonical_bytes
    assert service.verify(built.result, built.canonical_bytes).verified is True


def test_invalid_result_and_noncanonical_built_outcome_fail_closed() -> None:
    engine = M0602RepresentationEngine()
    built = engine.construct(_request())

    invalid = engine.verify(object(), built.canonical_bytes)
    assert invalid.verified is False
    assert invalid.reason.value == "invalid_result"
    invalid_bytes = engine.verify(
        built.result,
        bytearray(built.canonical_bytes),  # type: ignore[arg-type]
    )
    assert invalid_bytes.verified is False
    with pytest.raises(RepresentationInputError, match="not canonical"):
        BuiltProteinRepresentation(built.result, b"{}")


def test_result_closure_rejects_constructed_without_support_and_abstained_with_support() -> None:
    built = M0602RepresentationEngine().construct(_request())
    limited = SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="test",
        rationale="test limited support",
    )
    constructed_payload = built.result.model_copy(update={"support_decision": limited})
    constructed_payload = constructed_payload.model_copy(
        update={"result_digest": result_payload_digest(constructed_payload)}
    )
    with pytest.raises(ValueError, match="constructed result requires supported"):
        type(built.result).model_validate(constructed_payload, strict=True)

    abstained_payload = built.result.model_copy(
        update={"status": RepresentationConstructorStatus.ABSTAINED}
    )
    abstained_payload = abstained_payload.model_copy(
        update={"result_digest": result_payload_digest(abstained_payload)}
    )
    with pytest.raises(ValueError, match="cannot claim supported"):
        type(built.result).model_validate(abstained_payload, strict=True)


def test_authorization_rejects_withheld_consent_unresolved_identity_and_controls() -> None:
    request = _request()
    refs = request.context.references
    engine = M0602RepresentationEngine()

    withheld = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    unresolved = request.model_copy(
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
    rejected_control = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "support": refs.support.model_copy(
                                update={"state": UpstreamDecisionState.REJECTED}
                            )
                        }
                    )
                }
            )
        }
    )
    for denied in (withheld, unresolved, rejected_control):
        with pytest.raises(RepresentationAuthorizationError):
            engine.construct(denied)


def test_mapping_request_cannot_bypass_authorization() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD

    with pytest.raises(RepresentationAuthorizationError):
        M0602RepresentationEngine().construct(payload)


def test_strict_request_boundary_rejects_untyped_object() -> None:
    with pytest.raises((TypeError, ValueError)):
        M0602RepresentationEngine().construct(object())


def test_plugin_parse_once_validate_token_and_safe_execution() -> None:
    request = _request()
    plugin = M0602Plugin()
    submission = RepresentationSubmission(
        canonical_json_bytes(request.model_dump(mode="json"))
    )

    validated = plugin.validate(submission)
    built = plugin.run(validated)
    assert plugin.validate_request(request) == request
    assert plugin.validate(RepresentationSubmission(request)).request == request

    assert validated.request == request
    assert built.result.status is RepresentationConstructorStatus.CONSTRUCTED


def test_plugin_rejects_unvalidated_token_and_invalid_submission() -> None:
    plugin = M0602Plugin()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="representation submission"):
        plugin.validate(object())
    assert plugin.execute(_request()).result.status is RepresentationConstructorStatus.CONSTRUCTED


def test_public_construct_wrapper_and_result_limit_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    assert (
        construct_protein_representation(request).result.status
        is RepresentationConstructorStatus.CONSTRUCTED
    )
    built = M0602RepresentationEngine().construct(request)
    with pytest.raises(RepresentationInputError, match="digest"):
        BuiltProteinRepresentation(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
    monkeypatch.setattr(
        "glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor.engine.M0602_MAX_CANONICAL_RESULT_BYTES",
        1,
    )
    with pytest.raises(RepresentationInputError, match="exceeds byte limit"):
        M0602RepresentationEngine().construct(request)
