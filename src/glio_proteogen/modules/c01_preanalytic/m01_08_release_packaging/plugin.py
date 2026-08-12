"""Strict validate-then-run plugin boundary for M01-08."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_08 import BuildReleasePackageRequest
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging.engine import (
    BuiltReleasePackage,
    preflight_release_packaging_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging.service import (
        M0108Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[BuildReleasePackageRequest]] = TypeAdapter(
    BuildReleasePackageRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-08",
    title="Provenance and release packaging",
    version="1.0.0",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "self-generated signature or key",
        "scientific-result validation",
        "signature-authority or supply-chain qualification",
        "proteotype, kinase-state, or treatment inference",
    ),
)


@dataclass(frozen=True, slots=True)
class ReleasePackagingSubmission:
    request: object
    files: Mapping[str, bytes]


@dataclass(frozen=True, slots=True)
class ValidatedM0108Request:
    request: BuildReleasePackageRequest
    files: Mapping[str, bytes]


class M0108Plugin(ModulePlugin[object, ValidatedM0108Request, BuiltReleasePackage]):
    __slots__ = ("_service",)

    def __init__(self, service: M0108Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0108Request:
        if not isinstance(submission, ReleasePackagingSubmission):
            raise TypeError
        candidate = submission.request
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            decoded = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            preflight_release_packaging_authorization(decoded)
            request = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        else:
            request = self._service.validate_request(candidate)
        if not isinstance(submission.files, Mapping):
            raise TypeError
        files = dict(submission.files)
        return ValidatedM0108Request(request=request, files=files)

    def run(self, request: ValidatedM0108Request) -> BuiltReleasePackage:
        if not isinstance(request, ValidatedM0108Request):
            raise TypeError
        return self._service.execute(request.request, request.files)


__all__ = [
    "M0108Plugin",
    "ReleasePackagingSubmission",
    "ValidatedM0108Request",
]
