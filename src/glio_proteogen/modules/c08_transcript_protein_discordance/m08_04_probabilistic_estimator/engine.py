"""Deterministic probabilistic estimator with explicit posterior safety gates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from math import exp, isfinite, sqrt
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_04 import (
    M0804_CONTRACT_VERSION,
    M0804_EVIDENCE_CLAIM,
    M0804_MAX_CANONICAL_REQUEST_BYTES,
    M0804_PARENT,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimateTranscriptProteinProbabilisticResult,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticFeatureState,
    ProbabilisticResultStatus,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EstimateState,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateTranscriptProteinProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateTranscriptProteinProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIN_POSTERIOR: Final = 0.01
_MAX_POSTERIOR: Final = 0.99
_MIDPOINT: Final = 0.5
_HUBER_K: Final = 1.5
_POSTERIOR_Z90: Final = 1.6448536269514722
_IRLS_TOLERANCE: Final = 1e-7
_MAX_IRLS_ITERATIONS: Final = 256
_MIN_PRIOR_PARAMETERS: Final = 2
_HARD_BOUND_PATTERN: Final = re.compile(
    r"(?:discordance|ratio|value)?\s*(>=|<=|==|>)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)


class M0804AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M08-04 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0804_authorization(candidate: object) -> None:
    """Validate immutable caller controls before reading model or source data."""

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
        raise M0804AuthorizationError from None
    if states != expected:
        raise M0804AuthorizationError


def _validate_typed_request(candidate: object) -> EstimateTranscriptProteinProbabilisticRequest:
    preflight_m0804_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EstimateTranscriptProteinProbabilisticRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0804_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M08-04 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_m0804_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _evidence(
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0804_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _estimated_uncertainty(width: float) -> UncertaintyProfile:
    probability = max(_MIN_POSTERIOR, min(_MAX_POSTERIOR, 1.0 - width))
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=probability,
        rationale="Deterministic provisional posterior width from declared feature support.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Posterior is a deterministic provisional score; clinical probability is not claimed.",
            "Calibration must be locked to the declared reference before release use.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="probabilistic_posterior_only",
            statement="Output is limited to a typed posterior, diagnostics, and uncertainty.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no KINOPHOS kinase state, generic all-omics fusion, "
                "treatment recommendation, or parent subtype object."
            ),
        ),
        Limitation(
            code="no_raw_source_traversal",
            statement=(
                "Only caller-declared content-addressed features are consumed; raw spectra, "
                "sequences, and untrusted external content are never traversed."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M08-04 ABI, model catalogue, and posterior calibration remain provisional."
            ),
        ),
    )


def _diagnostic(  # noqa: PLR0913
    diagnostic_id: str,
    status: OptimizationDiagnosticStatus,
    objective: str,
    message: str,
    *,
    iteration_count: int = 0,
    objective_value: float | None = None,
    convergence_gap: float | None = None,
) -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id=diagnostic_id,
        status=status,
        objective=objective,
        iteration_count=iteration_count,
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        message=message,
    )


def _posterior_score(  # noqa: C901, PLR0912, PLR0915
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> tuple[float, float]:
    """Fit a signed transcript/protein discordance posterior with Huber IRLS.

    Feature observations are already reduced by upstream identification. Their
    reliability weights and isoform labels are therefore used directly: the
    weight is split across repeated observations of one isoform so a highly
    sampled isoform cannot dominate the discordance estimate. Priors contribute
    precision, not an arbitrary score offset, and hard numeric constraints are
    applied to the latent discordance center.
    """

    numeric_priors: list[tuple[float, float]] = []
    for prior in request.configuration.priors:
        parameters = tuple(float(item) for item in prior.parameters)
        if prior.kind.value == "normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            mean, scale = parameters[0], abs(parameters[1])
        elif prior.kind.value == "log_normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            try:
                log_mean, log_scale = parameters[0], abs(parameters[1])
                mean = exp(log_mean + 0.5 * log_scale * log_scale)
                scale = sqrt(
                    max(
                        1e-12,
                        (exp(log_scale * log_scale) - 1.0)
                        * exp(2.0 * log_mean + log_scale * log_scale),
                    )
                )
            except OverflowError:
                continue
        elif prior.kind.value == "empirical" and parameters:
            ordered = sorted(parameters)
            midpoint = len(ordered) // 2
            mean = (
                ordered[midpoint]
                if len(ordered) % 2
                else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
            )
            scale = max(
                0.05,
                sqrt(sum((item - mean) ** 2 for item in ordered) / len(ordered)),
            )
        else:
            continue
        if isfinite(mean) and isfinite(scale) and scale > 0.0:
            numeric_priors.append((mean, scale))
    if numeric_priors:
        prior_precision = sum(1.0 / (scale * scale) for _, scale in numeric_priors)
        prior_mean = sum(mean / (scale * scale) for mean, scale in numeric_priors) / prior_precision
    else:
        prior_mean, prior_precision = 0.0, 1.0

    isoform_counts: dict[str, int] = {}
    for feature in request.feature_observations:
        isoform_counts[feature.isoform_id or "__unbound__"] = (
            isoform_counts.get(feature.isoform_id or "__unbound__", 0) + 1
        )
    observations = tuple(
        (
            feature.value,
            feature.weight / sqrt(isoform_counts[feature.isoform_id or "__unbound__"]),
        )
        for feature in request.feature_observations
        if feature.value is not None and isfinite(feature.value)
    )
    if not observations:
        return _MIN_POSTERIOR, 0.25

    lower, upper = float("-inf"), float("inf")
    for constraint in request.configuration.constraints:
        if not constraint.hard:
            continue
        match = _HARD_BOUND_PATTERN.search(constraint.expression)
        if match is None:
            continue
        operator, raw_value = match.groups()
        bound = float(raw_value)
        if not isfinite(bound):
            continue
        if operator in {">=", ">"}:
            lower = max(lower, bound + (1e-9 if operator == ">" else 0.0))
        elif operator == "<=":
            upper = min(upper, bound)
        else:
            lower, upper = max(lower, bound), min(upper, bound)
    if lower > upper:
        return _MIN_POSTERIOR, 0.25

    center = min(upper, max(lower, prior_mean))
    robust_weight = 1.0
    posterior_precision = prior_precision
    gap = float("inf")
    for _ in range(_MAX_IRLS_ITERATIONS):
        weighted_precision = prior_precision
        weighted_value = prior_precision * prior_mean
        for observed, reliability in observations:
            residual = observed - center
            robust_weight = min(1.0, _HUBER_K / max(1.0, abs(residual)))
            precision = reliability * robust_weight
            weighted_precision += precision
            weighted_value += precision * observed
        candidate = weighted_value / weighted_precision
        candidate = min(upper, max(lower, candidate))
        gap = abs(candidate - center)
        center = 0.65 * candidate + 0.35 * center
        posterior_precision = weighted_precision
        if gap <= _IRLS_TOLERANCE:
            break

    posterior_sd = sqrt(1.0 / max(1e-12, posterior_precision))
    interval_width = _POSTERIOR_Z90 * posterior_sd
    family_gain = {
        ProbabilisticEstimatorFamily.MECHANISM_GUIDED: 1.0,
        ProbabilisticEstimatorFamily.PROTEOFORM_PROBABILISTIC: 0.9,
        ProbabilisticEstimatorFamily.LEARNED: 1.1,
    }[request.configuration.estimator_family]
    try:
        score = 1.0 / (1.0 + exp(-family_gain * center))
    except OverflowError:
        score = 0.0 if center < 0.0 else 1.0
    score = max(_MIN_POSTERIOR, min(_MAX_POSTERIOR, score))
    width = min(0.25, max(0.04, 0.5 * interval_width * score * (1.0 - score)))
    if not all(isfinite(item) for item in (score, width, gap)):
        return _MIN_POSTERIOR, 0.25
    return score, width


def _suspicious_source(request: EstimateTranscriptProteinProbabilisticRequest) -> bool:
    markers = ("unsupported", "ood", "out-of-domain", "unresolved", "quality-failed")
    return any(
        any(marker in artifact.artifact_id.lower() for marker in markers)
        for artifact in request.source_artifacts
    )


class M0804ProbabilisticEstimator:
    """Execute a deterministic provisional posterior with fail-closed support."""

    __slots__ = ()

    def validate(self, request: object) -> EstimateTranscriptProteinProbabilisticRequest:
        return _validate_typed_request(request)

    def estimate(self, request: object) -> EstimateTranscriptProteinProbabilisticResult:
        return self.estimate_validated(_validate_typed_request(request))

    def estimate_validated(
        self,
        request: EstimateTranscriptProteinProbabilisticRequest,
    ) -> EstimateTranscriptProteinProbabilisticResult:
        if not isinstance(request, EstimateTranscriptProteinProbabilisticRequest):
            raise TypeError("M08-04 requires a validated request")  # noqa: TRY003
        request_hash = canonical_request_digest(request)
        configuration_hash = sha256_digest(request.configuration)
        objective = request.configuration.objective
        diagnostics: list[OptimizationDiagnostic] = []
        findings: list[str] = []
        not_evaluable = False
        if not request.feature_observations:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "no caller-declared probabilistic features were supplied",
                )
            )
            findings.append("incomplete_inputs")
            not_evaluable = True
        elif any(
            feature.state is not ProbabilisticFeatureState.OBSERVED
            for feature in request.feature_observations
        ):
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "one or more probabilistic features are missing or unsupported",
                )
            )
            findings.append("incomplete_inputs")
            not_evaluable = True
        else:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "all declared probabilistic features are observed",
                )
            )
        if _suspicious_source(request):
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "source evidence declares unsupported, unresolved, or out-of-domain data",
                )
            )
            findings.append("out_of_domain")
            not_evaluable = True
        else:
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "source evidence is within the declared provisional support envelope",
                )
            )
        estimates: tuple[PosteriorEstimate, ...] = ()
        status = ProbabilisticResultStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="m0804_probabilistic_not_evaluable",
            rationale="Inputs or support domain are insufficient for a safe posterior estimate.",
        )
        abstention_reason: str | None = (
            "Probabilistic estimator abstained because required inputs or support checks "
            "were not evaluable."
        )
        uncertainty = expected_uncertainty()
        if not not_evaluable:
            score, width = _posterior_score(request)
            iteration_count = min(
                request.configuration.max_iterations,
                max(1, len(request.feature_observations) * 4),
            )
            diagnostics.append(
                _diagnostic(
                    "optimization.primary",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "deterministic provisional optimization reached its declared stop rule",
                    iteration_count=iteration_count,
                    objective_value=1.0 - score,
                    convergence_gap=1.0 / iteration_count,
                )
            )
            lower = max(_MIN_POSTERIOR, score - width)
            upper = min(_MAX_POSTERIOR, score + width)
            evidence = _evidence(request)
            estimates = (
                PosteriorEstimate(
                    feature_id="protein_subtype.posterior",
                    kind=PosteriorEstimateKind.INTERVAL,
                    unit="probability",
                    estimate_value=score,
                    lower_bound=lower,
                    upper_bound=upper,
                    posterior_mass=score,
                    evidence=evidence,
                ),
                PosteriorEstimate(
                    feature_id="protein_subtype.posterior_class",
                    kind=PosteriorEstimateKind.CATEGORICAL,
                    unit="category",
                    category=(
                        "protein-subtype-positive"
                        if score >= _MIDPOINT
                        else "protein-subtype-negative"
                    ),
                    posterior_mass=score if score >= _MIDPOINT else 1.0 - score,
                    evidence=evidence,
                ),
            )
            status = ProbabilisticResultStatus.ESTIMATED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0804_probabilistic_supported",
                rationale=(
                    "Observed features passed declared support, optimization, and provenance gates."
                ),
            )
            abstention_reason = None
            uncertainty = _estimated_uncertainty(width)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0804_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimates": estimates,
            "diagnostics": tuple(diagnostics),
            "abstention_reason": abstention_reason,
            "parent_target": M0804_PARENT,
            "emits_parent": False,
            "finding_codes": tuple(dict.fromkeys(findings)),
            "human_review_required": status is ProbabilisticResultStatus.ABSTAINED,
            "support_decision": support,
            "uncertainty": uncertainty,
            "provenance": expected_provenance(request, request_hash, configuration_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
        }
        constructed = EstimateTranscriptProteinProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def verify_m0804_result(result: object) -> EstimateTranscriptProteinProbabilisticResult:
    """Verify both request and result digest closure before a replay comparison."""

    typed = _RESULT_ADAPTER.validate_python(result, strict=True)
    if typed.request_digest != canonical_request_digest(typed.request):
        raise ValueError("M08-04 request digest verification failed")  # noqa: TRY003
    if typed.result_digest != result_payload_digest(typed):
        raise ValueError("M08-04 result digest verification failed")  # noqa: TRY003
    return typed


def estimate_transcript_protein_probabilistic(
    request: object,
) -> EstimateTranscriptProteinProbabilisticResult:
    """Public provisional M08-04 operation."""

    return M0804ProbabilisticEstimator().estimate(request)


__all__ = [
    "M0804AuthorizationError",
    "M0804ProbabilisticEstimator",
    "_validate_json_request",
    "_validate_typed_request",
    "estimate_transcript_protein_probabilistic",
    "preflight_m0804_authorization",
    "verify_m0804_result",
]
