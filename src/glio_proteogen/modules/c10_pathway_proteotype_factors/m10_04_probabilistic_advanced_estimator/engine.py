"""Deterministic, fail-closed provisional M10-04 estimator runtime."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite, sqrt
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_04 import (
    M1004_CONTRACT_VERSION,
    M1004_EVIDENCE_CLAIM,
    M1004_MAX_EVIDENCE,
    M1004_PARENT,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticObservation,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    ProbabilisticResultStatus,
    ProteinRnaDiscordanceProbabilisticResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinRnaDiscordanceProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_NORMAL_PARAMETER_COUNT: Final = 2
_HUBER_K: Final = 1.5
_CONVERGENCE_TOLERANCE: Final = 1e-9


class M1004ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for estimation."""

    def __init__(self) -> None:
        super().__init__(
            "M10-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1004ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-04 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_probabilistic_estimator_authorization(candidate: object) -> None:
    """Check seven control decisions before strict model validation."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M1004ProbabilisticEstimatorAuthorizationError from None
    if states != expected:
        raise M1004ProbabilisticEstimatorAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_probabilistic_estimator_authorization(candidate)
    return candidate


def _evidence(
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.baseline_result,
        request.configuration.reference,
        *request.source_artifacts,
        *(item.reference for observation in request.observations for item in observation.evidence),
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1004_EVIDENCE_CLAIM)
        for artifact in artifacts[:M1004_MAX_EVIDENCE]
    )


def _diagnostic() -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.not-evaluable",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective="owner-locked probabilistic objective pending",
        iteration_count=0,
        message=(
            "The provisional lane cannot claim optimization convergence until training, "
            "baseline comparison, and calibration artifacts are owner-locked."
        ),
    )


def _measured_diagnostic(
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    *,
    objective_value: float,
    iteration_count: int,
    convergence_gap: float,
) -> OptimizationDiagnostic:
    """Describe the deterministic robust posterior fit for measured observations."""

    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.robust-normal-irls",
        status=OptimizationDiagnosticStatus.CONVERGED,
        objective=request.configuration.objective,
        iteration_count=iteration_count,
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        message=(
            "Measured observations were fit with a robust Normal conjugate posterior using "
            "Huber IRLS, deterministic damping, and the locked configuration seed."
        ),
        evidence=_evidence(request),
    )


def _normal_prior(prior: ProbabilisticPrior) -> tuple[float, float] | None:
    """Return a finite (mean, standard deviation) Normal prior, if declared."""

    if (
        prior.kind is not ProbabilisticPriorKind.NORMAL
        or len(prior.parameters) < _NORMAL_PARAMETER_COUNT
    ):
        return None
    mean, standard_deviation = prior.parameters[:2]
    if not isfinite(mean) or not isfinite(standard_deviation) or standard_deviation <= 0:
        return None
    return mean, standard_deviation


def _fit_observation(
    observation: ProbabilisticObservation,
    prior: ProbabilisticPrior,
    *,
    max_iterations: int,
) -> tuple[PosteriorEstimate, float, int, float] | None:
    """Fit one measured value with a bounded Huber-IRLS Normal posterior.

    The prior is retained as an explicit regularizer.  Huber weights prevent a single
    low-quality outlier from dominating the protein/RNA discordance estimate while the
    posterior variance remains tied to the declared assay standard error.
    """

    prior_parameters = _normal_prior(prior)
    if prior_parameters is None:
        return None
    prior_mean, prior_sd = prior_parameters
    prior_precision = 1.0 / (prior_sd * prior_sd)
    observation_precision = observation.quality_weight / (
        observation.standard_error * observation.standard_error
    )
    if observation_precision <= 0:
        return None
    current = prior_mean
    damping = 0.7
    gap = float("inf")
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        standardized_residual = (observation.value - current) / observation.standard_error
        absolute_residual = abs(standardized_residual)
        huber_weight = (
            1.0 if absolute_residual <= _HUBER_K else _HUBER_K / absolute_residual
        )
        robust_precision = observation_precision * huber_weight
        target = (prior_precision * prior_mean + robust_precision * observation.value) / (
            prior_precision + robust_precision
        )
        updated = current + damping * (target - current)
        gap = abs(updated - current)
        current = updated
        if gap <= _CONVERGENCE_TOLERANCE:
            break
    robust_residual = (observation.value - current) / observation.standard_error
    absolute_residual = abs(robust_residual)
    huber_loss = (
        0.5 * robust_residual * robust_residual
        if absolute_residual <= _HUBER_K
        else _HUBER_K * absolute_residual - 0.5 * _HUBER_K * _HUBER_K
    )
    objective = 0.5 * ((current - prior_mean) / prior_sd) ** 2 + (
        observation.quality_weight * huber_loss
    )
    posterior_variance = 1.0 / (prior_precision + observation_precision)
    half_width = 1.96 * sqrt(posterior_variance)
    estimate = PosteriorEstimate(
        feature_id=observation.feature_id,
        kind=PosteriorEstimateKind.INTERVAL,
        unit="standardized-protein-rna-discordance",
        estimate_value=round(current, 8),
        lower_bound=round(current - half_width, 8),
        upper_bound=round(current + half_width, 8),
        posterior_mass=0.95,
        evidence=observation.evidence or prior.evidence,
    )
    return estimate, objective, iterations, gap


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m1004_estimation_review_required",
        rationale=(
            "Posterior estimation is abstained pending owner-locked objective, training, "
            "baseline comparison, and uncertainty calibration evidence."
        ),
    )


def _measured_support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="m1004_measured_posterior_supported",
        rationale=(
            "Every measured observation resolved to a finite Normal prior and contributed "
            "positive quality-weighted precision to the robust posterior."
        ),
    )


def _limitations(*, measured: bool = False) -> tuple[Limitation, ...]:
    if measured:
        return (
            Limitation(
                code="single_observation_sampling",
                statement=(
                    "Sampling uncertainty is not estimable from one observation per feature; "
                    "intervals reflect the declared assay error and Normal prior only."
                ),
            ),
            Limitation(
                code="prior_family_restriction",
                statement=(
                    "Measured fitting currently accepts finite Normal priors; other declared "
                    "prior families remain an explicit safe abstention."
                ),
            ),
            Limitation(
                code="no_parent_emission",
                statement=(
                    "This estimator emits no parent protein-RNA claim, kinase activity, "
                    "generic all-omics fusion, or treatment advice."
                ),
            ),
        )
    return (
        Limitation(
            code="posterior_not_published",
            statement="No posterior estimate is published until optimization gates are locked.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no parent protein-RNA discordance claim, kinase state, "
                "generic all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="opaque_inputs",
            statement="Inputs remain immutable artifact references and are not traversed.",
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "Estimator ABI, posterior representation, and baseline handoff are provisional."
            ),
        ),
    )


class M1004ProbabilisticEstimatorEngine:
    """Bind deterministic configuration and abstain until estimator gates are locked."""

    __slots__ = ()

    def estimate(self, request: object) -> ProteinRnaDiscordanceProbabilisticResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        request_hash = canonical_request_digest(request)
        estimates: list[PosteriorEstimate] = []
        objective_value = 0.0
        iteration_count = 0
        convergence_gap = 0.0
        if request.observations:
            priors = {prior.prior_id: prior for prior in request.configuration.priors}
            fits = [
                _fit_observation(
                    observation,
                    priors[observation.feature_id],
                    max_iterations=request.configuration.max_iterations,
                )
                for observation in request.observations
            ]
            if all(fit is not None for fit in fits):
                estimates = [fit[0] for fit in fits if fit is not None]
                objective_value = round(sum(fit[1] for fit in fits if fit is not None), 8)
                iteration_count = max(fit[2] for fit in fits if fit is not None)
                convergence_gap = round(max(fit[3] for fit in fits if fit is not None), 12)
        measured = bool(estimates)
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_posterior",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1004_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": (
                ProbabilisticResultStatus.ESTIMATED
                if measured
                else ProbabilisticResultStatus.ABSTAINED
            ),
            "estimates": tuple(estimates),
            "diagnostics": (
                _measured_diagnostic(
                    request,
                    objective_value=objective_value,
                    iteration_count=iteration_count,
                    convergence_gap=convergence_gap,
                )
                if measured
                else _diagnostic(),
            ),
            "abstention_reason": None
            if measured
            else (
                "Estimation is abstained until M10-03 baseline comparison, optimization, "
                "calibration, and transport gates are owner-locked, or finite measured "
                "observations resolve to compatible Normal priors."
            ),
            "parent_target": M1004_PARENT,
            "support_decision": _measured_support() if measured else _support(),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(measured=measured),
            "human_review_required": not measured,
        }
        constructed = ProteinRnaDiscordanceProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        """Verify receipt digests and optionally replay the exact request."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if not verify_result_digest(
            validated
        ):  # pragma: no cover - contract validator closes this path.
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if validated.request_digest != canonical_request_digest(
            validated.request
        ):  # pragma: no cover - contract validator closes this path.
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "request digest does not match embedded request"
            )
        if replay:
            expected = self.estimate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def estimate_protein_rna_discordance_probabilistic(
    request: object,
) -> ProteinRnaDiscordanceProbabilisticResult:
    """Public provisional M10-04 operation."""

    return M1004ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M1004ProbabilisticEstimatorAuthorizationError",
    "M1004ProbabilisticEstimatorEngine",
    "M1004ReplayVerificationError",
    "estimate_protein_rna_discordance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
