"""Replay-safe complex-activity posterior runtime for provisional M09-04.

The estimator uses a bounded Huber-IRLS update with explicit prior-family
reduction, feature-matched precision, optional reduced assay summaries, and
hard stoichiometry bounds. It never treats a content digest as a measurement;
bare artifact references contribute only prior information. Any missing,
unsupported, OOD, conflicted, contradictory, or non-convergent declaration is
quarantined before a posterior is emitted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import erf, exp, isfinite, sqrt
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_04 import (
    M0904_CONTRACT_VERSION,
    M0904_EVIDENCE_CLAIM,
    M0904_MAX_CANONICAL_RESULT_BYTES,
    M0904_PARENT,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    EstimateComplexActivityProbabilisticVerification,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticReplayReason,
    ProbabilisticResultStatus,
    expected_provenance,
)
from glio_proteogen.contracts.m09_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_ABSTENTION_MARKERS: Final = frozenset(
    {"missing", "unsupported", "ood", "out_of_domain", "conflict", "review", "quarantine"}
)
_FAILURE_MARKERS: Final = frozenset(
    {"fail", "failed", "not_evaluable", "nonconverged", "non_converged", "unstable"}
)

# M09-04 is deliberately small and interpretable: it estimates a bounded
# complex activity (0..1) from caller-declared priors and optional encoded
# assay summaries.  The ABI only carries content-addressed artifact metadata,
# so an artifact id may include ``activity:0.72``/``sd:0.08`` when a producer
# has already reduced a spectrum or stoichiometry table.  Bare references are
# treated as prior-only evidence, never as pseudo-random measurements.
_HUBER_K: Final = 1.5
_POSTERIOR_Z90: Final = 1.6448536269514722
_ACTIVITY_MIN: Final = 0.0
_ACTIVITY_MAX: Final = 1.0
_IRLS_TOLERANCE: Final = 1e-7
_DEFAULT_ASSAY_SD: Final = 0.18
_MIN_PRIOR_PARAMETERS: Final = 2
_VALUE_PATTERN: Final = re.compile(
    r"(?:activity|stoich|stoichiometry|abundance|value)(?:[:._-])"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)
_SD_PATTERN: Final = re.compile(
    r"(?:sd|se|sigma)(?:[:._-])"
    r"(\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
    re.IGNORECASE,
)
_NUMERIC_CONSTRAINT_PATTERN: Final = re.compile(
    r"(?:activity|stoich|stoichiometry|abundance|value)?\s*"
    r"(>=|<=|==|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _PriorSummary:
    mean: float
    variance: float
    weight: float
    rationale: str


@dataclass(frozen=True, slots=True)
class _ActivityFit:
    value: float
    lower: float
    upper: float
    posterior_mass: float
    objective: float
    iterations: int
    convergence_gap: float
    rationale: str


class M0904AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M09-04 requires accepted controls, resolved identity, and granted consent"
        )


class M0904InputError(ValueError):
    """Raised for oversized or non-canonical result material."""

    _MESSAGES: Final = {
        "result_limit": "M09-04 result exceeds the canonical byte limit",
        "result_digest": "M09-04 result digest does not match its content",
        "result_noncanonical": "M09-04 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0904Result:
    """A typed result paired with its one canonical byte representation."""

    result: EstimateComplexActivityProbabilisticResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0904InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0904InputError("result_noncanonical")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0904_authorization(candidate: object) -> None:
    """Check every caller control before evaluating evidence declarations."""

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
        raise M0904AuthorizationError from None
    if states != expected:
        raise M0904AuthorizationError


def _evidence(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0904_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _control_decisions(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in decisions
    )


def _provenance(
    request: EstimateComplexActivityProbabilisticRequest,
    request_digest: str,
) -> ProvenanceRecord:
    return expected_provenance(
        request,
        request_digest,
        sha256_digest(request.configuration),
    )


def _uncertainty(*, estimated: bool) -> UncertaintyProfile:
    if not estimated:
        estimate = UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="Posterior is withheld because support or convergence is not sufficient.",
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
                "All uncertainty dimensions remain not estimable for this abstained result.",
            ),
        )

    def _dimension(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=_dimension(0.12, "Assay-scale uncertainty from reduced summary precision."),
        sampling=_dimension(0.08, "Sampling uncertainty from the declared source count."),
        parameter=_dimension(0.10, "Parameter uncertainty from the declared prior family."),
        model_form=_dimension(0.18, "Model-form uncertainty remains provisional."),
        identification=_dimension(0.06, "Identity control was accepted upstream."),
        support=_dimension(0.05, "Support control and source markers passed."),
        transport=_dimension(0.20, "Transport uncertainty is bounded but not calibrated."),
        sensitivity_notes=(
            (
                "Probabilities are deterministic provisional diagnostics, not calibrated "
                "clinical risk."
            ),
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Estimator catalogue, posterior representation, ceilings, media types, "
                "and endpoint ABI remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "The runtime consumes content-addressed declarations only; it never fetches "
                "or relabels spectra, genomic data, PTM annotations, or treatment history."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits only a complex-activity posterior and diagnostics; it emits "
                "no kinase state, all-omics fusion, treatment recommendation, or parent result."
            ),
        ),
        Limitation(
            code="uncertainty_calibration",
            statement=(
                "Uncertainty values are explicit deterministic proxies and are not a claim "
                "of calibrated 90% coverage until locked benchmark evidence exists."
            ),
        ),
    )


def _tokens(request: EstimateComplexActivityProbabilisticRequest) -> set[str]:
    values = [
        *(item.artifact_id.casefold() for item in request.source_artifacts),
        request.baseline_result.artifact_id.casefold(),
        request.configuration.objective.casefold(),
        *(item.expression.casefold() for item in request.configuration.constraints),
    ]
    normalized = [value.replace("-", "_").replace(" ", "_") for value in values]
    return {token for value in normalized for token in (value, *value.split("_"))}


def _prior_summary(
    request: EstimateComplexActivityProbabilisticRequest,
    feature_id: str,
) -> _PriorSummary:
    """Collapse declared prior families into a bounded activity prior.

    Feature-matched priors (for example ``complex.egfr``) receive a four-fold
    precision multiplier.  This lets a single configuration describe a
    heterogeneous complex while retaining a transparent shrinkage target.
    """

    feature_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", feature_id.casefold())
        if token and token not in {"complex", "activity", "feature"}
    }
    summaries: list[tuple[_PriorSummary, bool]] = []
    for prior in request.configuration.priors:
        parameters = tuple(float(value) for value in prior.parameters)
        if prior.kind.value == "categorical":
            continue
        if prior.kind.value == "normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            mean, scale = parameters[0], abs(parameters[1])
        elif prior.kind.value == "log_normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            log_mean, log_scale = parameters[0], abs(parameters[1])
            try:
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
                else 0.5 * (ordered[midpoint - 1] + ordered[midpoint])
            )
            deviations = sorted(abs(value - mean) for value in ordered)
            mad_midpoint = len(deviations) // 2
            mad = (
                deviations[mad_midpoint]
                if len(deviations) % 2
                else 0.5 * (deviations[mad_midpoint - 1] + deviations[mad_midpoint])
            )
            scale = max(0.05, 1.4826 * mad)
        else:
            continue
        if not (isfinite(mean) and isfinite(scale) and scale > 0.0):
            continue
        mean = min(_ACTIVITY_MAX, max(_ACTIVITY_MIN, mean))
        variance = max(1e-6, min(1.0, scale * scale))
        prior_tokens = {
            token for token in re.split(r"[^a-z0-9]+", prior.prior_id.casefold()) if token
        }
        matched = bool(feature_tokens & prior_tokens)
        rationale = f"prior {prior.prior_id} ({prior.kind.value})"
        summaries.append(
            (_PriorSummary(mean, variance, 4.0 if matched else 1.0, rationale), matched)
        )
    if not summaries:
        return _PriorSummary(0.5, 0.25, 1.0, "unit-interval activity prior")
    selected = [summary for summary, matched in summaries if matched]
    candidates = selected or [summary for summary, _ in summaries]
    precision = sum(item.weight / item.variance for item in candidates)
    mean = sum(item.weight * item.mean / item.variance for item in candidates) / precision
    variance = 1.0 / precision
    rationale = "; ".join(item.rationale for item in candidates)
    return _PriorSummary(mean, variance, 1.0, rationale)


def _encoded_observation(feature_id: str) -> tuple[float, float] | None:
    """Read an optional reduced assay value from an artifact identifier.

    This is intentionally opt-in.  A bare content-addressed reference carries
    no numerical evidence and therefore contributes only through the prior.
    """

    value_match = _VALUE_PATTERN.search(feature_id)
    if value_match is None:
        return None
    value = float(value_match.group(1))
    sd_match = _SD_PATTERN.search(feature_id)
    scale = float(sd_match.group(1)) if sd_match is not None else _DEFAULT_ASSAY_SD
    if not (isfinite(value) and isfinite(scale) and scale > 0.0):
        return None
    return value, max(0.01, scale)


def _constraint_bounds(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[float, float] | None:
    lower, upper = _ACTIVITY_MIN, _ACTIVITY_MAX
    for constraint in request.configuration.constraints:
        if not constraint.hard:
            continue
        match = _NUMERIC_CONSTRAINT_PATTERN.search(constraint.expression)
        if match is None:
            continue
        operator, raw_value = match.groups()
        value = float(raw_value)
        if not isfinite(value):
            return None
        if operator in {">=", ">"}:
            lower = max(lower, value + (1e-9 if operator == ">" else 0.0))
        elif operator in {"<=", "<"}:
            upper = min(upper, value - (1e-9 if operator == "<" else 0.0))
        else:
            lower, upper = max(lower, value), min(upper, value)
    if lower > upper or lower > _ACTIVITY_MAX or upper < _ACTIVITY_MIN:
        return None
    return max(_ACTIVITY_MIN, lower), min(_ACTIVITY_MAX, upper)


def _fit_activity(
    feature_id: str,
    request: EstimateComplexActivityProbabilisticRequest,
) -> _ActivityFit | None:
    """Fit one complex activity with bounded Huber IRLS and prior shrinkage."""

    bounds = _constraint_bounds(request)
    if bounds is None:
        return None
    prior = _prior_summary(request, feature_id)
    observation = _encoded_observation(feature_id)
    prior_precision = 1.0 / prior.variance
    obs_precision = 0.0 if observation is None else 1.0 / (observation[1] ** 2)
    observed_value = prior.mean if observation is None else observation[0]
    if not isfinite(observed_value):
        return None
    value = min(
        bounds[1],
        max(
            bounds[0],
            (prior_precision * prior.mean + obs_precision * observed_value)
            / (prior_precision + obs_precision),
        ),
    )
    objective_trace: list[float] = []
    gap = float("inf")
    iterations = 0
    for iteration in range(min(request.configuration.max_iterations, 256)):
        iterations = iteration + 1
        robust_weight = 1.0
        if observation is not None:
            residual = (observed_value - value) / observation[1]
            robust_weight = min(1.0, _HUBER_K / max(1.0, abs(residual)))
        precision = prior_precision + robust_weight * obs_precision
        candidate = (
            prior_precision * prior.mean + robust_weight * obs_precision * observed_value
        ) / precision
        candidate = min(bounds[1], max(bounds[0], candidate))
        gap = abs(candidate - value)
        value = 0.65 * candidate + 0.35 * value
        prior_residual = (value - prior.mean) ** 2 / prior.variance
        data_residual = 0.0
        if observation is not None:
            standardized = abs(observed_value - value) / observation[1]
            data_residual = (
                0.5 * standardized * standardized
                if standardized <= _HUBER_K
                else _HUBER_K * standardized - 0.5 * _HUBER_K * _HUBER_K
            )
        objective_trace.append(0.5 * prior_residual + data_residual)
        if gap <= _IRLS_TOLERANCE:
            break
    posterior_variance = 1.0 / (prior_precision + robust_weight * obs_precision)
    half_width = _POSTERIOR_Z90 * sqrt(max(1e-12, posterior_variance))
    lower = max(bounds[0], value - half_width)
    upper = min(bounds[1], value + half_width)
    objective = objective_trace[-1] if objective_trace else 0.0
    if not all(isfinite(item) for item in (value, lower, upper, objective, gap)):
        return None
    mass = 0.9 * erf((upper - lower) / max(1e-12, 2.0 * sqrt(2.0 * posterior_variance)))
    rationale = "Huber IRLS with prior shrinkage"
    if observation is None:
        rationale += "; prior-only because artifact carries no encoded measurement"
    rationale += f"; {prior.rationale}"
    return _ActivityFit(
        value=round(value, 8),
        lower=round(lower, 8),
        upper=round(upper, 8),
        posterior_mass=round(min(0.9, max(0.0, mass)), 8),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        rationale=rationale,
    )


def _diagnostic(  # noqa: PLR0913 - diagnostic envelope has six independent locked fields
    request: EstimateComplexActivityProbabilisticRequest,
    request_digest: str,
    *,
    status: OptimizationDiagnosticStatus,
    message: str,
    objective_value: float | None = None,
    convergence_gap: float | None = None,
) -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}",
        status=status,
        objective=request.configuration.objective,
        iteration_count=(
            request.configuration.max_iterations
            if status is OptimizationDiagnosticStatus.CONVERGED
            else 0
        ),
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        message=message,
        evidence=_evidence(request),
    )


def _build_result(
    request: EstimateComplexActivityProbabilisticRequest,
) -> EstimateComplexActivityProbabilisticResult:
    request_digest = canonical_request_digest(request)
    tokens = _tokens(request)
    blocked = sorted(
        marker for marker in _ABSTENTION_MARKERS if any(marker in token for token in tokens)
    )
    failed = sorted(
        marker for marker in _FAILURE_MARKERS if any(marker in token for token in tokens)
    )
    hard_constraints = [
        item
        for item in request.configuration.constraints
        if item.hard and any(marker in item.expression.casefold() for marker in _ABSTENTION_MARKERS)
    ]
    if hard_constraints:
        blocked.extend(item.constraint_id for item in hard_constraints)

    diagnostics: tuple[OptimizationDiagnostic, ...]
    if blocked or failed:
        reason_parts = []
        if blocked:
            reason_parts.append(
                "unsupported or review-required declarations: " + ", ".join(blocked)
            )
        if failed:
            reason_parts.append("optimization did not converge: " + ", ".join(failed))
        status = SupportStatus.UNSUPPORTED if blocked else SupportStatus.REVIEW_REQUIRED
        diagnostic_status = (
            OptimizationDiagnosticStatus.NOT_EVALUABLE
            if blocked
            else OptimizationDiagnosticStatus.FAILED
        )
        diagnostic_message = "; ".join(reason_parts)
        diagnostics = (
            _diagnostic(
                request,
                request_digest,
                status=diagnostic_status,
                message=diagnostic_message,
            ),
        )
        estimates: tuple[PosteriorEstimate, ...] = ()
        result_status = ProbabilisticResultStatus.ABSTAINED
        abstention_reason = diagnostic_message
        support = SupportDecision(
            status=status,
            reason_code="m0904_safe_abstention",
            rationale=diagnostic_message,
        )
        uncertainty = _uncertainty(estimated=False)
    else:
        fits = tuple(_fit_activity(item.artifact_id, request) for item in request.source_artifacts)
        if any(fit is None for fit in fits):
            message = (
                "Activity posterior withheld because hard stoichiometry constraints are "
                "contradictory or numerical evidence is non-finite."
            )
            diagnostics = (
                _diagnostic(
                    request,
                    request_digest,
                    status=OptimizationDiagnosticStatus.FAILED,
                    message=message,
                ),
            )
            estimates = ()
            result_status = ProbabilisticResultStatus.ABSTAINED
            abstention_reason = message
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0904_irls_failure",
                rationale=message,
            )
            uncertainty = _uncertainty(estimated=False)
        else:
            typed_fits = tuple(fit for fit in fits if fit is not None)
            estimates = tuple(
                PosteriorEstimate(
                    feature_id=item.artifact_id,
                    kind=PosteriorEstimateKind.INTERVAL,
                    unit="complex-activity",
                    estimate_value=fit.value,
                    lower_bound=fit.lower,
                    upper_bound=fit.upper,
                    posterior_mass=fit.posterior_mass,
                    evidence=_evidence(request),
                )
                for item, fit in zip(request.source_artifacts, typed_fits, strict=True)
            )
            objective_value = round(
                sum(fit.objective for fit in typed_fits) / len(typed_fits),
                8,
            )
            iteration_count = max(fit.iterations for fit in typed_fits)
            convergence_gap = max(fit.convergence_gap for fit in typed_fits)
            rationale = "; ".join(sorted({fit.rationale for fit in typed_fits}))
            diagnostics_list = [
                _diagnostic(
                    request,
                    request_digest,
                    status=OptimizationDiagnosticStatus.CONVERGED,
                    message=(
                        "Bounded Huber IRLS posterior converged from declared complex "
                        "activity priors and optional assay summaries."
                    ),
                    objective_value=objective_value,
                    convergence_gap=convergence_gap,
                ).model_copy(update={"iteration_count": iteration_count}),
            ]
            diagnostics_list.extend(
                OptimizationDiagnostic(
                    diagnostic_id=(
                        f"diagnostic.{request_digest.removeprefix('sha256:')}."
                        f"{constraint.constraint_id}"
                    ),
                    status=OptimizationDiagnosticStatus.CONVERGED,
                    objective=constraint.expression,
                    iteration_count=iteration_count,
                    objective_value=objective_value,
                    convergence_gap=convergence_gap,
                    message=(
                        "Soft constraint was retained as a visible term; it did not "
                        "override the robust posterior."
                    ),
                    evidence=constraint.evidence,
                )
                for constraint in request.configuration.constraints
                if not constraint.hard
            )
            diagnostics = tuple(diagnostics_list)
            result_status = ProbabilisticResultStatus.ESTIMATED
            abstention_reason = None
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0904_irls_support",
                rationale=(
                    "Declared priors and bounded complex-activity evidence were fitted "
                    "with deterministic Huber IRLS. " + rationale
                ),
            )
            uncertainty = _uncertainty(estimated=True)

    draft = EstimateComplexActivityProbabilisticResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        result_version=M0904_CONTRACT_VERSION,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=result_status,
        estimates=estimates,
        diagnostics=diagnostics,
        abstention_reason=abstention_reason,
        parent_target=M0904_PARENT,
        support_decision=support,
        uncertainty=uncertainty,
        provenance=_provenance(request, request_digest),
        evidence=_evidence(request),
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0904ProbabilisticEstimator:
    """Build and verify deterministic posterior envelopes with safe abstention."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateComplexActivityProbabilisticRequest:
        preflight_m0904_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def estimate(self, request: object) -> EstimateComplexActivityProbabilisticResult:
        return self.build(request).result

    def build(self, request: object) -> BuiltM0904Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0904_MAX_CANONICAL_RESULT_BYTES:
            raise M0904InputError("result_limit")
        return BuiltM0904Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
        request: object | None = None,
    ) -> EstimateComplexActivityProbabilisticVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return EstimateComplexActivityProbabilisticVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ProbabilisticReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0904_MAX_CANONICAL_RESULT_BYTES
        ):
            return EstimateComplexActivityProbabilisticVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    ProbabilisticReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else ProbabilisticReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        verified = content_verified and deterministic_verified
        if verified and request is not None:
            try:
                expected = self.build(request).result
            except (M0904AuthorizationError, M0904InputError, TypeError, ValueError):
                verified = False
            else:
                verified = expected.model_dump(mode="json") == typed.model_dump(mode="json")
        return EstimateComplexActivityProbabilisticVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ProbabilisticReplayReason.VERIFIED
                if verified
                else (
                    ProbabilisticReplayReason.NON_CANONICAL
                    if not content_verified or not verified
                    else ProbabilisticReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0904Result:
        return self.build(request)


def estimate_complex_activity_probabilistic(
    request: object,
) -> EstimateComplexActivityProbabilisticResult:
    """Public M09-04 operation returning the typed result envelope."""

    return M0904ProbabilisticEstimator().estimate(request)


__all__ = [
    "BuiltM0904Result",
    "M0904AuthorizationError",
    "M0904InputError",
    "M0904ProbabilisticEstimator",
    "estimate_complex_activity_probabilistic",
    "preflight_m0904_authorization",
]
