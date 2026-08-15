"""Provisional M06-04 posterior-estimator boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_04 import EstimateProteinAbundanceProbabilisticRequest
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState, UpstreamDecisionState

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceProbabilisticRequest)


class ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Raised before an unauthorized posterior request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M06-04 probabilistic request is not authorized")


class ProbabilisticEstimatorInputError(ValueError):
    """Raised for a structurally valid request outside the provisional envelope."""


def preflight_probabilistic_estimator_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates when typed."""

    if not isinstance(request, EstimateProteinAbundanceProbabilisticRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ProbabilisticEstimatorAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ProbabilisticEstimatorAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise ProbabilisticEstimatorAuthorizationError


class M0604ProbabilisticEstimatorEngine:
    """Import-safe posterior seam; training/inference is not frozen yet."""

    @staticmethod
    def validate_request(request: object) -> EstimateProteinAbundanceProbabilisticRequest:
        preflight_probabilistic_estimator_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def estimate(self, request: object) -> None:
        self.validate_request(request)
        raise NotImplementedError(
            "M06-04 posterior estimation awaits ABI, metric, and model freeze"
        )


def estimate_protein_abundance_probabilistic(request: object) -> None:
    return M0604ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M0604ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "estimate_protein_abundance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
