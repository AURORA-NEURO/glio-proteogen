"""Strict, deterministic M06-04 estimator boundary.

The compatibility optimizer preserves the original declaration-only behavior.
The opt-in ``locked_glioma_abundance_irls_v1`` path fits observed scalar or
interval protein-abundance values with robust Huber IRLS, feature-matched
Normal/log-normal/empirical priors, assay precision, and hard domain bounds.
It never opens caller artifacts or treats a caller-declared probability as
calibrated evidence.
"""

# The transport preparation path intentionally enumerates hostile input shapes.
# ruff: noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915, TRY301

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import exp, isfinite, sqrt
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_01.v1 import FormalStateFeatureValue, FormalStateMissingness
from glio_proteogen.contracts.m06_04 import (
    M0604_CONTRACT_VERSION,
    M0604_EVIDENCE_CLAIM,
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    M0604_MODULE_ID,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticResultStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceProbabilisticRequest)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0604_PROXY_OPTIMIZER: Final = "deterministic_proxy_v1"
M0604_GLIOMA_IRLS_OPTIMIZER: Final = "locked_glioma_abundance_irls_v1"
_AUTHORIZATION_MESSAGE: Final = "M06-04 probabilistic request is not authorized"
_INPUT_MESSAGE: Final = "M06-04 request failed strict validation"
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4_096
_MAX_PLAIN_NODES: Final = 100_000
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}
_HUBER_K: Final = 1.5
_POSTERIOR_Z90: Final = 1.6448536269514722
_IRLS_TOLERANCE: Final = 1e-7
_MAX_IRLS_ITERATIONS: Final = 256
_MIN_PRIOR_PARAMETERS: Final = 2
_VALUE_CONSTRAINT = re.compile(
    r"(?:abundance|protein|value)?\s*(>=|<=|==|>)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _AbundanceFit:
    estimate: PosteriorEstimate
    iterations: int
    objective: float
    convergence_gap: float


class ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Raised before an unauthorized posterior request traverses inputs."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class ProbabilisticEstimatorInputError(ValueError):
    """Raised for malformed input without reflecting caller payloads."""

    def __init__(self) -> None:
        super().__init__(_INPUT_MESSAGE)


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    if isinstance(candidate, BaseModel):
        return getattr(candidate, field, None)
    return None


def _state_text(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def _plain_value(
    value: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    """Convert only finite JSON-like values accepted at the transport edge."""

    if _depth > _MAX_PLAIN_DEPTH:
        raise ProbabilisticEstimatorInputError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise ProbabilisticEstimatorInputError
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Enum):
        return _plain_value(value.value, _depth=_depth + 1, _budget=budget)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if type(value) is list:
        items = cast("list[object]", value)
        if len(items) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise ProbabilisticEstimatorInputError
        return [_plain_value(item, _depth=_depth + 1, _budget=budget) for item in items]
    if type(value) is tuple:
        tuple_items = cast("tuple[object, ...]", value)
        if len(tuple_items) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise ProbabilisticEstimatorInputError
        return tuple(_plain_value(item, _depth=_depth + 1, _budget=budget) for item in tuple_items)
    if type(value) is dict:
        mapping = cast("dict[object, object]", value)
        if len(mapping) > _MAX_PLAIN_DICT_ITEMS:
            raise ProbabilisticEstimatorInputError
        result: dict[str, object] = {}
        for key, item in mapping.items():
            if type(key) is not str:
                raise ProbabilisticEstimatorInputError
            result[key] = _plain_value(item, _depth=_depth + 1, _budget=budget)
        return result
    raise ProbabilisticEstimatorInputError


def preflight_probabilistic_estimator_authorization(request: object) -> None:
    """Reject denied controls before schema, values, or artifacts are traversed."""

    if type(request) is not EstimateProteinAbundanceProbabilisticRequest and not isinstance(
        request, Mapping
    ):
        raise ProbabilisticEstimatorAuthorizationError
    try:
        context = _member(request, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise ProbabilisticEstimatorAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise ProbabilisticEstimatorAuthorizationError


def _validate_json_request(
    candidate: object,
    serialized: bytes | str,
) -> EstimateProteinAbundanceProbabilisticRequest:
    if not isinstance(candidate, Mapping):
        raise ProbabilisticEstimatorInputError
    preflight_probabilistic_estimator_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0604_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        strict_json_loads(serialized, max_bytes=M0604_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except ProbabilisticEstimatorAuthorizationError:
        raise
    except ProbabilisticEstimatorInputError:
        raise
    except Exception as error:
        raise ProbabilisticEstimatorInputError from error


def _prepare_request(candidate: object) -> EstimateProteinAbundanceProbabilisticRequest:
    if type(candidate) is EstimateProteinAbundanceProbabilisticRequest:
        preflight_probabilistic_estimator_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0604_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        try:
            return _REQUEST_ADAPTER.validate_json(raw, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, bytes | bytearray | str):
        try:
            decoded: object = strict_json_loads(
                candidate,
                max_bytes=M0604_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, Mapping):
                raise ProbabilisticEstimatorInputError
            preflight_probabilistic_estimator_authorization(decoded)
            serialized = candidate if isinstance(candidate, str) else bytes(candidate)
            return _validate_json_request(decoded, serialized)
        except ProbabilisticEstimatorAuthorizationError:
            raise
        except ProbabilisticEstimatorInputError:
            raise
        except (ValidationError, TypeError, ValueError) as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, Mapping):
        preflight_probabilistic_estimator_authorization(candidate)
        try:
            raw = canonical_json_bytes(_plain_value(candidate))
        except ProbabilisticEstimatorInputError:
            raise
        except (TypeError, ValueError) as error:
            raise ProbabilisticEstimatorInputError from error
        return _validate_json_request(candidate, raw)
    raise ProbabilisticEstimatorInputError


def _control_decisions(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        *tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=role_reference.decision_id,
                state=role_reference.state.value,
                policy_version=role_reference.policy_version,
                evidence_digest=role_reference.evidence.digest,
            )
            for role, role_reference in (
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        ),
    )


def _provenance(
    request: EstimateProteinAbundanceProbabilisticRequest,
    request_hash: str,
) -> ProvenanceRecord:
    configuration_digest = sha256_digest(request.configuration.model_dump(mode="json"))
    input_digests = tuple(
        artifact.digest for artifact in (*request.source_artifacts, request.representation_artifact)
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0604.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0604_MODULE_ID,
        module_version=M0604_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=configuration_digest,
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M0604_EVIDENCE_CLAIM,
        )
        for artifact in request.source_artifacts
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M06-04 calibration and uncertainty decomposition are not frozen; "
            "no probability is emitted by this provisional boundary."
        ),
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
            "Deterministic proxy intervals are not calibrated posterior intervals.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_proxy_not_calibrated",
            statement=(
                "Any estimate is a deterministic declaration-only proxy, not a calibrated "
                "posterior or biological probability."
            ),
        ),
        Limitation(
            code="external_model_not_executed",
            statement=(
                "Caller artifacts are never opened; learned, proteoform, and external "
                "mechanistic models are not executed at this boundary."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source artifacts, configuration, and controls are caller-declared; issuer "
                "authority is not authenticated."
            ),
        ),
    )


