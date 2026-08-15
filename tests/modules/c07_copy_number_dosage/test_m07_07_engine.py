"""Adversarial runtime coverage for provisional M07-07."""

# ruff: noqa: INP001

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m07_06 import (
    M0706_CONSTRAINT_MEDIA_TYPE,
    M0706_CONTRACT_VERSION,
    M0706_NOMINAL_COVERAGE,
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m07_06.canonical import (
    canonical_request_digest as upstream_request_digest,
)
from glio_proteogen.contracts.m07_06.canonical import (
    result_payload_digest as upstream_digest,
)
from glio_proteogen.contracts.m07_07 import (
    M0707_NOMINAL_COVERAGE,
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrationMethod,
    CalibrationPolicy,
    CalibrationStratum,
    CalibrationStratumDimension,
    OutOfDistributionStatus,
    SelectiveCandidate,
    SelectivePredictionStatus,
    SelectiveSupportThreshold,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706Service,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction import (
    CalibrationAuthorizationError,
    M0707CalibrationEngine,
    M0707Service,
)

_DIGEST = "sha256:" + "a" * 64
_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}", version="0.1.0", digest=_DIGEST, media_type=media_type
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact("control"),
    )
    return ExecutionContext(
        request_id="request.context",
        actor_id="actor.synthetic",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity"),
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _upstream(*, supported: bool) -> CopyNumberDosageUncertaintyDecompositionResult:
    policy = UncertaintyDecompositionPolicy(
        policy_id="policy.upstream",
        version="1.0.0",
        method="synthetic",
        calibration_reference=_artifact("calibration"),
    )
    upstream_request = DecomposeCopyNumberDosageUncertaintyRequest(
        request_id="request.upstream",
        context=_context(),
        constraint_result=_artifact("constraint", M0706_CONSTRAINT_MEDIA_TYPE),
        policy=policy,
        source_artifacts=(_artifact("upstream"),),
    )
    request_digest = upstream_request_digest(upstream_request)
    if not supported:
        return cast(
            "CopyNumberDosageUncertaintyDecompositionResult",
            M0706Service().execute(upstream_request),
        )
    estimated = UncertaintyEstimate(
        state=EstimateState.ESTIMATED, probability=0.1, rationale="synthetic"
    )
    decomposition = UncertaintyDecomposition(
        decomposition_id="decomposition.synthetic",
        components=tuple(
            UncertaintyComponent(dimension=dimension, estimate=estimated, rationale="synthetic")
            for dimension in UncertaintyDimension
        ),
        method="synthetic",
        model_reference=_artifact("model"),
    )
    result_payload: dict[str, object] = {
        "result_id": "result.upstream",
        "result_version": M0706_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _DIGEST,
        "request": upstream_request,
        "status": UncertaintyDecompositionStatus.DECOMPOSED,
        "decomposition": decomposition,
        "sensitivity_envelope": SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=M0706_NOMINAL_COVERAGE,
            lower_bound=0.85,
            upper_bound=0.95,
            observed_coverage=0.90,
            rationale="synthetic",
        ),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "proteotype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED, reason_code="upstream_supported", rationale="synthetic"
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(upstream_request, request_digest, sha256_digest(policy)),
        "evidence": (),
        "limitations": (_artifact("limitation"),),
        "human_review_required": False,
    }
    result_payload["limitations"] = (Limitation(code="synthetic", statement="synthetic"),)
    constructed = CopyNumberDosageUncertaintyDecompositionResult.model_construct(**result_payload)
    result_payload["result_digest"] = upstream_digest(constructed)
    return CopyNumberDosageUncertaintyDecompositionResult.model_validate(
        result_payload, strict=True
    )


def _policy() -> CalibrationPolicy:
    strata = tuple(
        CalibrationStratum(
            stratum_id=f"stratum.{dimension.value}",
            dimension=dimension,
            label=dimension.value,
            sample_count=20,
            observed_coverage=0.90,
            calibration_error=0.02,
        )
        for dimension in CalibrationStratumDimension
    )
    return CalibrationPolicy(
        policy_id="policy.calibration",
        version="1.0.0",
        method=CalibrationMethod.CONFORMAL,
        calibration_reference=_artifact("calibration.m0707"),
        strata=strata,
        support_threshold=SelectiveSupportThreshold(
            threshold_id="threshold.m0707",
            version="1.0.0",
            minimum_support_score=0.8,
            maximum_ood_score=0.2,
            maximum_calibration_error=0.05,
            target_coverage=M0707_NOMINAL_COVERAGE,
        ),
    )


def _request(
    *,
    supported: bool = True,
    candidates: tuple[SelectiveCandidate, ...] = (),
) -> CalibrateSelectiveCopyNumberDosageRequest:
    policy = _policy()
    strata = tuple(item.stratum_id for item in policy.strata)
    selected = candidates or (
        SelectiveCandidate(
            feature_id="feature.good",
            estimate_value=1.25,
            labels=("low", "high"),
            support_score=0.95,
            ood_score=0.05,
            calibration_error=0.02,
            stratum_ids=strata,
        ),
    )
    return CalibrateSelectiveCopyNumberDosageRequest(
        request_id="request.m0707",
        context=_context(),
        uncertainty_result=_upstream(supported=supported),
        policy=policy,
        source_artifacts=(_artifact("input"),),
        candidates=selected,
    )


def test_supported_candidate_is_calibrated_and_replayable() -> None:
    request = _request()
    result = M0707CalibrationEngine().calibrate(request)
    assert result.status.value == "calibrated"
    assert result.estimates[0].selection_status is SelectivePredictionStatus.SELECTED
    assert result.estimates[0].ood_status is OutOfDistributionStatus.IN_DOMAIN
    assert M0707Service.verify_result(result, request).result_digest == result.result_digest


def test_upstream_abstention_is_preserved_without_candidate_value() -> None:
    result = M0707Service().execute(_request(supported=False))
    assert result.status.value == "abstained"
    assert not result.estimates
    assert not result.prediction_sets
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_low_support_and_ood_candidates_are_selectively_abstained() -> None:
    policy = _policy()
    strata = tuple(item.stratum_id for item in policy.strata)
    candidates = (
        SelectiveCandidate(
            feature_id="feature.low-support",
            category="low",
            support_score=0.2,
            ood_score=0.01,
            calibration_error=0.01,
            stratum_ids=strata,
        ),
        SelectiveCandidate(
            feature_id="feature.ood",
            category="high",
            support_score=0.9,
            ood_score=0.9,
            calibration_error=0.01,
            stratum_ids=strata,
        ),
    )
    result = M0707Service().execute(_request(candidates=candidates))
    assert result.status.value == "abstained"
    assert len(result.diagnostics) == len(candidates)
    assert result.support_decision.status is SupportStatus.UNSUPPORTED


def test_preflight_rejects_withheld_consent_before_execution() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": "withheld"})
    refs = request.context.references.model_copy(update={"consent": consent})
    blocked_context = request.context.model_copy(update={"references": refs})
    blocked = request.model_copy(update={"context": blocked_context})
    with pytest.raises(CalibrationAuthorizationError):
        M0707CalibrationEngine().calibrate(blocked)


def test_tampered_result_fails_canonical_replay() -> None:
    result = M0707Service().execute(_request())
    tampered = result.model_dump(mode="python")
    tampered["estimates"] = ()
    with pytest.raises((ValidationError, ValueError)):
        M0707Service.verify_result(tampered)
