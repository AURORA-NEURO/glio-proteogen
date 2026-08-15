"""Adversarial export contract and replay closure tests for M16-07."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m16_07 import (
    CompatibilityStatus,
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ProteinRnaDiscordanceDownstreamExportResult,
    SignedDownstreamContract,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    M1607ExportEngine,
)
from tests.modules.c16_kinophos_object_consumer.test_m16_07_engine import _request


def test_request_field_and_upstream_binding_closure() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="request downstream field ids"):
        ExportProteinRnaDiscordanceDownstreamContractRequest.model_validate(
            request.model_dump(mode="python") | {"fields": (request.fields[0], request.fields[0])}
        )
    wrong_upstream = request.intended_use_result.model_copy(
        update={"media_type": "application/json"}
    )
    with pytest.raises(ValidationError, match="bind the provisional M16-04"):
        ExportProteinRnaDiscordanceDownstreamContractRequest.model_validate(
            request.model_dump(mode="python") | {"intended_use_result": wrong_upstream}
        )


def test_result_identity_evidence_findings_and_digest_are_closed() -> None:
    result = M1607ExportEngine().export(_request())
    with pytest.raises(ValidationError, match="identifier must be derived"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python") | {"result_id": "result.wrong"}
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python") | {"evidence": ()}
        )
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python")
            | {"findings": (result.findings[0], result.findings[0])}
        )
    with pytest.raises(ValidationError, match="result digest does not match"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python") | {"result_digest": sha256_digest("tampered")}
        )


def test_signed_result_status_closure_rejects_review_mutations() -> None:
    result = M1607ExportEngine().export(_request())
    with pytest.raises(ValidationError, match="signed result requires"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python") | {"human_review_required": True}
        )
    abstained = M1607ExportEngine().export(_request(label="warning"))
    with pytest.raises(ValidationError, match="abstained result requires"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            abstained.model_dump(mode="python") | {"abstention_reason": None}
        )


def test_signed_contract_closure_rejects_duplicate_incompatible_and_partial_fields() -> None:
    result = M1607ExportEngine().export(_request())
    assert result.downstream_contract is not None
    contract = result.downstream_contract
    duplicate = contract.model_dump(mode="python") | {
        "fields": (contract.fields[0], contract.fields[0]),
        "compatibility": contract.compatibility.model_copy(
            update={"accepted_field_ids": (contract.fields[0].field_id,)}
        ),
    }
    with pytest.raises(ValidationError, match="field ids must be unique"):
        SignedDownstreamContract.model_validate(duplicate)
    with pytest.raises(ValidationError, match="requires compatible report"):
        SignedDownstreamContract.model_validate(
            contract.model_dump(mode="python")
            | {
                "compatibility": contract.compatibility.model_copy(
                    update={"status": CompatibilityStatus.REVIEW_REQUIRED}
                )
            }
        )
    with pytest.raises(ValidationError, match="match compatibility"):
        SignedDownstreamContract.model_validate(
            contract.model_dump(mode="python")
            | {
                "compatibility": contract.compatibility.model_copy(
                    update={"accepted_field_ids": ()}
                )
            }
        )


def test_result_request_digest_must_bind_exact_request() -> None:
    result = M1607ExportEngine().export(_request())
    with pytest.raises(ValidationError, match="request digest does not bind"):
        ProteinRnaDiscordanceDownstreamExportResult.model_validate(
            result.model_dump(mode="python") | {"request_digest": sha256_digest("wrong-request")}
        )