def _numeric_value(value: object) -> tuple[float, PosteriorEstimateKind] | None:
    state = getattr(value, "state", None)
    if state is not FormalStateMissingness.OBSERVED:
        return None
    scalar = getattr(value, "scalar_value", None)
    if scalar is not None:
        return (scalar, PosteriorEstimateKind.SCALAR) if isfinite(scalar) else None
    lower = getattr(value, "interval_lower", None)
    upper = getattr(value, "interval_upper", None)
    if lower is None or upper is None or not all(isfinite(item) for item in (lower, upper)):
        return None
    return ((lower + upper) / 2.0, PosteriorEstimateKind.INTERVAL)


def _estimates(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[PosteriorEstimate, ...] | None:
    definitions = {item.feature_id: item for item in request.state_schema.features}
    estimates: list[PosteriorEstimate] = []
    for value in request.feature_values:
        numeric = _numeric_value(value)
        if numeric is None:
            return None
        center, kind = numeric
        if kind is PosteriorEstimateKind.SCALAR:
            estimates.append(
                PosteriorEstimate(
                    feature_id=value.feature_id,
                    kind=kind,
                    unit=definitions[value.feature_id].unit,
                    estimate_value=center,
                )
            )
            continue
        lower = value.interval_lower
        upper = value.interval_upper
        if lower is None or upper is None:
            return None
        estimates.append(
            PosteriorEstimate(
                feature_id=value.feature_id,
                kind=kind,
                unit=definitions[value.feature_id].unit,
                estimate_value=center,
                lower_bound=lower,
                upper_bound=upper,
            )
        )
    return tuple(estimates)


def _prior_for_feature(
    request: EstimateProteinAbundanceProbabilisticRequest,
    feature_id: str,
) -> tuple[float, float, str]:
    """Reduce a declared prior family to a feature-specific Normal prior."""

    feature_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", feature_id.casefold())
        if token and token not in {"protein", "abundance", "feature"}
    }
    candidates: list[tuple[float, float, float, str, bool]] = []
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
            scale = max(0.05, sqrt(sum((item - mean) ** 2 for item in ordered) / len(ordered)))
        else:
            continue
        if not (isfinite(mean) and isfinite(scale) and scale > 0.0):
            continue
        prior_tokens = {
            token for token in re.split(r"[^a-z0-9]+", prior.prior_id.casefold()) if token
        }
        matched = bool(feature_tokens & prior_tokens)
        candidates.append((mean, scale, 4.0 if matched else 1.0, prior.prior_id, matched))
    if not candidates:
        return 0.0, 1.0, "unit-scale protein-abundance prior"
    selected = [item for item in candidates if item[4]] or candidates
    precision = sum(item[2] / (item[1] * item[1]) for item in selected)
    mean = sum(item[2] * item[0] / (item[1] * item[1]) for item in selected) / precision
    scale = sqrt(1.0 / precision)
    rationale = "; ".join(f"prior {item[3]}" for item in selected)
    return mean, scale, rationale


