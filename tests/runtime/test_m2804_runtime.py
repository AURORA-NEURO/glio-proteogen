"""Deterministic M28-04 runtime, abstention, and replay tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m28_04 import (
    M2804_OUTPUT_MEDIA_TYPE,
    AccessProtocol,
    AsyncJobRecord,
    AuditEvent,
    AuthorizationDecision,
    AuthorizationRecord,
    CompatibilityRule,
    CompatibilityStatus,
    GatewayConfiguration,
    GatewayError,
    GatewayOperation,
    GatewayStatus,
    IdempotencyRecord,
    JobStatus,
    OperationStatus,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
    result_identifier,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway import (
    GatewaySubmission,
    M2804AuthorizationError,
    M2804GatewayEngine,
    M2804Plugin,
    M2804ReplayError,
    M2804Service,
)


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2804.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact("evidence"),
        role="evidence",
        claim="Caller-declared M28-04 gateway evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2804.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2804.actor.gateway",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2804.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2804.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    request_id: str = "m2804.request.gateway",
) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
    evidence = (_evidence(),)
    operation = GatewayOperation(
        operation_id="m2804.operation.read",
        name="Read protein-RNA discordance access surface",
        version="1.0.0",
        protocol=AccessProtocol.API,
        request_media_type="application/json",
        response_media_type=M2804_OUTPUT_MEDIA_TYPE,
        authorization_scope="protein-rna-discordance:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=True,
        evidence=evidence,
    )
    authorization = AuthorizationRecord(
        authorization_id="m2804.authorization.read",
        operation_id=operation.operation_id,
        principal_id="m2804.principal.reader",
        scope=operation.authorization_scope,
        decision=AuthorizationDecision.ALLOW,
        policy_version="1.0.0",
        evidence=evidence,
    )
    idempotency = IdempotencyRecord(
        idempotency_id="m2804.idempotency.read",
        operation_id=operation.operation_id,
        key_digest=sha256_digest({"key": "m2804-key"}),
        request_digest="sha256:" + "b" * 64,
        evidence=evidence,
    )
    job = AsyncJobRecord(
        job_id="m2804.job.read",
        operation_id=operation.operation_id,
        status=JobStatus.SUCCEEDED,
        idempotency=idempotency,
        result_artifact=_artifact("job-result"),
        evidence=evidence,
    )
    compatibility = CompatibilityRule(
        rule_id="m2804.compatibility.read",
        operation_id=operation.operation_id,
        from_version="1.0.0",
        to_version="1.0.0",
        status=CompatibilityStatus.COMPATIBLE,
        migration_statement="No migration required.",
        evidence=evidence,
    )
    audit = AuditEvent(
        event_id="m2804.audit.read",
        operation_id=operation.operation_id,
        principal_id=authorization.principal_id,
        event_type="access",
        outcome="allowed",
        request_digest="sha256:" + "c" * 64,
        evidence=evidence,
    )
    configuration = GatewayConfiguration(
        configuration_id="m2804.configuration.gateway",
        version="1.0.0",
        supported_protocols=(AccessProtocol.API, AccessProtocol.SDK, AccessProtocol.CLI),
        evidence=evidence,
    )
    sources = (_artifact("mass-spectrometry"), _artifact("genome-transcriptome"), _artifact("ptm"))
    return PublishProteinRnaDiscordanceAccessSurfaceRequest(
        request_id=request_id,
        context=_context(request_id),
        mass_spectrometry_proteome=sources[0],
        genome_transcriptome=sources[1],
        ptm_annotations=sources[2],
        operations=(operation,),
        authorizations=(authorization,),
        idempotency_records=(idempotency,),
        jobs=(job,),
        compatibility_rules=(compatibility,),
        errors=(
            GatewayError(
                error_id="m2804.error.denied",
                code="authorization_denied",
                message="The operation is not authorized.",
                retryable=False,
                evidence=evidence,
            ),
        ),
        audit_events=(audit,),
        configuration=configuration,
        source_artifacts=sources,
    )


def test_published_surface_is_deterministic_and_replayable() -> None:
    request = _request()
    engine = M2804GatewayEngine()
    first = engine.publish(request)
    second = M2804Service().publish(request.model_dump_json())
    assert first == second
    assert first.status is GatewayStatus.PUBLISHED
    assert first.access_surface is not None
    assert first.result_id == result_identifier(first.request_digest)
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert engine.replay(first) == first


def test_denied_operation_abstains_without_surface() -> None:
    request = _request()
    denied = request.authorizations[0].model_copy(update={"decision": AuthorizationDecision.DENY})
    result = M2804GatewayEngine().publish(request.model_copy(update={"authorizations": (denied,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert result.access_surface is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_unresolved_job_abstains_without_surface() -> None:
    request = _request()
    queued = request.jobs[0].model_copy(update={"status": JobStatus.QUEUED})
    result = M2804GatewayEngine().publish(request.model_copy(update={"jobs": (queued,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert any(item.code.value == "async_job_unbound" for item in result.findings)


def test_authorization_preflight_fails_closed() -> None:
    request = _request()
    references = request.context.references.model_copy(
        update={
            "support": request.context.references.support.model_copy(update={"state": "rejected"})
        }
    )
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2804AuthorizationError):
        M2804GatewayEngine().publish(denied)


def test_service_rejects_custom_mapping_and_tampered_replay() -> None:
    class HostileDict(dict[str, object]):
        def get(self, key: str, _default: object = None) -> object:
            del key
            del _default
            raise AssertionError

    request = _request()
    with pytest.raises((TypeError, M2804AuthorizationError)):
        M2804Service().publish(HostileDict(request.model_dump(mode="json")))
    result = M2804Service().publish(request.model_dump_json())
    tampered = result.model_dump(mode="json")
    tampered["result_id"] = "gateway.m2804.forged"
    with pytest.raises((M2804ReplayError, ValidationError)):
        M2804Service().replay(tampered)


def test_plugin_requires_sealed_token_and_matches_service() -> None:
    plugin = M2804Plugin()
    request = _request()
    token = plugin.validate(GatewaySubmission(request.model_dump_json()))
    assert plugin.run(token) == M2804Service().publish(request.model_dump_json())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
