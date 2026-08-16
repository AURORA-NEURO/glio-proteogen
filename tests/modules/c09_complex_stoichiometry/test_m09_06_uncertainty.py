"""Adversarial runtime tests for the M09-06 uncertainty boundary."""

# ruff: noqa: INP001

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Final

import pytest

from glio_proteogen.contracts.m09_06 import (
    M0906_M0905_RESULT_MEDIA_TYPE,
    DecomposeComplexActivityUncertaintyRequest,
    DecomposeComplexActivityUncertaintyVerification,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyDecompositionReplayReason,
    canonical_request_digest,
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
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_06_uncertainty_decomposition_engine as m0906_module,
)

M0906AuthorizationError = m0906_module.M0906AuthorizationError
M0906Plugin = m0906_module.M0906Plugin
M0906Service = m0906_module.M0906Service
M0906UncertaintyDecompositionEngine = m0906_module.M0906UncertaintyDecompositionEngine
BuiltM0906Result = m0906_module.engine.BuiltM0906Result
M0906InputError = m0906_module.engine.M0906InputError

_DIGEST: Final = "sha256:" + ("a" * 64)
_DIMENSION_COUNT: Final = 7


def _artifact(
    name: str,
    media_type: str = "application/vnd.aurora.synthetic+json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _upstream(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=name,
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"{name}.evidence"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="context.m0906",
        actor_id="actor.m0906",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_upstream("configuration.m0906"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity.m0906",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity.m0906.evidence"),
            ),
            provenance=_upstream("provenance.m0906"),
            consent=ConsentReference(
                decision_id="consent.m0906",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent.m0906.evidence"),
            ),
            quality=_upstream("quality.m0906"),
            support=_upstream("support.m0906"),
            intended_use=_upstream("intended-use.m0906"),
        ),
    )


def _request(
    *,
    method: str = "deterministic-calibrated-uncertainty",
    source_media_type: str = "application/vnd.aurora.synthetic+json",
) -> DecomposeComplexActivityUncertaintyRequest:
    return DecomposeComplexActivityUncertaintyRequest(
        request_id="request.m0906",
        context=_context(),
        integrator_result=_artifact(
            "integrator.m0905",
            "application/vnd.glio-proteogen.m09-05+json",
        ),
        policy=UncertaintyDecompositionPolicy(
            policy_id="policy.m0906",
            version="1.0.0",
            method=method,
            calibration_reference=_artifact("calibration.m0906"),
        ),
        source_artifacts=(_artifact("source.m0906", source_media_type),),
    )


def test_decomposed_result_exposes_all_dimensions_and_coverage() -> None:
    built = M0906Service().execute(_request())
    assert built.result.status.value == "decomposed"
    assert built.result.support_decision.status.value == "supported"
    assert built.result.decomposition is not None
    assert len(built.result.decomposition.components) == _DIMENSION_COUNT
    assert {item.dimension.value for item in built.result.decomposition.components} == {
        "measurement",
        "sampling",
        "parameter",
        "model_form",
        "identification",
        "support",
        "transport",
    }
    assert built.result.sensitivity_envelope.status is SensitivityEnvelopeStatus.EVALUATED
    assert M0906UncertaintyDecompositionEngine.verify(built.result, built.canonical_bytes).verified


def test_determinism_and_replay_tamper_closure() -> None:
    service = M0906Service()
    first = service.execute(_request())
    second = service.execute(_request())
    assert first.canonical_bytes == second.canonical_bytes
    tampered = first.canonical_bytes.replace(b"decomposed", b"abstained", 1)
    assert not M0906UncertaintyDecompositionEngine.verify(first.result, tampered).verified


def test_unsupported_method_abstains_without_negative_output() -> None:
    built = M0906Service().execute(_request(method="unsupported:masked-foundation-model"))
    assert built.result.status.value == "abstained"
    assert built.result.decomposition is None
    assert built.result.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED
    assert built.result.support_decision.status.value == "unsupported"
    assert built.result.human_review_required is True


def test_uncalibrated_method_requires_review() -> None:
    built = M0906Service().execute(_request(method="uncalibrated-proteome-autoencoder"))
    assert built.result.status.value == "abstained"
    assert built.result.support_decision.status.value == "review_required"
    assert built.result.findings[0].code.value == "calibration_not_locked"


def test_unsupported_source_media_abstains() -> None:
    built = M0906Service().execute(_request(source_media_type="application/unsupported"))
    assert built.result.status.value == "abstained"
    assert built.result.support_decision.status.value == "unsupported"


def test_authorization_fails_closed() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "quality": request.context.references.quality.model_copy(
                        update={"state": UpstreamDecisionState.REJECTED}
                    )
                }
            )
        }
    )
    with pytest.raises(M0906AuthorizationError):
        M0906Service().execute(request.model_copy(update={"context": denied_context}))


def test_plugin_requires_validated_parse_once_token() -> None:
    plugin = M0906Plugin(M0906Service())
    token = plugin.validate(_request())
    assert plugin.run(token).result.status.value == "decomposed"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_rejects_duplicate_json() -> None:
    with pytest.raises(StrictJsonError, match="duplicate"):
        M0906Plugin(M0906Service()).validate(b'{"request_id":"one","request_id":"two"}')


def test_plugin_accepts_valid_strict_json_bytes() -> None:
    payload = json.dumps(_request().model_dump(mode="json")).encode()
    plugin = M0906Plugin(M0906Service())
    token = plugin.validate(payload)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-06"
    assert token.request.request_id == "request.m0906"


