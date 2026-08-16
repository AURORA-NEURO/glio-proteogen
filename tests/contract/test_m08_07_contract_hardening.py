"""Adversarial M08-07 contract closure tests.

These tests deliberately exercise the fields most likely to be weakened by a
future ABI implementation: duplicate references, duplicate diagnostics,
metric/status mismatches, and unsafe abstention claims.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_07 import (
    M0807_NOMINAL_COVERAGE,
    CalibratedEstimate,
    CalibrateProteinSubtypeSelectivePredictionRequest,
    CalibrationCandidate,
    CalibrationConfiguration,
    CalibrationDiagnostic,
    CalibrationDiagnosticStatus,
    CalibrationMethod,
    CalibrationScope,
    PredictionSet,
    ProteinSubtypeSelectivePredictionResult,
)
from glio_proteogen.contracts.m08_07.canonical import verify_result_replay
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
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_07_calibration_selective_prediction as m0807,
)


def _artifact(index: int = 1, *, media_type: str = "application/json"):
    return ArtifactReference(
        artifact_id=f"artifact.{index}",
        version="1.0.0",
        digest=f"sha256:{index:064x}",
        media_type=media_type,
    )


def _configuration() -> CalibrationConfiguration:
    return CalibrationConfiguration(
        configuration_id="configuration.m0807",
        version="1.0.0",
        method=CalibrationMethod.CONFORMAL,
        scopes=(
            CalibrationScope(
                site="site-a",
                platform="platform-a",
                disease_class="glioma",
                subgroup="all",
            ),
        ),
        nominal_coverage=M0807_NOMINAL_COVERAGE,
        support_threshold=0.8,
        ood_threshold=0.2,
        calibration_artifact=_artifact(2),
        benchmark_artifact=_artifact(3),
    )


def _request(source_artifacts: tuple[object, ...] | None = None):
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(11),
    )
    context = ExecutionContext(
        request_id="context.request",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=_artifact(12),
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact(13),
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )
    return CalibrateProteinSubtypeSelectivePredictionRequest(
        request_id="request.m0807",
        context=context,
        uncertainty_result=_artifact(20, media_type="application/vnd.glio-proteogen.m08-06+json"),
        configuration=_configuration(),
        source_artifacts=source_artifacts or (_artifact(21),),
    )


def test_duplicate_source_references_are_rejected() -> None:
    artifact = _artifact(21)
    with pytest.raises(ValueError, match="source artifact references"):
        _request((artifact, artifact))


def test_diagnostic_metric_presence_matches_evaluability() -> None:
    with pytest.raises(ValueError, match="non-evaluable"):
        CalibrationDiagnostic(
            diagnostic_id="diagnostic.bad",
            status=CalibrationDiagnosticStatus.NOT_EVALUABLE,
            metric_name="coverage",
            metric_value=0.9,
            message="not evaluated",
        )
    with pytest.raises(ValueError, match="finite metric"):
        CalibrationDiagnostic(
            diagnostic_id="diagnostic.bad",
            status=CalibrationDiagnosticStatus.PASS,
            metric_name="coverage",
            message="passed",
        )


def test_prediction_set_and_estimate_reject_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match=r"finite|less than"):
        PredictionSet(labels=("subtype",), nominal_coverage=float("nan"))
    with pytest.raises(ValueError, match=r"finite|less than"):
        CalibratedEstimate(
            predicted_subtype="subtype",
            score=float("inf"),
            calibrated_confidence=0.9,
            calibration_reference=_artifact(30),
        )


def test_scope_and_prediction_labels_close_uniquely() -> None:
    scope = CalibrationScope(
        site="site-a",
        platform="platform-a",
        disease_class="glioma",
        subgroup="all",
    )
    with pytest.raises(ValueError, match="scopes must be unique"):
        CalibrationConfiguration(
            configuration_id="configuration.duplicate",
            version="1.0.0",
            method=CalibrationMethod.CONFORMAL,
            scopes=(scope, scope),
            support_threshold=0.8,
            ood_threshold=0.2,
            calibration_artifact=_artifact(40),
            benchmark_artifact=_artifact(41),
        )
    with pytest.raises(ValueError, match="prediction-set labels"):
        PredictionSet(labels=("subtype", "subtype"), nominal_coverage=0.9)
    with pytest.raises(ValueError, match="contained"):
        CalibrationCandidate(
            site="site-a",
            platform="platform-a",
            disease_class="glioma",
            subgroup="all",
            predicted_subtype="missing",
            score=0.8,
            calibrated_confidence=0.9,
            labels=("subtype",),
            observed_coverage=0.9,
            calibration_error=0.05,
            support_score=0.9,
            ood_score=0.05,
            subgroup_disparity=0.02,
        )


def test_request_and_result_digest_closures_reject_tampering() -> None:
    request = _request()
    with pytest.raises(ValueError, match="M08-06"):
        CalibrateProteinSubtypeSelectivePredictionRequest.model_validate(
            request.model_copy(update={"uncertainty_result": _artifact(20)}),
            strict=True,
        )
    result = m0807.M0807Service().execute(request)
    payload = result.model_dump()
    payload["request_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="request digest"):
        ProteinSubtypeSelectivePredictionResult.model_validate(payload, strict=True)
    payload = result.model_dump()
    payload["human_review_required"] = False
    with pytest.raises(ValueError, match="human review"):
        ProteinSubtypeSelectivePredictionResult.model_validate(payload, strict=True)
    payload = result.model_dump()
    payload["result_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="result digest"):
        ProteinSubtypeSelectivePredictionResult.model_validate(payload, strict=True)


def test_canonical_replay_rejects_malformed_or_mismatched_documents() -> None:
    request = _request()
    result = m0807.M0807Service().execute(request)
    payload = result.model_dump(mode="json")
    assert verify_result_replay({"request": "not-an-object"}) is False
    mismatched = dict(payload)
    mismatched["request_digest"] = "sha256:" + "f" * 64
    assert verify_result_replay(mismatched) is False
    assert verify_result_replay(payload, _request()) is True
    assert (
        verify_result_replay(
            payload,
            _request().model_copy(update={"request_id": "request.other"}),
        )
        is False
    )
