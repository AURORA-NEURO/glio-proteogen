"""Strict service seam for M27-04 publication and replay."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_04 import (
    M2704_MAX_CANONICAL_REQUEST_BYTES,
    M2704_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityAccessSurfaceResult,
    PublishComplexActivityAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2704GatewayEngine, preflight_m2704_authorization

_REQUEST_ADAPTER = TypeAdapter(PublishComplexActivityAccessSurfaceRequest)


class M2704Service:
    """Validate, publish, and replay through one deterministic gateway engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2704GatewayEngine | None = None) -> None:
        self._engine = engine or M2704GatewayEngine()

    def validate_request(self, request: object) -> PublishComplexActivityAccessSurfaceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2704_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2704_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2704_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def publish(self, request: object) -> ComplexActivityAccessSurfaceResult:
        if type(request) is PublishComplexActivityAccessSurfaceRequest:
            preflight_m2704_authorization(request)
            return self._engine._publish_validated(request)
        return self._engine._publish_validated(self.validate_request(request))

    def replay(self, result: object) -> ComplexActivityAccessSurfaceResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2704_MAX_CANONICAL_RESULT_BYTES)
            typed = ComplexActivityAccessSurfaceResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif isinstance(result, Mapping):
            typed = ComplexActivityAccessSurfaceResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            typed = ComplexActivityAccessSurfaceResult.model_validate(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M27-04",
            "operation": "publish_complex_activity_access_surface",
            "owner": "Clinical science",
            "safety_class": "S3",
            "gate": "G2",
            "parent": "complex activity",
            "provisional_abi": True,
            "typed_operations": True,
            "authorization": True,
            "idempotency": True,
            "asynchronous_jobs": True,
            "compatibility": True,
            "signed_release_bundle_fallback": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "complex activity claim",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2704Service"]
