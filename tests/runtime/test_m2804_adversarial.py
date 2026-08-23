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


def test_request_rejects_duplicate_source_identity() -> None:
    request = _request()
    duplicate = request.source_artifacts[0]
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts, duplicate)
    with pytest.raises(ValidationError, match="source artifact ids must be unique"):
        PublishProteinRnaDiscordanceAccessSurfaceRequest.model_validate(payload, strict=True)


def test_result_rejects_duplicate_findings_and_evidence() -> None:
    result = M2804GatewayEngine().publish(_request())
    duplicate_finding = result.model_copy(
        update={"findings": (*result.findings, result.findings[0])}
    )
    with pytest.raises(ValidationError, match="finding ids must be unique"):
        type(result).model_validate(duplicate_finding.model_dump(mode="python"), strict=True)

    duplicate_evidence = result.model_copy(
        update={"evidence": (*result.evidence, result.evidence[0])}
    )
    with pytest.raises(ValidationError, match="result evidence must be unique"):
        type(result).model_validate(duplicate_evidence.model_dump(mode="python"), strict=True)


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
