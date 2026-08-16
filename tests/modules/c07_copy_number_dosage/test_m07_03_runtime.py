"""Runtime, replay, and adversarial coverage for provisional M07-03."""

from __future__ import annotations

import pytest
from evals.m07_03.run import request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_03 import (
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    canonical_request_digest,
    canonical_result_digest,
    normalized_request,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
    M0703Plugin,
    M0703ReplayVerificationError,
    M0703Service,
    ValidatedM0703Request,
    preflight_m0703_authorization,
)

_EXPECTED_EVIDENCE_COUNT = 4


def test_runtime_abstains_with_explicit_uncertainty_and_evidence() -> None:
    result = M0703Service().execute(request())
    assert result.status.value == "abstained"
    assert result.estimates == ()
    assert result.abstention_reason
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert len(result.evidence) == _EXPECTED_EVIDENCE_COUNT
    assert all(item.role == "evidence" for item in result.evidence)
    assert all(
        dimension.state.value == "not_estimable"
        for dimension in (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
    )
    assert result.emits_parent is False
    assert verify_result_digest(result)


def test_replay_is_transitive_and_deterministic() -> None:
    service = M0703Service()
    first = service.execute(request())
    assert service.verify(first) == first
    assert service.verify(first, replay=False) == first
    assert service.execute(request()) == first
    assert canonical_request_digest(first.request) == first.request_digest
    assert canonical_result_digest(first) == first.result_digest
    assert normalized_request(first.request)["request_id"] == "request.m0703"
    with pytest.raises(M0703ReplayVerificationError):
        service.verify(object())


def test_tampered_payload_digest_and_embedded_request_are_rejected() -> None:
    service = M0703Service()
    result = service.execute(request())
    with pytest.raises(M0703ReplayVerificationError):
        service.verify(result.model_copy(update={"abstention_reason": "tampered"}))
    with pytest.raises(M0703ReplayVerificationError):
        service.verify(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    mismatched = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    mismatched = mismatched.model_copy(update={"result_digest": result_payload_digest(mismatched)})
    with pytest.raises(M0703ReplayVerificationError):
        service.verify(mismatched)


def test_authentication_and_hostile_objects_fail_closed() -> None:
    with pytest.raises(M0703AuthorizationError):
        M0703Service().execute(request(accepted_controls=False))
    with pytest.raises(M0703AuthorizationError):
        preflight_m0703_authorization({"context": {"references": {}}})

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile context")  # noqa: TRY003

    with pytest.raises(M0703AuthorizationError):
        preflight_m0703_authorization(Hostile())


def test_request_and_typed_estimate_invariants_reject_ambiguous_inputs() -> None:
    base = request()
    source = base.source_artifacts[0]
    duplicate = base.model_dump(mode="python") | {"source_artifacts": (source, source)}
    with pytest.raises(ValidationError):
        type(base).model_validate(duplicate, strict=True)
    mismatched_context = base.model_dump(mode="python") | {
        "context": base.context.model_copy(update={"request_id": "request.other"})
    }
    with pytest.raises(ValidationError):
        type(base).model_validate(mismatched_context, strict=True)
    with pytest.raises(ValidationError):
        type(base).model_validate(
            base.model_dump(mode="python")
            | {"representation_result": source, "configuration": base.configuration},
            strict=True,
        )
    with pytest.raises(ValidationError):
        BaselineEstimate(
            feature_id="feature.scalar",
            kind=BaselineEstimateKind.SCALAR,
            unit="copies",
            estimate_value=1.0,
            lower_bound=0.0,
        )
    with pytest.raises(ValidationError):
        BaselineEstimate(
            feature_id="feature.interval",
            kind=BaselineEstimateKind.INTERVAL,
            unit="copies",
            estimate_value=3.0,
            lower_bound=4.0,
            upper_bound=5.0,
        )


def test_diagnostic_statuses_and_parse_once_plugin_boundary() -> None:
    diagnostic = BaselineDiagnostic(
        diagnostic_id="diagnostic.warning",
        status=BaselineDiagnosticStatus.WARNING,
        message="Support is limited.",
        metric_name="coverage",
        metric_value=0.8,
    )
    assert diagnostic.status is BaselineDiagnosticStatus.WARNING
    service = M0703Service()
    plugin = M0703Plugin(service)
    candidate = request()
    token = plugin.validate(candidate)
    assert isinstance(token, ValidatedM0703Request)
    assert plugin.run(token) == service.execute(candidate)
    assert plugin.verify(plugin.run(token)) == plugin.run(token)
    serialized = canonical_json_bytes(candidate.model_dump(mode="json"))
    assert plugin.run(plugin.validate(serialized)).status.value == "abstained"
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0703Request(request=token.request, _seal=object()))
    with pytest.raises(TypeError):
        plugin.run(
            ValidatedM0703Request(
                request=token.request.model_copy(update={"request_id": "request.changed"}),
                _seal=object(),
            )
        )
