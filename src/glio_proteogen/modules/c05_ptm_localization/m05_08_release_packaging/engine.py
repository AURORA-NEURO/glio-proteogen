"""Provisional quarantine-first M05-08 release-packaging engine boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_08 import (
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseManifest,
    canonical_request_digest,
    manifest_digest,
)
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState, UpstreamDecisionState

_REQUEST_ADAPTER: Final = TypeAdapter(BuildPtmLocalizationReleaseRequest)


class PtmLocalizationReleaseAuthorizationError(PermissionError):
    """Raised before an unauthorized M05-08 request can traverse its inputs."""


class PtmLocalizationReleaseInputError(ValueError):
    """Raised for a request that is structurally valid but not releaseable."""


def preflight_ptm_localization_release_authorization(
    request: object,
) -> None:
    """Apply the shared control gate when a typed request is already available."""

    if not isinstance(request, BuildPtmLocalizationReleaseRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise PtmLocalizationReleaseAuthorizationError(
            "M05-08 requires caller-granted consent"
        )
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise PtmLocalizationReleaseAuthorizationError(
            "M05-08 requires caller-resolved identity lineage"
        )
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise PtmLocalizationReleaseAuthorizationError(
            "M05-08 requires accepted caller control decisions"
        )


class M0508PtmLocalizationReleaseEngine:
    """Import-safe scaffold; executable packaging awaits ABI freeze."""

    @staticmethod
    def validate_request(request: object) -> BuildPtmLocalizationReleaseRequest:
        preflight_ptm_localization_release_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    @staticmethod
    def manifest(request: object) -> PtmLocalizationReleaseManifest:
        typed = M0508PtmLocalizationReleaseEngine.validate_request(request)
        return typed.manifest

    @staticmethod
    def request_digest(request: object) -> str:
        return canonical_request_digest(
            M0508PtmLocalizationReleaseEngine.validate_request(request)
        )

    @staticmethod
    def manifest_digest(request: object) -> str:
        return manifest_digest(M0508PtmLocalizationReleaseEngine.manifest(request))

    def execute(self, request: object) -> None:
        """Reserve the runtime entry point without implying a frozen ABI."""

        self.validate_request(request)
        raise NotImplementedError(
            "M05-08 package assembly is provisional and awaits ABI/fixture/limit freeze"
        )


def build_ptm_localization_release_manifest(
    request: object,
) -> PtmLocalizationReleaseManifest:
    return M0508PtmLocalizationReleaseEngine.manifest(request)


__all__ = [
    "M0508PtmLocalizationReleaseEngine",
    "PtmLocalizationReleaseAuthorizationError",
    "PtmLocalizationReleaseInputError",
    "build_ptm_localization_release_manifest",
    "preflight_ptm_localization_release_authorization",
]
