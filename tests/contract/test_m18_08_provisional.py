"""Focused contract/schema and identity closure for provisional M18-08."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_08 import (
    M1808_OUTPUT_MEDIA_TYPE,
    M1808_PROVISIONAL_ABI,
    RollbackDecision,
    TranslationFindingCode,
    TranslationHealthState,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c18_spatial_proteomics import (
    m18_08_translation_monitoring_service as m1808,
)
from tests.runtime.test_m18_08_monitoring import _request

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_translation_health_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["usageTelemetryRequired"]
        and schema["x-glio-contract"]["supportDriftRequired"]
        and schema["x-glio-contract"]["workflowEffectsRequired"]
        and schema["x-glio-contract"]["discrepanciesRequired"]
        and schema["x-glio-contract"]["suspensionRollbackRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m18-07+json")
        and schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1808_OUTPUT_MEDIA_TYPE
    assert M1808_PROVISIONAL_ABI is True


def test_health_and_rollback_states_are_explicit() -> None:
    assert TranslationHealthState.ROLLBACK_REQUIRED.value == "rollback_required"
    assert RollbackDecision.SUSPEND.value == "suspend"
    assert TranslationFindingCode.SUPPORT_DRIFT.value == "support_drift"
    assert str(RollbackDecision.SUSPEND.value) != str(RollbackDecision.NONE.value)


def test_request_closes_artifact_identity_not_only_artifact_ids() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["source_artifacts"][1]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="upstream result"):
        type(request).model_validate_json(canonical_json_bytes(payload), strict=True)


def test_request_rejects_digest_aliases_and_forged_evidence() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["source_artifacts"][0]["digest"] = payload["source_artifacts"][1]["digest"]
    with pytest.raises(ValidationError, match="digests must be unique"):
        type(request).model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = request.model_dump(mode="json")
    payload["telemetry"][0]["evidence"][0]["reference"]["media_type"] = "text/plain"
    with pytest.raises(ValidationError, match="unknown source artifact"):
        type(request).model_validate_json(canonical_json_bytes(payload), strict=True)


def test_result_closes_deterministic_ids_report_and_request_observations() -> None:
    result = m1808.M1808TranslationMonitoringEngine().infer(_request())
    payload = result.model_dump(mode="json")
    payload["result_id"] = "result.forged"
    with pytest.raises(ValidationError, match="result id"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = result.model_dump(mode="json")
    payload["health_report"]["telemetry"][0]["metric_name"] = "forged_metric"
    with pytest.raises(ValidationError, match="exact request observations"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
