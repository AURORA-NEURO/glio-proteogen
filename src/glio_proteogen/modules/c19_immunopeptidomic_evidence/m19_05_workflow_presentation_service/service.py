"""Service seam for strict M19-05 presentation and replay verification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_05 import (
    M1905_MAX_CANONICAL_REQUEST_BYTES,
    M1905_MAX_CANONICAL_RESULT_BYTES,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ProteotypeHumanReviewWorkspaceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1905Engine, M1905ReplayError

_REQUEST_ADAPTER: Final = TypeAdapter(PresentProteotypeHumanReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeHumanReviewWorkspaceResult)


class M1905Service:
    """Parse once, present deterministically and verify canonical replay."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1905Engine()

    def validate_request(self, request: object) -> PresentProteotypeHumanReviewWorkspaceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(
                request,
                max_bytes=M1905_MAX_CANONICAL_REQUEST_BYTES,
            )
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteotypeHumanReviewWorkspaceResult:
        return self._engine.present(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeHumanReviewWorkspaceResult:
        try:
            if isinstance(result, (bytes, bytearray, str)):
                decoded = strict_json_loads(
                    result,
                    max_bytes=M1905_MAX_CANONICAL_RESULT_BYTES,
                )
                validated = _RESULT_ADAPTER.validate_json(
                    canonical_json_bytes(decoded), strict=True
                )
            elif isinstance(result, Mapping):
                validated = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result), strict=True)
            else:
                validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1905ReplayError from error
        return self._engine.verify(validated, replay=replay)

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M19-05",
            title="workflow presentation service (provisional)",
            version="0.1.0-provisional",
            owner="Data engineering",
            safety_class="S2",
            gate="G4",
            prohibited_outputs=(
                "kinase activity, generic all-omics fusion, direct treatment recommendation",
                "identity/consent inference or unsupported-to-negative conversion",
                "upstream mutation, relabeling or disagreement erasure",
            ),
        )


__all__ = ["M1905Service"]
