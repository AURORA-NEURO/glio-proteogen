"""Adversarial contract closure for M19-08 translation monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_08 import (
    M1908_DOSSIER_SHA256,
    M1908_DOSSIER_SLICE,
    DiscrepancyObservation,
    MonitorProteotypeTranslationHealthRequest,
    ObservationStatus,
    RollbackDecision,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationHealthReport,
    TranslationHealthState,
    WorkflowEffectObservation,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m1908.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1908:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M19-08 evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m1908.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.synthetic.m1908",
        actor_id="actor.synthetic.m1908",
        occurred_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1908.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1908.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m1908.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _request(
    *,
    telemetry: tuple[TelemetryObservation, ...] | None = None,
    support_drift: tuple[SupportDriftObservation, ...] | None = None,
    workflow_effects: tuple[WorkflowEffectObservation, ...] | None = None,
    discrepancies: tuple[DiscrepancyObservation, ...] | None = None,
    rollback_policy: RollbackPolicy | None = None,
) -> MonitorProteotypeTranslationHealthRequest:
    health = _artifact("health")
    evidence = (_evidence(health),)
    upstream = _artifact(
        "upstream",
        "application/vnd.glio-proteogen.m19-07+json",
    )
    rollback = _artifact("rollback")
    source = (upstream, rollback, health)
    return MonitorProteotypeTranslationHealthRequest(
        request_id="request.synthetic.m1908",
        context=_context(),
        upstream_result=upstream,
        telemetry=telemetry
        if telemetry is not None
        else (
            TelemetryObservation(
                observation_id="observation.m1908.telemetry",
                metric_name="translation_latency",
                observed_value=1.0,
                baseline_value=1.0,
                allowed_delta=0.2,
                status=ObservationStatus.PASS,
                evidence=evidence,
            ),
        ),
        support_drift=support_drift
        if support_drift is not None
        else (
            SupportDriftObservation(
                observation_id="observation.m1908.support",
                support_dimension="assay_support",
                baseline_status="supported",
                current_status="supported",
                status=ObservationStatus.PASS,
                evidence=evidence,
            ),
        ),
        workflow_effects=workflow_effects
        if workflow_effects is not None
        else (
            WorkflowEffectObservation(
                observation_id="observation.m1908.workflow",
                workflow="translation_export",
                effect_description="synthetic workflow remains in envelope",
                status=ObservationStatus.PASS,
                evidence=evidence,
            ),
        ),
        discrepancies=discrepancies
        if discrepancies is not None
        else (
            DiscrepancyObservation(
                discrepancy_id="discrepancy.m1908.synthetic",
                description="synthetic discrepancy is resolved",
                resolved=True,
                status=ObservationStatus.PASS,
                evidence=evidence,
            ),
        ),
        rollback_policy=rollback_policy
        or RollbackPolicy(
            policy_id="rollback-policy.m1908.synthetic",
            version="1.0.0",
            critical_failure_threshold=2,
            rollback_target_version="0.9.0",
            rollback_artifact=rollback,
            suspension_reason="synthetic critical translation drift",
            evidence=evidence,
        ),
        source_artifacts=source,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m1908_synthetic_supported",
            rationale="Synthetic fixture declares supported monitoring evidence.",
        ),
    )


def test_authority_metadata_is_locked_to_the_verified_dossier() -> None:
    assert M1908_DOSSIER_SHA256 == (
        "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M1908_DOSSIER_SLICE.endswith(":6824-6864")


def test_request_is_strict_and_binds_the_m19_07_media_type() -> None:
    request = _request()
    assert (
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(request.model_dump(mode="json")), strict=True
        )
        == request
    )
    payload = request.model_dump(mode="json")
    payload["telemetry"][0]["allowed_delta"] = "0.2"
    with pytest.raises(ValidationError):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
    payload = request.model_dump(mode="json")
    payload["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="M19-07"):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_nonfinite_telemetry_is_rejected() -> None:
    payload = _request().telemetry[0].model_dump(mode="json") | {"observed_value": float("nan")}
    with pytest.raises(ValidationError):
        TelemetryObservation.model_validate(payload, strict=True)


def test_source_artifact_closure_rejects_missing_or_duplicate_bindings() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["source_artifacts"] = [payload["source_artifacts"][1]]
    with pytest.raises(ValidationError, match="upstream result"):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
    payload = request.model_dump(mode="json")
    payload["source_artifacts"] = payload["source_artifacts"] + [payload["source_artifacts"][0]]
    with pytest.raises(ValidationError, match="unique"):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_evidence_cannot_escape_the_declared_source_bundle() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    unknown = _evidence(_artifact("not-in-source"))
    payload["telemetry"][0]["evidence"] = [unknown.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="unknown source artifact"):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_health_report_requires_exact_state_decision_pair() -> None:
    request = _request()
    report = TranslationHealthReport(
        report_id="report.m1908.synthetic",
        version="0.1.0-provisional",
        telemetry=request.telemetry,
        support_drift=request.support_drift,
        workflow_effects=request.workflow_effects,
        discrepancies=request.discrepancies,
        health_state=TranslationHealthState.HEALTHY,
        rollback_decision=RollbackDecision.NONE,
        rollback_policy=request.rollback_policy,
        evidence=(_evidence(_artifact("health")),),
    )
    assert report.health_state is TranslationHealthState.HEALTHY
    payload = report.model_dump(mode="json")
    payload["health_state"] = "degraded"
    with pytest.raises(ValidationError, match="decision"):
        TranslationHealthReport.model_validate(payload, strict=True)


def test_health_ids_are_unique_across_all_observation_kinds() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["discrepancies"][0]["discrepancy_id"] = payload["telemetry"][0]["observation_id"]
    with pytest.raises(ValidationError, match="observation ids"):
        MonitorProteotypeTranslationHealthRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
