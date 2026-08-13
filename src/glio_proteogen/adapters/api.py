"""FastAPI surface for the active pre-analytic module slices."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Final

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.contracts.m01_01.schema import (
    ContractName as M0101ContractName,
)
from glio_proteogen.contracts.m01_01.schema import (
    contract_json_schema as m0101_contract_json_schema,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    EvaluateMetadataRequest,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.schema import (
    ContractName as M0102ContractName,
)
from glio_proteogen.contracts.m01_02.schema import (
    contract_json_schema as m0102_contract_json_schema,
)
from glio_proteogen.contracts.m01_02.v1 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m01_03.schema import (
    ContractName as M0103ContractName,
)
from glio_proteogen.contracts.m01_03.schema import (
    contract_json_schema as m0103_contract_json_schema,
)
from glio_proteogen.contracts.m01_03.v1 import ValidatedRawInputDescriptor
from glio_proteogen.contracts.m01_04.schema import (
    ContractName as M0104ContractName,
)
from glio_proteogen.contracts.m01_04.schema import (
    contract_json_schema as m0104_contract_json_schema,
)
from glio_proteogen.contracts.m01_04.v1 import (
    ComputeQualityMetricsRequest,
    QualityProfile,
)
from glio_proteogen.contracts.m01_05.schema import (
    ContractName as M0105ContractName,
)
from glio_proteogen.contracts.m01_05.schema import (
    contract_json_schema as m0105_contract_json_schema,
)
from glio_proteogen.contracts.m01_05.v1 import (
    ArtifactDetectionResult,
    DetectArtifactsRequest,
)
from glio_proteogen.contracts.m01_06.schema import (
    ContractName as M0106ContractName,
)
from glio_proteogen.contracts.m01_06.schema import (
    contract_json_schema as m0106_contract_json_schema,
)
from glio_proteogen.contracts.m01_06.v1 import (
    HarmonizationResult,
    HarmonizeObservationsRequest,
)
from glio_proteogen.contracts.m01_07.schema import (
    ContractName as M0107ContractName,
)
from glio_proteogen.contracts.m01_07.schema import (
    contract_json_schema as m0107_contract_json_schema,
)
from glio_proteogen.contracts.m01_07.v1 import (
    RouteSupportRequest,
    SupportRoutingResult,
)
from glio_proteogen.contracts.m01_08.schema import (
    ContractName as M0108ContractName,
)
from glio_proteogen.contracts.m01_08.schema import (
    contract_json_schema as m0108_contract_json_schema,
)
from glio_proteogen.contracts.m02_01.schema import (
    ContractName as M0201ContractName,
)
from glio_proteogen.contracts.m02_01.schema import (
    contract_json_schema as m0201_contract_json_schema,
)
from glio_proteogen.contracts.m02_01.v1 import (
    ConformanceEvaluation as M0201ConformanceEvaluation,
)
from glio_proteogen.contracts.m02_01.v1 import EvaluateConformanceRequest
from glio_proteogen.contracts.m02_02.schema import (
    ContractName as M0202ContractName,
)
from glio_proteogen.contracts.m02_02.schema import (
    contract_json_schema as m0202_contract_json_schema,
)
from glio_proteogen.contracts.m02_02.v1 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.contracts.m02_03.schema import (
    ContractName as M0203ContractName,
)
from glio_proteogen.contracts.m02_03.schema import (
    contract_json_schema as m0203_contract_json_schema,
)
from glio_proteogen.contracts.m02_04.schema import (
    ContractName as M0204ContractName,
)
from glio_proteogen.contracts.m02_04.schema import (
    contract_json_schema as m0204_contract_json_schema,
)
from glio_proteogen.contracts.m02_04.v1 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.contracts.m02_05.schema import (
    ContractName as M0205ContractName,
)
from glio_proteogen.contracts.m02_05.schema import (
    contract_json_schema as m0205_contract_json_schema,
)
from glio_proteogen.contracts.m02_05.v1 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.contracts.m02_06.schema import (
    ContractName as M0206ContractName,
)
from glio_proteogen.contracts.m02_06.schema import (
    contract_json_schema as m0206_contract_json_schema,
)
from glio_proteogen.contracts.m02_06.v1 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.contracts.m02_07.schema import (
    ContractName as M0207ContractName,
)
from glio_proteogen.contracts.m02_07.schema import (
    contract_json_schema as m0207_contract_json_schema,
)
from glio_proteogen.contracts.m02_07.v1 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.contracts.m02_08.schema import (
    ContractName as M0208ContractName,
)
from glio_proteogen.contracts.m02_08.schema import (
    contract_json_schema as m0208_contract_json_schema,
)
from glio_proteogen.contracts.m03_01.schema import (
    ContractName as M0301ContractName,
)
from glio_proteogen.contracts.m03_01.schema import (
    contract_json_schema as m0301_contract_json_schema,
)
from glio_proteogen.contracts.m03_01.v1 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.contracts.m03_02.schema import (
    ContractName as M0302ContractName,
)
from glio_proteogen.contracts.m03_02.schema import (
    contract_json_schema as m0302_contract_json_schema,
)
from glio_proteogen.contracts.m03_02.v1 import (
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_03.schema import (
    ContractName as M0303ContractName,
)
from glio_proteogen.contracts.m03_03.schema import (
    contract_json_schema as m0303_contract_json_schema,
)
from glio_proteogen.contracts.m03_04.schema import (
    ContractName as M0304ContractName,
)
from glio_proteogen.contracts.m03_04.schema import (
    contract_json_schema as m0304_contract_json_schema,
)
from glio_proteogen.contracts.m03_04.v1 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.contracts.m03_05.schema import (
    ContractName as M0305ContractName,
)
from glio_proteogen.contracts.m03_05.schema import (
    contract_json_schema as m0305_contract_json_schema,
)
from glio_proteogen.contracts.m03_05.v1 import (
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.contracts.m03_06.schema import (
    ContractName as M0306ContractName,
)
from glio_proteogen.contracts.m03_06.schema import (
    contract_json_schema as m0306_contract_json_schema,
)
from glio_proteogen.contracts.m03_06.v1 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.contracts.m03_07.schema import (
    ContractName as M0307ContractName,
)
from glio_proteogen.contracts.m03_07.schema import (
    contract_json_schema as m0307_contract_json_schema,
)
from glio_proteogen.contracts.m03_07.v1 import (
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainVerification,
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    ChainIntegrityError,
    ConsentAuthorizationError,
    IdempotencyConflictError,
    InvalidProtocolLookupError,
    M0101Service,
    PayloadTooLargeError,
    ProtocolNotFoundError,
    ProtocolSchemaValidationError,
    ProtocolVersionConflictError,
    UpstreamControlAuthorizationError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainIntegrityError as M0102ChainIntegrityError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification as M0102ChainVerification,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    IdempotencyConflictError as M0102IdempotencyConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
    ResolutionNotFoundError,
    ResolutionSupersessionConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    PayloadTooLargeError as M0102PayloadTooLargeError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    IngestionLimits,
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
    M0105Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    HarmonizationAuthorizationError,
    preflight_harmonization_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.service import (
    M0106Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    SupportRoutingAuthorizationError,
    preflight_support_routing_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.service import (
    M0107Service,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    ConformanceAuthorizationError,
    M0201ConformanceEvaluator,
    preflight_conformance_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    IdentityBindingAuthorizationError,
    M0202IdentityBindingEvaluator,
    preflight_identity_binding_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    IdentificationQualityAuthorizationError,
    M0204Service,
    preflight_identification_quality_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    IdentificationArtifactAuthorizationError,
    M0205Service,
    preflight_identification_artifact_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    IdentificationHarmonizationAuthorizationError,
    M0206Service,
    preflight_identification_harmonization_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    IdentificationSupportAuthorizationError,
    M0207Service,
    preflight_identification_support_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Service,
    ProteinInferenceProtocolAuthorizationError,
    preflight_protein_inference_protocol_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Service,
    ProteinIdentityLineageAuthorizationError,
    preflight_protein_identity_lineage_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Service,
    ProteinInferenceQualityAuthorizationError,
    preflight_protein_inference_quality_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Service,
    ProteinInferenceArtifactAuthorizationError,
    preflight_protein_inference_artifact_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    M0306Service,
    ProteinInferenceHarmonizationAuthorizationError,
    preflight_protein_inference_harmonization_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    M0307Service,
    ProteinInferenceSupportAuthorizationError,
    preflight_protein_inference_support_authorization,
)

_REGISTER_ADAPTER: Final = TypeAdapter(RegisterProtocolRequest)
_EVALUATE_ADAPTER: Final = TypeAdapter(EvaluateMetadataRequest)
_RECONCILE_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)
_QUALITY_ADAPTER: Final = TypeAdapter(ComputeQualityMetricsRequest)
_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectArtifactsRequest)
_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeObservationsRequest)
_SUPPORT_ROUTING_ADAPTER: Final = TypeAdapter(RouteSupportRequest)
_M0201_CONFORMANCE_ADAPTER: Final = TypeAdapter(EvaluateConformanceRequest)
_M0202_BINDING_ADAPTER: Final = TypeAdapter(ValidateIdentityBindingsRequest)
_M0204_QUALITY_ADAPTER: Final = TypeAdapter(ComputeIdentificationQualityRequest)
_M0205_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectIdentificationArtifactsRequest)
_M0206_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeIdentificationEvidenceRequest)
_M0207_SUPPORT_ADAPTER: Final = TypeAdapter(RouteIdentificationSupportRequest)
_M0301_PROTOCOL_ADAPTER: Final = TypeAdapter(EvaluateProteinInferenceProtocolRequest)
_M0302_LINEAGE_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)
_M0304_QUALITY_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)
_M0305_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_M0306_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)
_M0307_SUPPORT_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)
_RESOLUTION_DIGEST_ADAPTER: Final = TypeAdapter(Sha256Digest)
_IDENTIFIER_ADAPTER: Final = TypeAdapter(Identifier)
_MAX_ADVISORY_FILENAME_BYTES: Final = 512
_MAX_CHECKSUM_TEXT_LENGTH: Final = 80
_RAW_API_LIMITS: Final = IngestionLimits(
    max_source_bytes=MAX_REQUEST_BYTES,
    max_decoded_bytes=MAX_REQUEST_BYTES * 4,
)


def _contract_schema(name: M0101ContractName) -> dict[str, object]:
    """Retain the original M01-01 schema helper used by the CLI."""

    return m0101_contract_json_schema(name)


def _identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
    return m0102_contract_json_schema(name)


def _raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
    return m0103_contract_json_schema(name)


def _quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
    return m0104_contract_json_schema(name)


def _artifact_contract_schema(name: M0105ContractName) -> dict[str, object]:
    return m0105_contract_json_schema(name)


def _harmonization_contract_schema(name: M0106ContractName) -> dict[str, object]:
    return m0106_contract_json_schema(name)


def _support_routing_contract_schema(name: M0107ContractName) -> dict[str, object]:
    return m0107_contract_json_schema(name)


def _release_packaging_contract_schema(name: M0108ContractName) -> dict[str, object]:
    return m0108_contract_json_schema(name)


def _identification_contract_schema(name: M0201ContractName) -> dict[str, object]:
    return m0201_contract_json_schema(name)


def _identity_binding_contract_schema(name: M0202ContractName) -> dict[str, object]:
    return m0202_contract_json_schema(name)


def _identification_raw_contract_schema(name: M0203ContractName) -> dict[str, object]:
    return m0203_contract_json_schema(name)


def _identification_quality_contract_schema(name: M0204ContractName) -> dict[str, object]:
    return m0204_contract_json_schema(name)


def _identification_artifact_contract_schema(name: M0205ContractName) -> dict[str, object]:
    return m0205_contract_json_schema(name)


def _identification_harmonization_contract_schema(
    name: M0206ContractName,
) -> dict[str, object]:
    return m0206_contract_json_schema(name)


def _identification_support_contract_schema(
    name: M0207ContractName,
) -> dict[str, object]:
    return m0207_contract_json_schema(name)


def _identification_release_contract_schema(
    name: M0208ContractName,
) -> dict[str, object]:
    return m0208_contract_json_schema(name)


def _protein_inference_protocol_contract_schema(
    name: M0301ContractName,
) -> dict[str, object]:
    return m0301_contract_json_schema(name)


def _protein_inference_lineage_contract_schema(
    name: M0302ContractName,
) -> dict[str, object]:
    return m0302_contract_json_schema(name)


def _protein_inference_raw_contract_schema(
    name: M0303ContractName,
) -> dict[str, object]:
    return m0303_contract_json_schema(name)


def _protein_inference_quality_contract_schema(
    name: M0304ContractName,
) -> dict[str, object]:
    return m0304_contract_json_schema(name)


def _protein_inference_artifact_contract_schema(
    name: M0305ContractName,
) -> dict[str, object]:
    return m0305_contract_json_schema(name)


def _protein_inference_harmonization_contract_schema(
    name: M0306ContractName,
) -> dict[str, object]:
    return m0306_contract_json_schema(name)


def _protein_inference_support_contract_schema(
    name: M0307ContractName,
) -> dict[str, object]:
    return m0307_contract_json_schema(name)


def _request_body(name: M0101ContractName) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0101_contract_json_schema(name)}},
        }
    }


def _identity_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0102_contract_json_schema("request")}},
        }
    }


def _quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0104_contract_json_schema("request")}},
        }
    }


def _artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0105_contract_json_schema("request")}},
        }
    }


def _harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0106_contract_json_schema("request")}},
        }
    }


def _support_routing_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0107_contract_json_schema("request")}},
        }
    }


def _identification_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0201_contract_json_schema("request")}},
        }
    }


def _identity_binding_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0202_contract_json_schema("request")}},
        }
    }


def _identification_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0204_contract_json_schema("request")}},
        }
    }


def _identification_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0205_contract_json_schema("request")}},
        }
    }


def _identification_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0206_contract_json_schema("request")}},
        }
    }


def _identification_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0207_contract_json_schema("request")}},
        }
    }


def _protein_inference_protocol_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0301_contract_json_schema("request")}},
        }
    }


def _protein_inference_lineage_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0302_contract_json_schema("request")}},
        }
    }


def _protein_inference_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0304_contract_json_schema("request")}},
        }
    }


def _protein_inference_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0305_contract_json_schema("request")}},
        }
    }


def _protein_inference_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0306_contract_json_schema("request")}},
        }
    }


def _protein_inference_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0307_contract_json_schema("request")}},
        }
    }


async def _strict_json_body[ModelT](
    request: Request,
    adapter: TypeAdapter[ModelT],
    preflight: Callable[[object], None] | None = None,
    max_bytes: int = MAX_REQUEST_BYTES,
) -> ModelT:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=max_bytes)
        if preflight is not None:
            preflight(decoded)
        return adapter.validate_json(body, strict=True)
    except StrictJsonError as error:
        details = [strict_json_error_detail(error, location_prefix=("body",))]
        raise RequestValidationError(details) from error
    except ValidationError as error:
        details = sanitized_validation_errors(error, location_prefix=("body",))
        raise RequestValidationError(details) from error


async def _register_body(request: Request) -> RegisterProtocolRequest:
    return await _strict_json_body(request, _REGISTER_ADAPTER)


async def _evaluate_body(request: Request) -> EvaluateMetadataRequest:
    return await _strict_json_body(request, _EVALUATE_ADAPTER)


async def _reconcile_body(request: Request) -> ReconcileIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _RECONCILE_ADAPTER,
        preflight_identity_authorization,
    )


async def _quality_body(request: Request) -> ComputeQualityMetricsRequest:
    return await _strict_json_body(request, _QUALITY_ADAPTER)


async def _artifact_body(request: Request) -> DetectArtifactsRequest:
    return await _strict_json_body(request, _ARTIFACT_ADAPTER)


async def _harmonization_body(request: Request) -> HarmonizeObservationsRequest:
    return await _strict_json_body(
        request,
        _HARMONIZATION_ADAPTER,
        preflight_harmonization_authorization,
    )


async def _support_routing_body(request: Request) -> RouteSupportRequest:
    return await _strict_json_body(
        request,
        _SUPPORT_ROUTING_ADAPTER,
        preflight_support_routing_authorization,
    )


async def _identification_body(request: Request) -> EvaluateConformanceRequest:
    return await _strict_json_body(
        request,
        _M0201_CONFORMANCE_ADAPTER,
        preflight_conformance_authorization,
    )


async def _identity_binding_body(request: Request) -> ValidateIdentityBindingsRequest:
    return await _strict_json_body(
        request,
        _M0202_BINDING_ADAPTER,
        preflight_identity_binding_authorization,
    )


async def _identification_quality_body(
    request: Request,
) -> ComputeIdentificationQualityRequest:
    return await _strict_json_body(
        request,
        _M0204_QUALITY_ADAPTER,
        preflight_identification_quality_authorization,
    )


async def _identification_artifact_body(
    request: Request,
) -> DetectIdentificationArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0205_ARTIFACT_ADAPTER,
        preflight_identification_artifact_authorization,
    )


async def _identification_harmonization_body(
    request: Request,
) -> HarmonizeIdentificationEvidenceRequest:
    return await _strict_json_body(
        request,
        _M0206_HARMONIZATION_ADAPTER,
        preflight_identification_harmonization_authorization,
    )


async def _identification_support_body(
    request: Request,
) -> RouteIdentificationSupportRequest:
    return await _strict_json_body(
        request,
        _M0207_SUPPORT_ADAPTER,
        preflight_identification_support_authorization,
    )


async def _protein_inference_protocol_body(
    request: Request,
) -> EvaluateProteinInferenceProtocolRequest:
    return await _strict_json_body(
        request,
        _M0301_PROTOCOL_ADAPTER,
        preflight_protein_inference_protocol_authorization,
    )


async def _protein_inference_lineage_body(
    request: Request,
) -> ReconcileProteinInferenceIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _M0302_LINEAGE_ADAPTER,
        preflight_protein_identity_lineage_authorization,
    )


async def _protein_inference_quality_body(
    request: Request,
) -> ComputeProteinInferenceQualityRequest:
    return await _strict_json_body(
        request,
        _M0304_QUALITY_ADAPTER,
        preflight_protein_inference_quality_authorization,
        M0304_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_artifact_body(
    request: Request,
) -> DetectProteinInferenceArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0305_ARTIFACT_ADAPTER,
        preflight_protein_inference_artifact_authorization,
        M0305_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_harmonization_body(
    request: Request,
) -> HarmonizeProteinInferenceSupportRequest:
    return await _strict_json_body(
        request,
        _M0306_HARMONIZATION_ADAPTER,
        preflight_protein_inference_harmonization_authorization,
        M0306_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_support_body(
    request: Request,
) -> RouteProteinInferenceSupportRequest:
    return await _strict_json_body(
        request,
        _M0307_SUPPORT_ADAPTER,
        preflight_protein_inference_support_authorization,
        M0307_MAX_CANONICAL_REQUEST_BYTES,
    )


def create_app(database_path: Path) -> FastAPI:  # noqa: PLR0915 - central route composition.
    """Create an isolated API instance backed by one append-only event database."""

    store = M0101EventStore(database_path)
    service = M0101Service(store)
    identity_store = M0102EventStore(database_path)
    identity_service = M0102Service(identity_store)
    quality_service = M0104Service()
    artifact_service = M0105Service()
    harmonization_service = M0106Service()
    support_routing_service = M0107Service()
    identification_evaluator = M0201ConformanceEvaluator()
    identity_binding_evaluator = M0202IdentityBindingEvaluator()
    identification_quality_service = M0204Service()
    identification_artifact_service = M0205Service()
    identification_harmonization_service = M0206Service()
    identification_support_service = M0207Service()
    protein_inference_protocol_service = M0301Service()
    protein_inference_lineage_service = M0302Service()
    protein_inference_quality_service = M0304Service()
    protein_inference_artifact_service = M0305Service()
    protein_inference_harmonization_service = M0306Service()
    protein_inference_support_service = M0307Service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        identity_service.close()
        service.close()

    app = FastAPI(
        title="GLIO-PROTEOGEN",
        version="0.1.0",
        description="Research-use-only preanalytic contracts and bounded evidence processing.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

    @app.exception_handler(ProtocolNotFoundError)
    def not_found_handler(_request: Request, error: ProtocolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ProtocolVersionConflictError)
    @app.exception_handler(IdempotencyConflictError)
    def conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(PayloadTooLargeError)
    def payload_handler(_request: Request, error: PayloadTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(ConsentAuthorizationError)
    @app.exception_handler(UpstreamControlAuthorizationError)
    @app.exception_handler(SupportRoutingAuthorizationError)
    @app.exception_handler(ConformanceAuthorizationError)
    @app.exception_handler(IdentityBindingAuthorizationError)
    @app.exception_handler(IdentificationQualityAuthorizationError)
    @app.exception_handler(IdentificationArtifactAuthorizationError)
    @app.exception_handler(IdentificationHarmonizationAuthorizationError)
    @app.exception_handler(IdentificationSupportAuthorizationError)
    @app.exception_handler(ProteinInferenceProtocolAuthorizationError)
    @app.exception_handler(ProteinIdentityLineageAuthorizationError)
    @app.exception_handler(ProteinInferenceQualityAuthorizationError)
    @app.exception_handler(ProteinInferenceArtifactAuthorizationError)
    @app.exception_handler(ProteinInferenceHarmonizationAuthorizationError)
    @app.exception_handler(ProteinInferenceSupportAuthorizationError)
    def authorization_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(InvalidProtocolLookupError)
    def lookup_input_handler(
        _request: Request,
        error: InvalidProtocolLookupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ProtocolSchemaValidationError)
    def schema_handler(
        _request: Request,
        error: ProtocolSchemaValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": str(error),
                "issues": [issue.model_dump(mode="json") for issue in error.issues],
            },
        )

    @app.exception_handler(ChainIntegrityError)
    def integrity_handler(_request: Request, error: ChainIntegrityError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(ResolutionNotFoundError)
    def identity_not_found_handler(
        _request: Request,
        error: ResolutionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(M0102IdempotencyConflictError)
    @app.exception_handler(ResolutionSupersessionConflictError)
    def identity_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(M0102PayloadTooLargeError)
    def identity_payload_handler(
        _request: Request,
        error: M0102PayloadTooLargeError,
    ) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(IdentityLineageAuthorizationError)
    def identity_authorization_handler(
        _request: Request,
        error: IdentityLineageAuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(HarmonizationAuthorizationError)
    def harmonization_authorization_handler(
        _request: Request,
        error: HarmonizationAuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(M0102ChainIntegrityError)
    @app.exception_handler(M0102EventStoreError)
    def identity_integrity_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/healthz", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "alive", "module": "GLIO-PROTEOGEN-M01-01"}

    @app.get("/readyz", response_model=ChainVerification, tags=["operations"])
    def readiness() -> ChainVerification:
        _require_valid_identity_chain(identity_service.verify_event_chain())
        return _require_valid_chain(service.verify_event_chain())

    @app.get("/v1/contracts/M01-01/{name}/schema", tags=["contracts"])
    def contract_schema(name: M0101ContractName) -> dict[str, object]:
        return _contract_schema(name)

    @app.get("/v1/contracts/M01-02/{name}/schema", tags=["contracts"])
    def identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
        return _identity_contract_schema(name)

    @app.get("/v1/contracts/M01-03/{name}/schema", tags=["contracts"])
    def raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
        return _raw_contract_schema(name)

    @app.get("/v1/contracts/M01-04/{name}/schema", tags=["contracts"])
    def quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
        return _quality_contract_schema(name)

    @app.get("/v1/contracts/M01-05/{name}/schema", tags=["contracts"])
    def artifact_contract_schema(name: M0105ContractName) -> dict[str, object]:
        return _artifact_contract_schema(name)

    @app.get("/v1/contracts/M01-06/{name}/schema", tags=["contracts"])
    def harmonization_contract_schema(name: M0106ContractName) -> dict[str, object]:
        return _harmonization_contract_schema(name)

    @app.get("/v1/contracts/M01-07/{name}/schema", tags=["contracts"])
    def support_routing_contract_schema(name: M0107ContractName) -> dict[str, object]:
        return _support_routing_contract_schema(name)

    @app.get("/v1/contracts/M01-08/{name}/schema", tags=["contracts"])
    def release_packaging_contract_schema(name: M0108ContractName) -> dict[str, object]:
        return _release_packaging_contract_schema(name)

    @app.get("/v1/contracts/M02-01/{name}/schema", tags=["contracts"])
    def identification_contract_schema(name: M0201ContractName) -> dict[str, object]:
        return _identification_contract_schema(name)

    @app.post(
        "/v1/modules/M02-01/conformance",
        response_model=M0201ConformanceEvaluation,
        tags=["M02-01"],
        openapi_extra=_identification_request_body(),
    )
    def evaluate_identification_metadata(
        request: Annotated[EvaluateConformanceRequest, Depends(_identification_body)],
    ) -> M0201ConformanceEvaluation:
        return identification_evaluator.evaluate(request)

    @app.get("/v1/contracts/M02-02/{name}/schema", tags=["contracts"])
    def identity_binding_contract_schema(name: M0202ContractName) -> dict[str, object]:
        return _identity_binding_contract_schema(name)

    @app.get("/v1/contracts/M02-03/{name}/schema", tags=["contracts"])
    def identification_raw_contract_schema(name: M0203ContractName) -> dict[str, object]:
        return _identification_raw_contract_schema(name)

    @app.get("/v1/contracts/M02-04/{name}/schema", tags=["contracts"])
    def identification_quality_contract_schema(name: M0204ContractName) -> dict[str, object]:
        return _identification_quality_contract_schema(name)

    @app.get("/v1/contracts/M02-05/{name}/schema", tags=["contracts"])
    def identification_artifact_contract_schema(name: M0205ContractName) -> dict[str, object]:
        return _identification_artifact_contract_schema(name)

    @app.get("/v1/contracts/M02-06/{name}/schema", tags=["contracts"])
    def identification_harmonization_contract_schema(
        name: M0206ContractName,
    ) -> dict[str, object]:
        return _identification_harmonization_contract_schema(name)

    @app.get("/v1/contracts/M02-07/{name}/schema", tags=["contracts"])
    def identification_support_contract_schema(
        name: M0207ContractName,
    ) -> dict[str, object]:
        return _identification_support_contract_schema(name)

    @app.get("/v1/contracts/M02-08/{name}/schema", tags=["contracts"])
    def identification_release_contract_schema(
        name: M0208ContractName,
    ) -> dict[str, object]:
        return _identification_release_contract_schema(name)

    @app.get("/v1/contracts/M03-01/{name}/schema", tags=["contracts"])
    def protein_inference_protocol_contract_schema(
        name: M0301ContractName,
    ) -> dict[str, object]:
        return _protein_inference_protocol_contract_schema(name)

    @app.get("/v1/contracts/M03-02/{name}/schema", tags=["contracts"])
    def protein_inference_lineage_contract_schema(
        name: M0302ContractName,
    ) -> dict[str, object]:
        return _protein_inference_lineage_contract_schema(name)

    @app.get("/v1/contracts/M03-03/{name}/schema", tags=["contracts"])
    def protein_inference_raw_contract_schema(
        name: M0303ContractName,
    ) -> dict[str, object]:
        return _protein_inference_raw_contract_schema(name)

    @app.get("/v1/contracts/M03-04/{name}/schema", tags=["contracts"])
    def protein_inference_quality_contract_schema(
        name: M0304ContractName,
    ) -> dict[str, object]:
        return _protein_inference_quality_contract_schema(name)

    @app.get("/v1/contracts/M03-05/{name}/schema", tags=["contracts"])
    def protein_inference_artifact_contract_schema(
        name: M0305ContractName,
    ) -> dict[str, object]:
        return _protein_inference_artifact_contract_schema(name)

    @app.post(
        "/v1/modules/M03-05/artifacts",
        response_model=ProteinInferenceArtifactDetectionResult,
        tags=["M03-05"],
        openapi_extra=_protein_inference_artifact_request_body(),
    )
    def detect_protein_inference_artifacts(
        request: Annotated[
            DetectProteinInferenceArtifactsRequest,
            Depends(_protein_inference_artifact_body),
        ],
    ) -> ProteinInferenceArtifactDetectionResult:
        return protein_inference_artifact_service.execute(request)

    @app.get("/v1/contracts/M03-06/{name}/schema", tags=["contracts"])
    def protein_inference_harmonization_contract_schema(
        name: M0306ContractName,
    ) -> dict[str, object]:
        return _protein_inference_harmonization_contract_schema(name)

    @app.post(
        "/v1/modules/M03-06/harmonization",
        response_model=ProteinInferenceHarmonizationResult,
        tags=["M03-06"],
        openapi_extra=_protein_inference_harmonization_request_body(),
    )
    def harmonize_protein_inference_support(
        request: Annotated[
            HarmonizeProteinInferenceSupportRequest,
            Depends(_protein_inference_harmonization_body),
        ],
    ) -> ProteinInferenceHarmonizationResult:
        return protein_inference_harmonization_service.execute(request)

    @app.get("/v1/contracts/M03-07/{name}/schema", tags=["contracts"])
    def protein_inference_support_contract_schema(
        name: M0307ContractName,
    ) -> dict[str, object]:
        return _protein_inference_support_contract_schema(name)

    @app.post(
        "/v1/modules/M03-07/support-route",
        response_model=ProteinInferenceSupportRouteResult,
        tags=["M03-07"],
        openapi_extra=_protein_inference_support_request_body(),
    )
    def route_protein_inference_support(
        request: Annotated[
            RouteProteinInferenceSupportRequest,
            Depends(_protein_inference_support_body),
        ],
    ) -> ProteinInferenceSupportRouteResult:
        return protein_inference_support_service.execute(request)

    @app.post(
        "/v1/modules/M03-04/quality",
        response_model=ProteinInferenceQualityResult,
        tags=["M03-04"],
        openapi_extra=_protein_inference_quality_request_body(),
    )
    def compute_protein_inference_quality(
        request: Annotated[
            ComputeProteinInferenceQualityRequest,
            Depends(_protein_inference_quality_body),
        ],
    ) -> ProteinInferenceQualityResult:
        return protein_inference_quality_service.execute(request)

    @app.post(
        "/v1/modules/M03-02/identity-lineage-reconciliation",
        response_model=ProteinInferenceIdentityLineageResolution,
        tags=["M03-02"],
        openapi_extra=_protein_inference_lineage_request_body(),
    )
    def reconcile_protein_inference_identity_lineage(
        request: Annotated[
            ReconcileProteinInferenceIdentityLineageRequest,
            Depends(_protein_inference_lineage_body),
        ],
    ) -> ProteinInferenceIdentityLineageResolution:
        return protein_inference_lineage_service.execute(request)

    @app.post(
        "/v1/modules/M03-01/protocol-conformance",
        response_model=ProteinInferenceProtocolConformanceResult,
        tags=["M03-01"],
        openapi_extra=_protein_inference_protocol_request_body(),
    )
    def evaluate_protein_inference_protocol_conformance(
        request: Annotated[
            EvaluateProteinInferenceProtocolRequest,
            Depends(_protein_inference_protocol_body),
        ],
    ) -> ProteinInferenceProtocolConformanceResult:
        return protein_inference_protocol_service.execute(request)

    @app.post(
        "/v1/modules/M02-07/support-route",
        response_model=IdentificationSupportRouteResult,
        tags=["M02-07"],
        openapi_extra=_identification_support_request_body(),
    )
    def route_identification_support(
        request: Annotated[
            RouteIdentificationSupportRequest,
            Depends(_identification_support_body),
        ],
    ) -> IdentificationSupportRouteResult:
        return identification_support_service.execute(request)

    @app.post(
        "/v1/modules/M02-06/harmonization",
        response_model=IdentificationHarmonizationResult,
        tags=["M02-06"],
        openapi_extra=_identification_harmonization_request_body(),
    )
    def harmonize_identification_evidence(
        request: Annotated[
            HarmonizeIdentificationEvidenceRequest,
            Depends(_identification_harmonization_body),
        ],
    ) -> IdentificationHarmonizationResult:
        return identification_harmonization_service.execute(request)

    @app.post(
        "/v1/modules/M02-05/artifacts",
        response_model=IdentificationArtifactDetectionResult,
        tags=["M02-05"],
        openapi_extra=_identification_artifact_request_body(),
    )
    def detect_identification_artifacts(
        request: Annotated[
            DetectIdentificationArtifactsRequest,
            Depends(_identification_artifact_body),
        ],
    ) -> IdentificationArtifactDetectionResult:
        return identification_artifact_service.execute(request)

    @app.post(
        "/v1/modules/M02-04/quality",
        response_model=IdentificationQualityProfile,
        tags=["M02-04"],
        openapi_extra=_identification_quality_request_body(),
    )
    def compute_identification_quality(
        request: Annotated[
            ComputeIdentificationQualityRequest,
            Depends(_identification_quality_body),
        ],
    ) -> IdentificationQualityProfile:
        return identification_quality_service.execute(request)

    @app.post(
        "/v1/modules/M02-02/audit-bindings",
        response_model=IdentityBindingEvaluation,
        tags=["M02-02"],
        openapi_extra=_identity_binding_request_body(),
    )
    def audit_identification_bindings(
        request: Annotated[ValidateIdentityBindingsRequest, Depends(_identity_binding_body)],
    ) -> IdentityBindingEvaluation:
        return identity_binding_evaluator.evaluate(request)

    @app.post(
        "/v1/modules/M01-07/route",
        response_model=SupportRoutingResult,
        tags=["M01-07"],
        openapi_extra=_support_routing_request_body(),
    )
    def route_support(
        request: Annotated[RouteSupportRequest, Depends(_support_routing_body)],
    ) -> SupportRoutingResult:
        return support_routing_service.execute(request)

    @app.post(
        "/v1/modules/M01-06/harmonize",
        response_model=HarmonizationResult,
        tags=["M01-06"],
        openapi_extra=_harmonization_request_body(),
    )
    def harmonize_observations(
        request: Annotated[HarmonizeObservationsRequest, Depends(_harmonization_body)],
    ) -> HarmonizationResult:
        return harmonization_service.execute(request)

    @app.post(
        "/v1/modules/M01-05/detect",
        response_model=ArtifactDetectionResult,
        tags=["M01-05"],
        openapi_extra=_artifact_request_body(),
    )
    def detect_artifacts(
        request: Annotated[DetectArtifactsRequest, Depends(_artifact_body)],
    ) -> ArtifactDetectionResult:
        return artifact_service.execute(request)

    @app.post(
        "/v1/modules/M01-04/quality",
        response_model=QualityProfile,
        tags=["M01-04"],
        openapi_extra=_quality_request_body(),
    )
    def compute_quality_metrics(
        request: Annotated[ComputeQualityMetricsRequest, Depends(_quality_body)],
    ) -> QualityProfile:
        return quality_service.execute(request)

    @app.post(
        "/v1/modules/M01-03/inspect",
        response_model=ValidatedRawInputDescriptor,
        tags=["M01-03"],
    )
    async def inspect_raw_input(
        request: Request,
        source_id: str,
        filename: str | None = None,
        expected_sha256: str | None = None,
    ) -> ValidatedRawInputDescriptor:
        """Inspect one bounded binary body without retaining or interpreting its records."""

        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type != "application/octet-stream":
            raise HTTPException(
                status_code=415,
                detail="content-type must be application/octet-stream",
            )
        if filename is not None and len(filename.encode("utf-8")) > _MAX_ADVISORY_FILENAME_BYTES:
            raise HTTPException(status_code=422, detail="filename is too long")
        if expected_sha256 is not None and len(expected_sha256) > _MAX_CHECKSUM_TEXT_LENGTH:
            raise HTTPException(status_code=422, detail="checksum is too long")
        try:
            validated_source_id = _IDENTIFIER_ADAPTER.validate_python(source_id, strict=True)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="source identifier is invalid") from error
        return parse_raw_input(
            await request.body(),
            source_id=validated_source_id,
            filename=filename,
            expected_sha256=expected_sha256,
            limits=_RAW_API_LIMITS,
        )

    @app.post(
        "/v1/modules/M01-01/protocols",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
        openapi_extra=_request_body("register-request"),
    )
    def register_protocol(
        request: Annotated[RegisterProtocolRequest, Depends(_register_body)],
    ) -> ProtocolSchemaReceipt:
        return service.register(request)

    @app.post(
        "/v1/modules/M01-01/conformance",
        response_model=ConformanceProfile,
        tags=["M01-01"],
        openapi_extra=_request_body("evaluate-request"),
    )
    def evaluate_metadata(
        request: Annotated[EvaluateMetadataRequest, Depends(_evaluate_body)],
    ) -> ConformanceProfile:
        return service.evaluate(request)

    @app.get(
        "/v1/modules/M01-01/protocols/{schema_id}/{version}",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
    )
    def get_protocol(
        schema_id: str,
        version: str,
    ) -> ProtocolSchemaReceipt:
        return service.get_protocol(schema_id, version)

    @app.get(
        "/v1/modules/M01-01/events/verify",
        response_model=ChainVerification,
        tags=["operations"],
    )
    def verify_events() -> ChainVerification:
        return _require_valid_chain(service.verify_event_chain())

    @app.post(
        "/v1/modules/M01-02/reconcile",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
        openapi_extra=_identity_request_body(),
    )
    def reconcile_identity_lineage(
        request: Annotated[ReconcileIdentityLineageRequest, Depends(_reconcile_body)],
    ) -> IdentityLineageResolution:
        return identity_service.execute(request)

    @app.get(
        "/v1/modules/M01-02/resolutions/{resolution_digest}",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
    )
    def get_identity_resolution(
        resolution_digest: str,
    ) -> IdentityLineageResolution:
        try:
            validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
                resolution_digest,
                strict=True,
            )
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail="resolution digest is invalid",
            ) from error
        return identity_service.get_resolution(validated_digest)

    @app.get(
        "/v1/modules/M01-02/events/verify",
        response_model=M0102ChainVerification,
        tags=["operations"],
    )
    def verify_identity_events() -> M0102ChainVerification:
        return _require_valid_identity_chain(identity_service.verify_event_chain())

    return app


def _require_valid_chain(verification: ChainVerification) -> ChainVerification:
    if not verification.valid:
        raise ChainIntegrityError(verification.reason or "event chain verification failed")
    return verification


def _require_valid_identity_chain(
    verification: M0102ChainVerification,
) -> M0102ChainVerification:
    if not verification.valid:
        raise M0102ChainIntegrityError(
            verification.reason or "identity event chain verification failed"
        )
    return verification
