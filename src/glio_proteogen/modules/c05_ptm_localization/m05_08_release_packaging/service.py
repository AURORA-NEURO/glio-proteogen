"""Stateless application boundary for M05-08 release packaging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.engine import (
    BuiltPtmLocalizationRelease,
    M0508PtmLocalizationReleaseEngine,
    PtmLocalizationSignatureVerifier,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.contracts.m05_08 import (
        BuildPtmLocalizationReleaseRequest,
        PtmLocalizationReleaseManifest,
        PtmLocalizationReleaseVerification,
    )


class M0508Service:
    """Authorize, validate, build and inspect without persisting caller data."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        verifier: PtmLocalizationSignatureVerifier | None = None,
        engine: M0508PtmLocalizationReleaseEngine | None = None,
    ) -> None:
        self._engine = engine or M0508PtmLocalizationReleaseEngine(verifier)

    @staticmethod
    def validate_request(request: object) -> BuildPtmLocalizationReleaseRequest:
        return M0508PtmLocalizationReleaseEngine.validate_request(request)

    def manifest(self, request: object) -> PtmLocalizationReleaseManifest:
        return self._engine.manifest(request)

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, bytes],
    ) -> BuiltPtmLocalizationRelease:
        return self._engine.build(request, artifacts_by_path)

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> PtmLocalizationReleaseVerification:
        return self._engine.verify(result, package_bytes)

    def execute(
        self,
        request: object,
        artifacts_by_path: Mapping[str, bytes] | None = None,
    ) -> BuiltPtmLocalizationRelease:
        return self._engine.execute(request, artifacts_by_path)


__all__ = ["M0508Service"]
