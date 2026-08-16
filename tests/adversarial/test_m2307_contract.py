"""Adversarial contract closure for provisional M23-07."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m23_07 import (
    M2307_M2306_INPUT_MEDIA_TYPE,
    EvaluateVariantPeptideHumanFactorsRequest,
    FallbackScenario,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    canonical_request_digest,
    result_identifier,
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


def _artifact(label: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
    return ArtifactReference(
        artifact_id=label,
        version="0.1.0",
        digest=f"sha256:{digest}",
        media_type=media_type,
    )


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact("m2307-evidence"),
        role="evidence",
        claim="Caller-declared operational evidence.",
    )


def _decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"{role}-decision",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="0.1.0",
        evidence=_artifact(f"{role}-evidence"),
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_artifact("identity-binding").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact("consent-evidence"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _request(request_id: str = "request-1") -> EvaluateVariantPeptideHumanFactorsRequest:
    evidence = (_evidence(),)
    dimensions = tuple(OperationalDimension)
    metrics = tuple(
        OperationalMetric(
            metric_id=f"metric-{index}",
            dimension=dimension,
            metric_name=dimension.value,
            observed_value=1.0,
            target_value=1.0,
            tolerance=0.1,
            sample_size=10,
            status=OperationalStatus.PASS,
            evidence=evidence,
        )
        for index, dimension in enumerate(dimensions)
    )
    fallbacks = tuple(
        FallbackScenario(
            scenario_id=f"fallback-{dimension.value}",
            dimension=dimension,
            trigger="primary path unavailable",
            fallback_path="review queue",
            recovery_seconds=1.0,
            fallback_available=True,
            status=OperationalStatus.PASS,
            evidence=evidence,
        )
        for dimension in (
            OperationalDimension.DOWNTIME,
            OperationalDimension.RECOVERY,
            OperationalDimension.FALLBACK,
        )
    )
    configuration = OperationalConfiguration(
        configuration_id="configuration-1",
        version="0.1.0",
        required_dimensions=dimensions,
        evidence=evidence,
    )
    upstream = _artifact("m2306-upstream", M2307_M2306_INPUT_MEDIA_TYPE)
    return EvaluateVariantPeptideHumanFactorsRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=upstream,
        metrics=metrics,
        fallbacks=fallbacks,
        configuration=configuration,
        source_artifacts=(upstream,),
    )


def test_request_requires_context_binding_and_exact_upstream_media() -> None:
    request = _request()
    assert request.context.request_id == request.request_id

    context_drift = request.model_dump(mode="python")
    context_drift["context"]["request_id"] = "other-request"
    with pytest.raises(ValueError, match="bind the request identifier"):
        EvaluateVariantPeptideHumanFactorsRequest(**context_drift)

    media_drift = request.model_dump(mode="python")
    media_drift["upstream_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M23-06 challenge result"):
        EvaluateVariantPeptideHumanFactorsRequest(**media_drift)


def test_request_rejects_duplicate_metric_ids_and_missing_dimensions() -> None:
    request = _request()
    duplicate_metrics = request.model_dump(mode="python")
    duplicate_metrics["metrics"] = (
        duplicate_metrics["metrics"][0],
        *duplicate_metrics["metrics"][1:],
    )
    duplicate_metrics["metrics"][1]["metric_id"] = duplicate_metrics["metrics"][0]["metric_id"]
    with pytest.raises(ValueError, match="metric ids must be unique"):
        EvaluateVariantPeptideHumanFactorsRequest(**duplicate_metrics)

    missing_dimension = request.model_dump(mode="python")
    missing_dimension["metrics"] = missing_dimension["metrics"][:-1]
    with pytest.raises(ValueError, match="every configured operational dimension"):
        EvaluateVariantPeptideHumanFactorsRequest(**missing_dimension)


def test_canonical_request_and_result_identity_change_with_bound_input() -> None:
    first = _request("request-1")
    second = _request("request-2")
    assert canonical_request_digest(first) != canonical_request_digest(second)
    assert result_identifier(first) != result_identifier(second)
