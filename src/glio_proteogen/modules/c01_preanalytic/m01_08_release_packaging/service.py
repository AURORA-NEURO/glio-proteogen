"""Thin stateless service for M01-08 release packaging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_08 import BuildReleasePackageRequest
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging.engine import (
    BuiltReleasePackage,
    M0108ReleasePackager,
    preflight_release_packaging_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_ADAPTER: Final[TypeAdapter[BuildReleasePackageRequest]] = TypeAdapter(
    BuildReleasePackageRequest
)


class M0108Service:
    __slots__ = ("_packager",)

    def __init__(self, packager: M0108ReleasePackager | None = None) -> None:
        self._packager = packager or M0108ReleasePackager()

    @staticmethod
    def validate_request(request: object) -> BuildReleasePackageRequest:
        preflight_release_packaging_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object, files: Mapping[str, bytes]) -> BuiltReleasePackage:
        return self._packager.build(self.validate_request(request), files)


__all__ = ["M0108Service"]
