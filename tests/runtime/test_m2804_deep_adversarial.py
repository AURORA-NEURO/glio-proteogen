"""Deep adversarial closure for M28-04 cross-reference and replay invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m28_04 import (
    AccessProtocol,
    AsyncJobRecord,
    AuditEvent,
    AuthorizationDecision,
    AuthorizationRecord,
    CompatibilityRule,
    CompatibilityStatus,
    GatewayConfiguration,
    GatewayOperation,
    GatewayStatus,
    IdempotencyRecord,
    JobStatus,
    OperationStatus,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m28_04.v1 import _validate_gateway_collections
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway import (
    GatewaySubmission,
    M2804AuthorizationError,
    M2804GatewayEngine,
    M2804Plugin,
    M2804ReplayError,
    M2804Service,
    M2804TokenError,
    publish_protein_rna_discordance_access_surface,
)
from tests.runtime.test_m2804_runtime import _evidence, _request


@pytest.mark.parametrize(
    ("status", "result_artifact", "error_code"),
    [
        (JobStatus.SUCCEEDED, None, None),
        (JobStatus.ABSTAINED, _request().jobs[0].result_artifact, None),
        (JobStatus.FAILED, None, None),
        (JobStatus.QUEUED, None, "m2804.error.unexpected"),
    ],
)
def test_every_async_terminal_outcome_is_closed(
    status: JobStatus, result_artifact: object, error_code: str | None
) -> None:
    request = _request()
    with pytest.raises(ValidationError):
        AsyncJobRecord(
            job_id="m2804.job.invalid-outcome",
            operation_id=request.operations[0].operation_id,
            status=status,
            idempotency=request.idempotency_records[0],
            result_artifact=result_artifact,  # type: ignore[arg-type]
            error_code=error_code,
            evidence=(_evidence(),),
        )


def test_all_request_cross_references_are_closed() -> None:
    request = _request()
    for field in (
        "authorizations",
        "idempotency_records",
        "jobs",
        "compatibility_rules",
        "audit_events",
    ):
        candidate = request.model_dump(mode="json")
        candidate[field][0]["operation_id"] = "m2804.unknown-operation"
        with pytest.raises(ValidationError):
            PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate_json(
                canonical_json_bytes(candidate)
            )
    for field in (
        "authorizations",
        "idempotency_records",
        "jobs",
        "compatibility_rules",
        "audit_events",
    ):
        candidate = request.model_dump(mode="json")
        candidate[field].append(dict(candidate[field][0]))
        with pytest.raises(ValidationError):
            PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate(candidate)
    candidate = request.model_dump(mode="json")
    candidate["jobs"][0]["idempotency"]["idempotency_id"] = "m2804.unknown-idempotency"
    with pytest.raises(ValidationError):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate_json(
            canonical_json_bytes(candidate)
        )


def test_collection_validator_closes_each_typed_reference_path() -> None:
    request = _request()
    operations = request.operations
    authorizations = request.authorizations
    idempotency = request.idempotency_records
    jobs = request.jobs
    compatibility = request.compatibility_rules
    audit = request.audit_events
    configuration = request.configuration

    def check(  # noqa: PLR0913
        *,
        operations_: tuple[GatewayOperation, ...] = operations,
        authorizations_: tuple[AuthorizationRecord, ...] = authorizations,
        idempotency_: tuple[IdempotencyRecord, ...] = idempotency,
        jobs_: tuple[AsyncJobRecord, ...] = jobs,
        compatibility_: tuple[CompatibilityRule, ...] = compatibility,
        audit_: tuple[AuditEvent, ...] = audit,
        configuration_: GatewayConfiguration = configuration,
    ) -> None:
        with pytest.raises(
            ValueError,
            match=r"(gateway|authorization|idempotency|async|compatibility|audit|protocol)",
        ):
            _validate_gateway_collections(
                operations=operations_,
                authorizations=authorizations_,
                idempotency_records=idempotency_,
                jobs=jobs_,
                compatibility_rules=compatibility_,
                audit_events=audit_,
                configuration=configuration_,
            )

    check(operations_=(operations[0], operations[0]))
    check(authorizations_=(authorizations[0], authorizations[0]))
    check(idempotency_=(idempotency[0], idempotency[0]))
    check(jobs_=(jobs[0], jobs[0]))
    check(compatibility_=(compatibility[0], compatibility[0]))
    check(audit_=(audit[0], audit[0]))
    check(authorizations_=(authorizations[0].model_copy(update={"operation_id": "m2804.unknown"}),))
    check(idempotency_=(idempotency[0].model_copy(update={"operation_id": "m2804.unknown"}),))
    check(jobs_=(jobs[0].model_copy(update={"operation_id": "m2804.unknown"}),))
    check(
        jobs_=(
            jobs[0].model_copy(
                update={
                    "idempotency": idempotency[0].model_copy(
                        update={"idempotency_id": "m2804.unknown"}
                    )
                }
            ),
        )
    )
    check(compatibility_=(compatibility[0].model_copy(update={"operation_id": "m2804.unknown"}),))
    check(audit_=(audit[0].model_copy(update={"operation_id": "m2804.unknown"}),))
    check(
        configuration_=GatewayConfiguration(
            configuration_id="m2804.configuration.cli-only",
            version="1.0.0",
            supported_protocols=(AccessProtocol.CLI,),
            evidence=(_evidence(),),
        )
    )


def test_configuration_duplicate_protocols_and_canonical_mapping() -> None:
    with pytest.raises(ValidationError):
        GatewayConfiguration(
            configuration_id="m2804.configuration.duplicate",
            version="1.0.0",
            supported_protocols=(AccessProtocol.API, AccessProtocol.API),
            evidence=(_evidence(),),
        )
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    assert sha256_digest({"m28": "04"}).startswith("sha256:")


def test_engine_rejects_hostile_types_and_service_descriptor() -> None:
    engine = M2804GatewayEngine()
    with pytest.raises(M2804AuthorizationError):
        engine.publish(object())
    with pytest.raises(M2804AuthorizationError):
        engine.publish(b"not-json")
    request = _request()
    result = engine.publish(request)
    assert engine.replay(result) == result
    assert M2804Service().descriptor["provisional_abi"] is True
    with pytest.raises(M2804ReplayError):
        engine.replay(object())
    for update in (
        {"request_digest": "sha256:" + "d" * 64},
        {"result_id": "gateway.m2804.forged"},
        {"result_digest": "sha256:" + "e" * 64},
    ):
        with pytest.raises(M2804ReplayError):
            engine.replay(result.model_copy(update=update))
    altered = result.model_copy(update={"findings": ()})
    altered = altered.model_copy(update={"result_digest": result_payload_digest(altered)})
    with pytest.raises(M2804ReplayError):
        engine.replay(altered)
    assert publish_protein_rna_discordance_access_surface(request) == result


def test_preflight_rejects_non_mapping_nested_references() -> None:
    with pytest.raises(M2804AuthorizationError):
        M2804GatewayEngine().publish({"context": {"references": 1}})


def test_plugin_rejects_forged_and_wrong_tokens() -> None:
    plugin = M2804Plugin()
    with pytest.raises(M2804TokenError):
        plugin.validate(object())  # type: ignore[arg-type]
    with pytest.raises(M2804TokenError):
        plugin.run(object())  # type: ignore[arg-type]
    token = plugin.validate(GatewaySubmission(_request()))
    assert plugin.validate_request(_request()).request_id.startswith("m2804.request")
    assert token.request.request_id.startswith("m2804.request")
    token._seal = object()
    with pytest.raises(M2804TokenError):
        plugin.run(token)
    assert plugin.replay(M2804GatewayEngine().publish(_request())).status.value == "published"


def test_each_finding_path_abstains() -> None:
    request = _request()
    engine = M2804GatewayEngine()
    disabled = request.model_copy(
        update={
            "operations": (
                request.operations[0].model_copy(update={"status": OperationStatus.DISABLED}),
            )
        }
    )
    queued = request.model_copy(
        update={"jobs": (request.jobs[0].model_copy(update={"status": JobStatus.QUEUED}),)}
    )
    incompatible = request.model_copy(
        update={
            "compatibility_rules": (
                request.compatibility_rules[0].model_copy(
                    update={"status": CompatibilityStatus.INCOMPATIBLE}
                ),
            )
        }
    )
    assert engine.publish(disabled).status.value == "abstained"
    assert engine.publish(queued).status.value == "abstained"
    assert engine.publish(incompatible).status.value == "abstained"


def test_service_rejects_untrusted_request_and_result_types() -> None:
    service = M2804Service()
    with pytest.raises((TypeError, ValueError)):
        service.validate_request(object())
    with pytest.raises(TypeError):
        service.replay(object())
    request = _request()
    assert (
        service.validate_request(request.model_dump(mode="json")).request_id == request.request_id
    )
    result = service.publish(request)
    assert service.replay(result.model_dump_json()) == result


def test_result_envelope_rejects_status_mismatches() -> None:
    request = _request()
    baseline = M2804GatewayEngine().publish(request)
    published = baseline.model_copy(update={"access_surface": None})
    with pytest.raises(ValidationError):
        type(baseline).model_validate(published)
    published = baseline.model_copy(update={"request_digest": "sha256:" + "d" * 64})
    with pytest.raises(ValidationError):
        type(baseline).model_validate(published)
    published = baseline.model_copy(update={"result_id": "gateway.m2804.forged"})
    with pytest.raises(ValidationError):
        type(baseline).model_validate(published)
    denied = request.model_copy(
        update={
            "authorizations": (
                request.authorizations[0].model_copy(
                    update={"decision": AuthorizationDecision.DENY}
                ),
            )
        }
    )
    abstained = M2804GatewayEngine().publish(denied)
    invalid = abstained.model_copy(update={"access_surface": baseline.access_surface})
    with pytest.raises(ValidationError):
        type(abstained).model_validate(invalid)
    invalid = abstained.model_copy(update={"result_digest": "sha256:" + "e" * 64})
    with pytest.raises(ValidationError):
        type(abstained).model_validate(invalid)
    published = baseline.model_copy(update={"findings": abstained.findings})
    with pytest.raises(ValidationError):
        type(baseline).model_validate(published)
    assert abstained.status is GatewayStatus.ABSTAINED
    assert abstained.support_decision.status is SupportStatus.REVIEW_REQUIRED
