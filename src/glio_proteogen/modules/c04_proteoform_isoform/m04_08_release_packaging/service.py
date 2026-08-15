"""Stateless application boundary for M04-08 proteoform releases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_08 import (
    BuildProteoformReleaseRequest,
    ProteoformReleaseVerification,
    ProteoformReproducibilityManifest,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    M0408ProteoformReleaseEngine,
    preflight_proteoform_release_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
        BuiltProteoformRelease,
        ProteoformSignatureVerifier,
    )

_REQUEST_ADAPTER = TypeAdapter(BuildProteoformReleaseRequest)


class M0408Service:
    """Authorize, validate, package, and inspect without owning signing keys."""

    __slots__ = ("_engine",)

    def __init__(self, verifier: ProteoformSignatureVerifier | None = None) -> None:
        self._engine = M0408ProteoformReleaseEngine(verifier)

    @staticmethod
    def validate_request(request: object) -> BuildProteoformReleaseRequest:
        preflight_proteoform_release_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteoformRelease:
        return self._engine.build(request, artifacts_by_path, stage_results_by_module)

    execute = build

    def manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteoformReproducibilityManifest:
        return self._engine.build_manifest(request, artifacts_by_path, stage_results_by_module)

    build_manifest = manifest

    def verify(self, result: object, package_bytes: bytes) -> ProteoformReleaseVerification:
        return self._engine.verify(result, package_bytes)


__all__ = ["M0408Service"]
