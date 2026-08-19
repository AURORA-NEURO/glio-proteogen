"""Adversarial contract closure for provisional M21-07."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m21_07 import (
    M2107_DOSSIER_SHA256,
    M2107_DOSSIER_SLICE,
    M2107_M2106_INPUT_MEDIA_TYPE,
    EvaluateComplexActivityHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

DIMENSIONS = tuple(OperationalDimension)


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2107.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2107": label, "media": media_type}),
        media_type=media_type,
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Caller-declared M21-07 operational evidence.",
        ),
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2107.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(f"control-{role}")
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended-use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m2107.synthetic",
        actor_id="actor.m2107.synthetic",
        occurred_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2107.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2107.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2107.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended-use", artifacts["intended-use"]),
        ),
    )


def _configuration() -> OperationalConfiguration:
    return OperationalConfiguration(
        configuration_id="configuration.m2107.synthetic",
        version="1.0.0",
        required_dimensions=DIMENSIONS,
        evidence=_evidence("configuration"),
    )


def _metric(
    dimension: OperationalDimension,
    status: OperationalStatus = OperationalStatus.PASS,
) -> OperationalMetric:
    return OperationalMetric(
        metric_id=f"metric.m2107.{dimension.value}",
        dimension=dimension,
        metric_name=f"{dimension.value} metric",
        observed_value=0.9 if status is OperationalStatus.PASS else 0.2,
        target_value=0.8,
        tolerance=0.1,
        sample_size=12,
        status=status,
        evidence=_evidence(f"metric-{dimension.value}"),
    )


def _fallback(status: OperationalStatus = OperationalStatus.PASS) -> FallbackScenario:
    return FallbackScenario(
        scenario_id="fallback.m2107.synthetic",
        trigger="operational interruption",
        fallback_path="manual review queue",
        recovery_seconds=30.0,
        fallback_available=status is not OperationalStatus.NOT_EVALUABLE,
        status=status,
        evidence=_evidence("fallback"),
    )


def _request(
    *,
    upstream_media_type: str = M2107_M2106_INPUT_MEDIA_TYPE,
    statuses: tuple[OperationalStatus, ...] | None = None,
) -> EvaluateComplexActivityHumanFactorsRequest:
    upstream = _artifact("upstream", upstream_media_type)
    statuses = statuses or (OperationalStatus.PASS,) * len(DIMENSIONS)
    return EvaluateComplexActivityHumanFactorsRequest(
        request_id="request.m2107.synthetic",
        context=_context(),
        upstream_result=upstream,
        metrics=tuple(
            _metric(dimension, status)
            for dimension, status in zip(DIMENSIONS, statuses, strict=True)
        ),
        fallbacks=(_fallback(),),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("source")),
    )


def test_authority_and_schema_metadata_are_explicit() -> None:
    assert (
        M2107_DOSSIER_SHA256
        == "sha256:" + "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2107_DOSSIER_SLICE.endswith(":7500-7540")
    metadata = cast("dict[str, Any]", contract_json_schema("request")["x-glio-contract"])
    assert metadata["dossierSha256"] == M2107_DOSSIER_SHA256
    assert metadata["upstreamInputMediaType"] == M2107_M2106_INPUT_MEDIA_TYPE


def test_request_closes_dimensions_sources_and_context() -> None:
    request = _request()
    assert {metric.dimension for metric in request.metrics} == set(DIMENSIONS)
    assert request.upstream_result in request.source_artifacts
    with pytest.raises(ValidationError, match="M21-06"):
        EvaluateComplexActivityHumanFactorsRequest.model_validate(
            _request(upstream_media_type="application/json")
        )
    with pytest.raises(ValidationError, match="request source artifacts must include"):
        EvaluateComplexActivityHumanFactorsRequest.model_validate(
            request.model_copy(update={"source_artifacts": (_artifact("other"),)})
        )


def test_configuration_fallback_and_report_closure_are_fail_closed() -> None:
    configuration = _configuration()
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        OperationalConfiguration.model_validate(
            configuration.model_copy(
                update={"required_dimensions": (OperationalDimension.REVIEWER_COMPREHENSION,) * 7}
            )
        )
    with pytest.raises(ValidationError, match="unavailable fallback"):
        FallbackScenario.model_validate(
            _fallback(OperationalStatus.PASS).model_copy(update={"fallback_available": False})
        )
    request = _request()
    report = HumanFactorsOperationalReport(
        report_id="report.m2107.synthetic",
        version=request.configuration.version,
        metrics=request.metrics,
        fallbacks=request.fallbacks,
        configuration=request.configuration,
        evidence=_evidence("report"),
    )
    with pytest.raises(ValidationError, match="every configured"):
        HumanFactorsOperationalReport.model_validate(
            report.model_copy(update={"metrics": report.metrics[:-1]})
        )