def _abundance_bounds(
    request: EstimateProteinAbundanceProbabilisticRequest,
    feature_id: str,
) -> tuple[float | None, float | None] | None:
    definition = next(
        item for item in request.state_schema.features if item.feature_id == feature_id
    )
    lower, upper = definition.domain_lower, definition.domain_upper
    for constraint in request.configuration.constraints:
        if not constraint.hard:
            continue
        match = _VALUE_CONSTRAINT.search(constraint.expression)
        if match is None:
            continue
        operator, raw = match.groups()
        value = float(raw)
        if not isfinite(value):
            return None
        if operator in {">=", ">"}:
            lower = (
                max(lower, value + (1e-9 if operator == ">" else 0.0))
                if lower is not None
                else value
            )
        elif operator == "<=":
            upper = min(upper, value) if upper is not None else value
        else:
            lower, upper = value, value
    if lower is not None and upper is not None and lower > upper:
        return None
    return lower, upper


def _fit_abundance(
    value: FormalStateFeatureValue,
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> _AbundanceFit | None:
    feature_id = value.feature_id
    bounds = _abundance_bounds(request, feature_id)
    if bounds is None:
        return None
    if value.state is not FormalStateMissingness.OBSERVED:
        return None
    scalar = value.scalar_value
    interval_lower = value.interval_lower
    interval_upper = value.interval_upper
    if scalar is not None:
        observed, assay_sd = scalar, 0.25
    elif interval_lower is not None and interval_upper is not None:
        observed = (interval_lower + interval_upper) / 2.0
        assay_sd = max(0.01, (interval_upper - interval_lower) / (2.0 * _POSTERIOR_Z90))
    else:
        return None
    if not isfinite(observed):
        return None
    prior_mean, prior_sd, _prior_rationale = _prior_for_feature(request, feature_id)
    prior_precision = 1.0 / max(1e-8, prior_sd * prior_sd)
    assay_precision = 1.0 / (assay_sd * assay_sd)
    estimate = (prior_precision * prior_mean + assay_precision * observed) / (
        prior_precision + assay_precision
    )
    if bounds[0] is not None:
        estimate = max(bounds[0], estimate)
    if bounds[1] is not None:
        estimate = min(bounds[1], estimate)
    robust_weight = 1.0
    gap = float("inf")
    objective = float("inf")
    iterations = 0
    for iteration in range(min(request.configuration.max_iterations, _MAX_IRLS_ITERATIONS)):
        iterations = iteration + 1
        residual = (observed - estimate) / assay_sd
        robust_weight = min(1.0, _HUBER_K / max(1.0, abs(residual)))
        precision = prior_precision + robust_weight * assay_precision
        candidate = (
            prior_precision * prior_mean + robust_weight * assay_precision * observed
        ) / precision
        if bounds[0] is not None:
            candidate = max(bounds[0], candidate)
        if bounds[1] is not None:
            candidate = min(bounds[1], candidate)
        gap = abs(candidate - estimate)
        estimate = 0.65 * candidate + 0.35 * estimate
        standardized = abs(observed - estimate) / assay_sd
        data_loss = (
            0.5 * standardized * standardized
            if standardized <= _HUBER_K
            else _HUBER_K * standardized - 0.5 * _HUBER_K * _HUBER_K
        )
        objective = 0.5 * (estimate - prior_mean) ** 2 / (prior_sd * prior_sd) + data_loss
        if gap <= _IRLS_TOLERANCE:
            break
    if not all(isfinite(item) for item in (estimate, objective, gap)):
        return None
    posterior_sd = sqrt(1.0 / (prior_precision + robust_weight * assay_precision))
    lower = estimate - _POSTERIOR_Z90 * posterior_sd
    upper = estimate + _POSTERIOR_Z90 * posterior_sd
    if bounds[0] is not None:
        lower = max(bounds[0], lower)
    if bounds[1] is not None:
        upper = min(bounds[1], upper)
    posterior_mass = 0.9
    return _AbundanceFit(
        estimate=PosteriorEstimate(
            feature_id=feature_id,
            kind=PosteriorEstimateKind.INTERVAL,
            unit=value.unit,
            estimate_value=round(estimate, 8),
            lower_bound=round(lower, 8),
            upper_bound=round(upper, 8),
            posterior_mass=posterior_mass,
            evidence=value.evidence,
        ),
        iterations=iterations,
        objective=round(objective, 8),
        convergence_gap=round(gap, 8),
    )


def _glioma_estimates(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[tuple[PosteriorEstimate, ...], int, float, float] | None:
    fits = tuple(_fit_abundance(value, request) for value in request.feature_values)
    if any(fit is None for fit in fits):
        return None
    typed = tuple(fit for fit in fits if fit is not None)
    return (
        tuple(fit.estimate for fit in typed),
        max(fit.iterations for fit in typed),
        sum(fit.objective for fit in typed) / len(typed),
        max(fit.convergence_gap for fit in typed),
    )


def _support(status: ProbabilisticResultStatus, reason: str) -> SupportDecision:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="provisional_proxy_estimate",
            rationale=(
                "All declared controls passed and the locked deterministic proxy accepted "
                "the observed numeric representation."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="probabilistic_estimator_abstained",
        rationale=reason,
    )


def _diagnostic(
    request: EstimateProteinAbundanceProbabilisticRequest,
    status: ProbabilisticResultStatus,
    reason: str,
    *,
    iteration_count: int = 0,
    objective_value: float = 0.0,
    convergence_gap: float = 0.0,
) -> OptimizationDiagnostic:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return OptimizationDiagnostic(
            diagnostic_id="diagnostic.m0604.proxy",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective=request.configuration.objective,
            iteration_count=iteration_count,
            objective_value=objective_value,
            convergence_gap=convergence_gap,
            message=reason,
        )
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m0604.abstain",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective=request.configuration.objective,
        iteration_count=0,
        message=reason,
    )


class M0604ProbabilisticEstimatorEngine:
    """Execute the compatibility proxy or locked glioma abundance posterior."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinAbundanceProbabilisticRequest:
        return _prepare_request(request)

    def estimate(self, request: object) -> EstimateProteinAbundanceProbabilisticResult:
        canonical = _prepare_request(request)
        request_hash = canonical_request_digest(canonical)
        reason = (
            "The selected estimator family or optimizer is not authorized by the provisional "
            "M06-04 execution boundary."
        )
        estimates: tuple[PosteriorEstimate, ...] | None = None
        diagnostic_iterations = 0
        diagnostic_objective = 0.0
        diagnostic_gap = 0.0
        if (
            canonical.configuration.estimator_family
            is ProbabilisticEstimatorFamily.MECHANISM_GUIDED
            and canonical.configuration.optimizer
            in {M0604_PROXY_OPTIMIZER, M0604_GLIOMA_IRLS_OPTIMIZER}
        ):
            if canonical.configuration.optimizer == M0604_GLIOMA_IRLS_OPTIMIZER:
                fitted = _glioma_estimates(canonical)
                if fitted is not None:
                    estimates, iterations, objective, gap = fitted
                    diagnostic_iterations = iterations
                    diagnostic_objective = objective
                    diagnostic_gap = gap
                    reason = (
                        "Locked glioma protein-abundance Huber IRLS posterior converged "
                        "under feature priors, assay precision, and hard constraints."
                    )
                else:
                    reason = "Observed values are outside the locked abundance posterior domain."
            else:
                estimates = _estimates(canonical)
                if estimates is not None:
                    reason = "Observed values accepted by the compatibility declaration proxy."
        status = (
            ProbabilisticResultStatus.ESTIMATED
            if estimates
            else ProbabilisticResultStatus.ABSTAINED
        )
        diagnostic = _diagnostic(
            canonical,
            status,
            reason,
            iteration_count=diagnostic_iterations,
            objective_value=diagnostic_objective,
            convergence_gap=diagnostic_gap,
        )
        candidate = EstimateProteinAbundanceProbabilisticResult.model_construct(
            result_id=f"result.m0604.{request_hash.removeprefix('sha256:')}",
            result_version=M0604_CONTRACT_VERSION,
            request_digest=request_hash,
            result_digest=_ZERO_DIGEST,
            request=canonical,
            status=status,
            estimates=estimates or (),
            diagnostics=(diagnostic,),
            abstention_reason=None if status is ProbabilisticResultStatus.ESTIMATED else reason,
            parent_target="biomarker_panel",
            emits_parent=False,
            support_decision=_support(status, reason),
            uncertainty=_uncertainty(),
            provenance=_provenance(canonical, request_hash),
            evidence=_evidence(canonical),
            limitations=_limitations(),
        )
        payload = candidate.model_dump(mode="python")
        payload["result_digest"] = result_payload_digest(candidate)
        return EstimateProteinAbundanceProbabilisticResult.model_validate(payload, strict=True)


def estimate_protein_abundance_probabilistic(
    request: object,
) -> EstimateProteinAbundanceProbabilisticResult:
    """Estimate from one strict request, abstaining when the proxy cannot run."""

    return M0604ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M0604_PROXY_OPTIMIZER",
    "M0604ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "estimate_protein_abundance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
