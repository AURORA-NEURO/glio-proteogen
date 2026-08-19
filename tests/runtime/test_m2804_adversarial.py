"""Adversarial closure for M28-04 cross-reference and replay invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m28_04 import (
    AccessProtocol,
    AsyncJobRecord,
    GatewayConfiguration,
    JobStatus,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.engine import (
    M2804GatewayEngine,
)
from tests.runtime.test_m2804_runtime import _evidence, _request


def test_job_cannot_bind_another_operation() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        AsyncJobRecord(
            job_id=request.jobs[0].job_id,
            operation_id=request.operations[0].operation_id,
            status=JobStatus.SUCCEEDED,
            idempotency=request.idempotency_records[0].model_copy(
                update={"operation_id": "m2804.other"}
            ),
            result_artifact=request.jobs[0].result_artifact,
            evidence=(_evidence(),),
        )


def test_request_rejects_unknown_job_idempotency_reference() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["idempotency_records"] = []
    with pytest.raises(ValidationError):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate_json(
            canonical_json_bytes(payload)
        )


def test_request_rejects_duplicate_operation_and_protocol_mismatch() -> None:
    request = _request()
    operation = request.operations[0]
    payload = request.model_dump(mode="json")
    payload["operations"] = [operation.model_dump(mode="json"), operation.model_dump(mode="json")]
    with pytest.raises(ValidationError):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate_json(
            canonical_json_bytes(payload)
        )
    disabled_config = GatewayConfiguration(
        configuration_id="m2804.configuration.cli-only",
        version="1.0.0",
        supported_protocols=(AccessProtocol.CLI,),
        evidence=(_evidence(),),
    )
    payload["operations"] = [operation.model_dump(mode="json")]
    payload["configuration"] = disabled_config.model_dump(mode="json")
    with pytest.raises(ValidationError):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate(payload)


def test_request_requires_each_operation_control_record() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    second = request.operations[0].model_dump(mode="json")
    second["operation_id"] = "m2804.operation.write"
    payload["operations"] = [payload["operations"][0], second]
    with pytest.raises(ValidationError, match="every gateway operation"):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate_json(
            canonical_json_bytes(payload)
        )


def test_queued_job_cannot_carry_an_error_or_result() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        AsyncJobRecord(
            job_id="m2804.job.invalid",
            operation_id=request.operations[0].operation_id,
            status=JobStatus.QUEUED,
            idempotency=request.idempotency_records[0],
            error_code="gateway.error",
            evidence=(_evidence(),),
        )


def test_result_rejects_unbound_input_provenance() -> None:
    result = M2804GatewayEngine().publish(_request())
    payload = result.model_dump(mode="json")
    payload["provenance"]["input_digests"] = payload["provenance"]["input_digests"][1:]
    with pytest.raises(ValidationError, match="every declared input artifact"):
        type(result).model_validate_json(canonical_json_bytes(payload))


def test_result_rejects_unbound_control_provenance() -> None:
    result = M2804GatewayEngine().publish(_request())
    payload = result.model_dump(mode="json")
    payload["provenance"]["control_decisions"][0]["decision_id"] = "m2804.forged"
    with pytest.raises(ValidationError, match="control is not request-bound"):
        type(result).model_validate_json(canonical_json_bytes(payload))


def test_result_rejects_provenance_metadata_drift() -> None:
    result = M2804GatewayEngine().publish(_request())
    cases = (
        ("module_id", "GLIO-PROTEOGEN-M28-05", "module does not match"),
        ("module_version", "0.2.0", "version does not match"),
        ("activity_id", "m2804.activity.forged", "activity does not bind"),
        ("consent_decision_id", "m2804.forged", "consent decision is not"),
        ("consent_state", "revoked", "consent state is not"),
        ("consent_policy_version", "2.0.0", "consent policy is not"),
        ("consent_evidence_digest", "sha256:" + "f" * 64, "consent evidence is not"),
    )
    for field, value, message in cases:
        payload = result.model_dump(mode="json")
        payload["provenance"][field] = value
        with pytest.raises(ValidationError, match=message):
            type(result).model_validate_json(canonical_json_bytes(payload))

    payload = result.model_dump(mode="json")
    for record in payload["provenance"]["control_decisions"]:
        if record["role"] == "identity_lineage":
            record["subject_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="identity control is not"):
        type(result).model_validate_json(canonical_json_bytes(payload))
