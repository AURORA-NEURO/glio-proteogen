"""Stateless application boundary for M02-08 identification releases."""

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_08 import (
    BuildIdentificationQcReleaseRequest,
    IdentificationQcReproducibilityManifest,
    IdentificationReleaseVerification,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging.engine import (
    BuiltIdentificationRelease,
    IdentificationSignatureVerifier,
    M0208IdentificationReleaseEngine,
    preflight_identification_release_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(BuildIdentificationQcReleaseRequest)


class M0208Service:
    """Authorize, validate, package, and inspect without owning signing keys."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        verifier: IdentificationSignatureVerifier | None = None,
        engine: M0208IdentificationReleaseEngine | None = None,
    ) -> None:
        self._engine = engine or M0208IdentificationReleaseEngine(verifier)

    @staticmethod
    def validate_request(request: object) -> BuildIdentificationQcReleaseRequest:
        preflight_identification_release_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltIdentificationRelease:
        return self._engine.build(request, artifacts_by_path, stage_results_by_module)

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> IdentificationQcReproducibilityManifest:
        return self._engine.build_manifest(
            request,
            artifacts_by_path,
            stage_results_by_module,
        )

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> IdentificationReleaseVerification:
        return self._engine.verify(result, package_bytes)


__all__ = ["M0208Service"]