def test_preflight_rejects_non_request_consent_and_identity() -> None:
    with pytest.raises(M0906AuthorizationError):
        m0906_module.preflight_m0906_authorization(object())
    request = _request()
    withheld = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(M0906AuthorizationError):
        M0906Service().execute(withheld)


def test_built_result_rejects_bad_digest_and_bytes() -> None:
    built = M0906Service().execute(_request())
    with pytest.raises(M0906InputError, match="digest"):
        BuiltM0906Result(
            result=built.result.model_copy(update={"result_digest": _DIGEST}),
            canonical_bytes=built.canonical_bytes,
        )
    with pytest.raises(M0906InputError, match="canonical"):
        BuiltM0906Result(result=built.result, canonical_bytes=b"{}")


def test_verify_rejects_different_valid_result_and_invalid_inputs() -> None:
    supported = M0906Service().execute(_request())
    abstained = M0906Service().execute(_request(method="unsupported:foundation"))
    different = M0906UncertaintyDecompositionEngine.verify(
        supported.result,
        abstained.canonical_bytes,
    )
    assert different.verified is False
    assert M0906UncertaintyDecompositionEngine.verify(object(), b"[]").verified is False


def test_sensitivity_schema_rejects_out_of_range_bounds() -> None:
    with pytest.raises(ValueError, match="lower_bound"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=-0.1,
            upper_bound=0.95,
            observed_coverage=0.9,
            rationale="invalid lower bound",
        )


def test_contract_closures_reject_duplicate_dimensions_and_bad_sensitivity() -> None:
    built = M0906Service().execute(_request())
    assert built.result.decomposition is not None
    components = built.result.decomposition.components
    with pytest.raises(ValueError, match="all seven"):
        UncertaintyDecomposition.model_validate(
            built.result.decomposition.model_dump(mode="python")
            | {"components": (*components[:-1], components[0])}
        )
    with pytest.raises(ValueError, match="not ordered"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=0.95,
            upper_bound=0.85,
            observed_coverage=0.9,
            rationale="bounds reversed",
        )
    with pytest.raises(ValueError, match="nominal 90"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=0.8,
            lower_bound=0.85,
            upper_bound=0.95,
            observed_coverage=0.9,
            rationale="nominal coverage is not locked",
        )


def test_policy_request_result_and_verification_closures() -> None:
    request = _request()
    with pytest.raises(ValueError, match="nominal 90"):
        UncertaintyDecompositionPolicy.model_validate(
            request.policy.model_dump(mode="python") | {"nominal_coverage": 0.8}
        )
    with pytest.raises(ValueError, match="M09-05"):
        DecomposeComplexActivityUncertaintyRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "integrator_result": _artifact(
                    "wrong",
                    "application/vnd.glio-proteogen.other+json",
                )
            }
        )
    assert request.integrator_result.media_type == M0906_M0905_RESULT_MEDIA_TYPE
    with pytest.raises(ValueError, match="verified results"):
        DecomposeComplexActivityUncertaintyVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=UncertaintyDecompositionReplayReason.VERIFIED,
        )
    built = M0906Service().execute(request)
    with pytest.raises(ValueError, match="request digest"):
        type(built.result).model_validate(
            built.result.model_dump(mode="python") | {"request_digest": _DIGEST}
        )
    with pytest.raises(ValueError, match="calibrated"):
        type(built.result).model_validate(
            built.result.model_dump(mode="python") | {"decomposition": None}
        )


def test_result_finding_and_digest_closures() -> None:
    request = _request(method="unsupported:foundation")
    built = M0906Service().execute(request)
    finding = built.result.findings[0]
    with pytest.raises(ValueError, match="finding ids"):
        type(built.result).model_validate(
            built.result.model_dump(mode="python") | {"findings": (finding, finding)}
        )
    with pytest.raises(ValueError, match="result digest"):
        type(built.result).model_validate(
            built.result.model_dump(mode="python") | {"result_digest": _DIGEST}
        )


def test_limits_digest_branches_public_operation_and_service_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = M0906Service().execute(_request())
    original_request_digest = canonical_request_digest
    assert m0906_module.decompose_complex_activity_uncertainty(_request()).canonical_bytes == (
        built.canonical_bytes
    )
    assert M0906Service().verify(built.result, built.canonical_bytes).verified

    monkeypatch.setattr(m0906_module.engine, "M0906_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(M0906InputError, match="result exceeds"):
        M0906Service().execute(_request())
    monkeypatch.setattr(m0906_module.engine, "M0906_MAX_CANONICAL_RESULT_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(m0906_module.engine, "M0906_MAX_CANONICAL_REQUEST_BYTES", 1)
    with pytest.raises(M0906InputError, match="request exceeds"):
        M0906Plugin(M0906Service()).validate(b"{}")

    monkeypatch.setattr(m0906_module.engine, "M0906_MAX_CANONICAL_REQUEST_BYTES", 4 * 1024 * 1024)
    monkeypatch.setattr(m0906_module.engine, "canonical_request_digest", lambda _value: _DIGEST)
    request_mismatch = M0906UncertaintyDecompositionEngine.verify(
        built.result,
        built.canonical_bytes,
    )
    assert request_mismatch.reason == "request digest does not replay"
    monkeypatch.setattr(
        m0906_module.engine,
        "canonical_request_digest",
        original_request_digest,
    )
    monkeypatch.setattr(m0906_module.engine, "result_payload_digest", lambda _value: _DIGEST)
    digest_mismatch = M0906UncertaintyDecompositionEngine.verify(
        built.result,
        built.canonical_bytes,
    )
    assert digest_mismatch.reason == "result digest does not replay"
