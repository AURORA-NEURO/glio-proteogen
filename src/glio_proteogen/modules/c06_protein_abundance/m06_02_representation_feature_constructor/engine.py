"""Provisional M06-02 leakage-safe representation constructor boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_02 import BuildProteinRepresentationRequest
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteinRepresentationRequest)


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized representation request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M06-02 representation request is not authorized")


class RepresentationInputError(ValueError):
    """Raised for a structurally valid request outside the provisional envelope."""


def preflight_representation_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates when typed."""

    if not isinstance(request, BuildProteinRepresentationRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise RepresentationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise RepresentationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise RepresentationAuthorizationError


class M0602RepresentationEngine:
    """Import-safe constructor seam; learned/mechanistic execution is not frozen."""

    @staticmethod
    def validate_request(request: object) -> BuildProteinRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> None:
        self.validate_request(request)
        raise NotImplementedError(
            "M06-02 representation construction awaits ABI and feature-catalogue freeze"
        )


def construct_protein_representation(request: object) -> None:
    """Reserve the provisional public operation without claiming implementation."""

    return M0602RepresentationEngine().construct(request)


__all__ = [
    "M0602RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_protein_representation",
    "preflight_representation_authorization",
]
