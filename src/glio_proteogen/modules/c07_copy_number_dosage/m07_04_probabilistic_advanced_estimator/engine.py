"""Deterministic, replay-verifiable M07-04 estimator boundary.

The dossier describes an advanced probabilistic estimator but does not freeze
the model registry, weights, feature catalogue, posterior semantics, or
endpoint ABI.  This implementation therefore executes a deliberately small
declaration-only proxy: a locked mechanism-guided configuration may project
finite caller-declared scalar/interval observations into typed estimates.
Every other family, optimizer, categorical observation, or malformed transport
is rejected or safely abstained.  No artifact is opened and no calibrated
probability is emitted.
"""

# The transport preparation path intentionally enumerates hostile input shapes.
# ruff: noqa: C901, PLR0911, PLR0912, TRY301

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import erf, exp, isfinite, log, sqrt
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_04 import (
    M0704_CONTRACT_VERSION,
    M0704_EVIDENCE_CLAIM,
    M0704_MAX_CANONICAL_REQUEST_BYTES,
    M0704_MODULE_ID,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimateCopyNumberDosageProbabilisticResult,
    EstimatorObservation,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    ProbabilisticResultStatus,
    canonical_request_digest,
    expected_uncertainty,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

# The old declaration-only name is retained as a compatibility alias. Both
# names execute the same bounded GBM dosage model below.
M0704_GBM_OPTIMIZER: Final = "locked_gbm_copy_number_irls_v1"
M0704_PROXY_OPTIMIZER: Final = M0704_GBM_OPTIMIZER
_LEGACY_PROXY_OPTIMIZER: Final = "locked_declaration_proxy_v1"
_SUPPORTED_OPTIMIZERS: Final = frozenset({M0704_GBM_OPTIMIZER, _LEGACY_PROXY_OPTIMIZER})
_REQUEST_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4_096
_MAX_PLAIN_NODES: Final = 100_000
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}

_HUBER_K: Final = 1.5
_POSTERIOR_Z90: Final = 1.6448536269514722
_MIN_SCALE: Final = 1e-3
_MAX_SCALE: Final = 1e3
_PRIOR_ARITY: Final = 2
_CONVERGENCE_TOLERANCE: Final = 1e-9
_COPY_NUMBER_MAX: Final = 32.0
_GBM_DOSAGE_PRIORS: Final = {
    # Broad, research-only priors for recurrent GBM dosage events. The assay
    # observation still dominates; marker recognition prevents treating all
    # glioma loci as exchangeable.
    "egfr": (4.0, 2.0, "GBM EGFR amplification prior"),
    "pdgfra": (4.0, 2.0, "GBM PDGFRA amplification prior"),
    "met": (4.0, 2.0, "GBM MET amplification prior"),
    "cdk4": (4.0, 2.0, "GBM CDK4 amplification prior"),
    "mdm2": (4.0, 2.0, "GBM MDM2 amplification prior"),
    "mycn": (4.0, 2.0, "GBM MYCN amplification prior"),
    "cdkn2a": (1.0, 1.0, "GBM CDKN2A loss prior"),
    "cdkn2b": (1.0, 1.0, "GBM CDKN2B loss prior"),
    "pten": (1.0, 1.0, "GBM PTEN loss prior"),
    "nf1": (1.0, 1.0, "GBM NF1 loss prior"),
    "chr10": (1.0, 1.0, "GBM chromosome-10 loss prior"),
}
_TOKEN_RE: Final = re.compile(r"[a-z0-9]+")
_CONSTRAINT_RE: Final = re.compile(
    r"^(?P<feature>[a-z0-9_.-]+)\s*(?P<op>>=|<=|==)\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _FeatureProfile:
    family: str
    lower: float | None
    upper: float | None
    default_mean: float
    default_scale: float
    marker_rationale: str


@dataclass(frozen=True)
class _PriorSpec:
    mean: float
    scale: float
    rationale: str


@dataclass(frozen=True)
class _PosteriorFit:
    estimate: PosteriorEstimate
    objective: float
    convergence_gap: float
    iterations: int
    rationale: str


class ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Raised before unauthorized requests traverse representation metadata."""

    def __init__(self) -> None:
        super().__init__(
            "M07-04 requires accepted controls, resolved identity, and granted consent"
        )


class ProbabilisticEstimatorInputError(ValueError):
    """Raised for malformed or over-limit request transport."""

    def __init__(self, detail: str = "M07-04 request is invalid") -> None:
        super().__init__(detail)


class ProbabilisticEstimatorReplayError(ValueError):
    """Raised when a result cannot be reproduced from its exact request."""

    def __init__(self, detail: str = "verification failed") -> None:
        super().__init__(f"M07-04 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state_text(value: object) -> object:
    return getattr(value, "value", value)


def _plain_value(
    value: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    """Convert only strict JSON-like values for canonical transport."""

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
    """Reject denied controls before schema, observations, or artifacts are traversed."""

    if type(request) is not EstimateCopyNumberDosageProbabilisticRequest and not isinstance(
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
    except Exception:  # noqa: BLE001 - hostile values fail closed.
        raise ProbabilisticEstimatorAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise ProbabilisticEstimatorAuthorizationError


def _validate_json_request(
    candidate: object,
    serialized: bytes | str,
) -> EstimateCopyNumberDosageProbabilisticRequest:
    if not isinstance(candidate, Mapping):
        raise ProbabilisticEstimatorInputError
    preflight_probabilistic_estimator_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0704_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        strict_json_loads(serialized, max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except ProbabilisticEstimatorAuthorizationError:
        raise
    except ProbabilisticEstimatorInputError:
        raise
    except Exception as error:
        raise ProbabilisticEstimatorInputError from error


def _prepare_request(candidate: object) -> EstimateCopyNumberDosageProbabilisticRequest:
    if type(candidate) is EstimateCopyNumberDosageProbabilisticRequest:
        preflight_probabilistic_estimator_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0704_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        try:
            return _REQUEST_ADAPTER.validate_json(raw, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, bytes | bytearray | str):
        try:
            decoded: object = strict_json_loads(
                candidate,
                max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, Mapping):
                raise ProbabilisticEstimatorInputError
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
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        *tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
            )
            for role, reference in (
                (ControlRole.PROVENANCE, refs.provenance),
                (ControlRole.CONSENT, refs.consent),
                (ControlRole.QUALITY, refs.quality),
                (ControlRole.SUPPORT, refs.support),
                (ControlRole.INTENDED_USE, refs.intended_use),
            )
        ),
    )


def _provenance(
    request: EstimateCopyNumberDosageProbabilisticRequest,
    request_hash: str,
) -> ProvenanceRecord:
    input_digests = tuple(
        artifact.digest for artifact in (request.representation_result, *request.source_artifacts)
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0704.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0704_MODULE_ID,
        module_version=M0704_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M0704_EVIDENCE_CLAIM,
        )
        for artifact in (request.representation_result, *request.source_artifacts)
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_proxy_not_calibrated",
            statement=(
                "The conjugate posterior is a deterministic research estimate, not a clinically "
                "calibrated probability and must not be used as a treatment recommendation."
            ),
        ),
        Limitation(
            code="external_model_not_executed",
            statement=(
                "Caller artifacts are never opened; the locked estimator uses only typed values, "
                "declared priors, and copy-number marker semantics."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source artifacts, observations, configuration, and controls are caller "
                "declared; issuer authority is not authenticated."
            ),
        ),
    )


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(value.casefold()))


def _feature_profile(observation: EstimatorObservation) -> _FeatureProfile:
    """Classify a dosage feature and attach GBM-aware physical bounds."""

    unit = observation.unit.casefold().replace("_", "-").replace(" ", "-")
    tokens = _tokens(observation.feature_id)
    marker = next((name for name in _GBM_DOSAGE_PRIORS if name in tokens), None)
    marker_rationale = (
        _GBM_DOSAGE_PRIORS[marker][2] if marker is not None else "neutral dosage prior"
    )
    if "copy" in tokens or "dosage" in tokens or unit in {"copy-number", "copies"}:
        if marker is not None:
            mean, scale, _ = _GBM_DOSAGE_PRIORS[marker]
        else:
            mean, scale = 2.0, 1.0
        return _FeatureProfile(
            family="copy_number",
            lower=0.0,
            upper=_COPY_NUMBER_MAX,
            default_mean=mean,
            default_scale=scale,
            marker_rationale=marker_rationale,
        )
    if unit in {"fraction", "ratio", "allelic-balance", "allelic_fraction"} or any(
        token in tokens for token in ("fraction", "balance", "ratio")
    ):
        return _FeatureProfile(
            family="fraction",
            lower=0.0,
            upper=1.0,
            default_mean=0.5,
            default_scale=0.25,
            marker_rationale="bounded allelic-balance prior",
        )
    if unit in {"log2-ratio", "log2ratio", "log2"} or "log2" in tokens:
        return _FeatureProfile(
            family="log2_ratio",
            lower=None,
            upper=None,
            default_mean=0.0,
            default_scale=1.0,
            marker_rationale="diploid log2-ratio prior",
        )
    return _FeatureProfile(
        family="scalar",
        lower=None,
        upper=None,
        default_mean=0.0,
        default_scale=1.0,
        marker_rationale="generic scalar prior",
    )


def _numeric_prior(
    prior: ProbabilisticPrior,
    profile: _FeatureProfile,
) -> _PriorSpec | None:
    """Decode the small, explicit prior grammar into a finite Normal prior."""

    values = tuple(float(value) for value in prior.parameters)
    if not values or any(not isfinite(value) for value in values):
        return None
    if prior.kind is ProbabilisticPriorKind.NORMAL:
        if len(values) < _PRIOR_ARITY:
            return None
        mean, scale = values[:2]
    elif prior.kind is ProbabilisticPriorKind.LOG_NORMAL:
        if len(values) < _PRIOR_ARITY:
            return None
        log_mean, log_scale = values[:2]
        if log_scale <= 0 or log_mean > log(_MAX_SCALE):
            return None
        mean = exp(log_mean + 0.5 * log_scale**2)
        variance = (exp(log_scale**2) - 1.0) * exp(2.0 * log_mean + log_scale**2)
        scale = sqrt(variance) if isfinite(variance) and variance > 0 else 0.0
    elif prior.kind is ProbabilisticPriorKind.EMPIRICAL:
        # Empirical priors are ordered support points. Use a robust median and
        # MAD-derived scale rather than pretending the points are iid samples.
        ordered = sorted(values)
        middle = len(ordered) // 2
        mean = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        deviations = sorted(abs(value - mean) for value in ordered)
        mad = deviations[len(deviations) // 2]
        scale = 1.4826 * mad if mad > 0 else profile.default_scale
    else:
        return None
    if not isfinite(mean) or not isfinite(scale) or scale <= 0:
        return None
    if profile.lower is not None and mean < profile.lower:
        return None
    if profile.upper is not None and mean > profile.upper:
        return None
    return _PriorSpec(
        mean=mean,
        scale=min(max(scale, _MIN_SCALE), _MAX_SCALE),
        rationale=f"declared {prior.kind.value} prior {prior.prior_id}",
    )


def _prior_for(
    observation: EstimatorObservation,
    profile: _FeatureProfile,
    priors: tuple[ProbabilisticPrior, ...],
) -> _PriorSpec:
    feature_tokens = _tokens(observation.feature_id)
    marker_tokens = feature_tokens & _GBM_DOSAGE_PRIORS.keys()
    # A feature-keyed prior is authoritative. Generic copy-number priors do not
    # silently override the locked GBM marker priors.
    for prior in priors:
        prior_tokens = _tokens(prior.prior_id)
        if (marker_tokens and marker_tokens & prior_tokens) or (
            not marker_tokens and feature_tokens & prior_tokens
        ):
            decoded = _numeric_prior(prior, profile)
            if decoded is not None:
                return decoded
    if not marker_tokens:
        for prior in priors:
            decoded = _numeric_prior(prior, profile)
            if decoded is not None:
                return decoded
    return _PriorSpec(
        mean=profile.default_mean,
        scale=profile.default_scale,
        rationale=profile.marker_rationale,
    )


def _constraint_bounds(
    feature_id: str,
    profile: _FeatureProfile,
    constraints: tuple[object, ...],
) -> tuple[float | None, float | None] | None:
    """Apply only the locked numeric hard-constraint grammar."""

    lower, upper = profile.lower, profile.upper
    normalized_feature = feature_id.casefold().replace("_", "-")
    for constraint in constraints:
        if not getattr(constraint, "hard", False):
            continue
        expression = getattr(constraint, "expression", "").strip().casefold()
        if expression in {"nonnegative", "dosage >= 0", "copy-number >= 0"}:
            lower = max(lower if lower is not None else float("-inf"), 0.0)
            continue
        match = _CONSTRAINT_RE.fullmatch(expression)
        if match is None:
            continue
        target = match.group("feature").replace("_", "-")
        if target not in {normalized_feature, "*", "all"}:
            continue
        value = float(match.group("value"))
        if not isfinite(value):
            return None
        operator = match.group("op")
        if operator in {">=", "=="}:
            lower = value if lower is None else max(lower, value)
        if operator in {"<=", "=="}:
            upper = value if upper is None else min(upper, value)
    if lower is not None and upper is not None and lower > upper:
        return None
    return lower, upper


def _likelihood(
    observation: EstimatorObservation, profile: _FeatureProfile
) -> tuple[float, float] | None:
    if observation.scalar_value is not None:
        value = float(observation.scalar_value)
        if not isfinite(value):
            return None
        scale = {"copy_number": 0.50, "fraction": 0.08, "log2_ratio": 0.25}.get(
            profile.family, 0.50
        )
        return value, scale
    if observation.interval_lower is None or observation.interval_upper is None:
        return None
    lower, upper = float(observation.interval_lower), float(observation.interval_upper)
    if not all(isfinite(item) for item in (lower, upper)) or lower > upper:
        return None
    center = (lower + upper) / 2.0
    # Treat a declared interval as a central 90% assay interval. A floor keeps
    # zero-width intervals numerically stable while retaining their direction.
    scale = max((upper - lower) / (2.0 * _POSTERIOR_Z90), _MIN_SCALE)
    return center, scale


def _normal_cdf(value: float, mean: float, scale: float) -> float:
    return 0.5 * (1.0 + erf((value - mean) / (scale * sqrt(2.0))))


def _fit_posterior(
    observation: EstimatorObservation,
    *,
    priors: tuple[ProbabilisticPrior, ...] = (),
    constraints: tuple[object, ...] = (),
    max_iterations: int = 32,
    evidence: tuple[EvidenceReference, ...] = (),
) -> _PosteriorFit | None:
    profile = _feature_profile(observation)
    likelihood = _likelihood(observation, profile)
    if likelihood is None:
        return None
    value, measurement_scale = likelihood
    prior = _prior_for(observation, profile, priors)
    bounds = _constraint_bounds(observation.feature_id, profile, constraints)
    if bounds is None:
        return None
    lower, upper = bounds
    prior_variance = prior.scale**2
    measurement_variance = measurement_scale**2
    mean = prior.mean
    gap = float("inf")
    robust_weight = 1.0
    for _iteration in range(1, max(1, min(max_iterations, 256)) + 1):
        residual = (value - mean) / measurement_scale
        if not isfinite(residual):
            return None
        robust_weight = 1.0 if abs(residual) <= _HUBER_K else _HUBER_K / abs(residual)
        likelihood_precision = robust_weight / measurement_variance
        posterior_precision = 1.0 / prior_variance + likelihood_precision
        updated = (prior.mean / prior_variance + likelihood_precision * value) / posterior_precision
        if lower is not None:
            updated = max(updated, lower)
        if upper is not None:
            updated = min(updated, upper)
        gap = abs(updated - mean)
        mean = updated
        if gap <= _CONVERGENCE_TOLERANCE:
            break
    posterior_variance = 1.0 / (1.0 / prior_variance + robust_weight / measurement_variance)
    posterior_scale = sqrt(posterior_variance)
    if not all(isfinite(item) for item in (mean, posterior_scale, gap)):
        return None
    posterior_lower = mean - _POSTERIOR_Z90 * posterior_scale
    posterior_upper = mean + _POSTERIOR_Z90 * posterior_scale
    if lower is not None:
        posterior_lower = max(posterior_lower, lower)
    if upper is not None:
        posterior_upper = min(posterior_upper, upper)
    if posterior_lower > posterior_upper:
        posterior_lower = posterior_upper = mean
    standardized = abs(value - mean) / sqrt(measurement_variance + prior_variance)
    support_mass = min(max(exp(-0.5 * standardized**2), 0.0), 1.0)
    if observation.interval_lower is not None and observation.interval_upper is not None:
        support_mass = min(
            max(
                _normal_cdf(float(observation.interval_upper), mean, posterior_scale)
                - _normal_cdf(float(observation.interval_lower), mean, posterior_scale),
                0.0,
            ),
            1.0,
        )
    if observation.scalar_value is not None:
        estimate = PosteriorEstimate(
            feature_id=observation.feature_id,
            kind=PosteriorEstimateKind.SCALAR,
            unit=observation.unit,
            estimate_value=mean,
            posterior_mass=support_mass,
            evidence=evidence,
        )
    else:
        estimate = PosteriorEstimate(
            feature_id=observation.feature_id,
            kind=PosteriorEstimateKind.INTERVAL,
            unit=observation.unit,
            estimate_value=mean,
            lower_bound=posterior_lower,
            upper_bound=posterior_upper,
            posterior_mass=support_mass,
            evidence=evidence,
        )
    objective = 0.5 * (
        (value - mean) ** 2 / measurement_variance
        + (mean - prior.mean) ** 2 / prior_variance
    )
    if not isfinite(objective):
        return None
    rationale = (
        f"{profile.family} Huber-IRLS update using {prior.rationale}; {profile.marker_rationale}"
    )
    return _PosteriorFit(
        estimate=estimate,
        objective=objective,
        convergence_gap=gap,
        iterations=_iteration,
        rationale=rationale,
    )


def _posterior(observation: EstimatorObservation) -> PosteriorEstimate | None:
    """Compatibility helper using the neutral GBM defaults."""

    fit = _fit_posterior(observation)
    return fit.estimate if fit is not None else None


def _posteriors(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[tuple[PosteriorEstimate, ...], tuple[_PosteriorFit, ...]] | None:
    source_by_digest = {
        artifact.digest: artifact
        for artifact in (request.representation_result, *request.source_artifacts)
    }
    fits: list[_PosteriorFit] = []
    for observation in request.observations:
        artifact = source_by_digest.get(observation.source_artifact_digest)
        if artifact is None:
            return None
        evidence = (
            EvidenceReference(
                reference=artifact,
                role="evidence",
                claim="Typed M07-04 dosage observation used by the locked GBM posterior model.",
            ),
        )
        fit = _fit_posterior(
            observation,
            priors=request.configuration.priors,
            constraints=request.configuration.constraints,
            max_iterations=request.configuration.max_iterations,
            evidence=evidence,
        )
        if fit is None:
            return None
        fits.append(fit)
    if not fits:
        return None
    return tuple(item.estimate for item in fits), tuple(fits)


def _support(status: ProbabilisticResultStatus, reason: str) -> SupportDecision:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="gbm_copy_number_irls_estimate",
            rationale=(
                "Accepted controls and finite numeric observations passed the locked GBM "
                "copy-number posterior update with explicit assay variance and constraints."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="probabilistic_estimator_abstained",
        rationale=reason,
    )


def _diagnostic(
    request: EstimateCopyNumberDosageProbabilisticRequest,
    status: ProbabilisticResultStatus,
    reason: str,
    fits: tuple[_PosteriorFit, ...] = (),
) -> OptimizationDiagnostic:
    if status is ProbabilisticResultStatus.ESTIMATED:
        objective = sum(item.objective for item in fits)
        iterations = max((item.iterations for item in fits), default=1)
        gap = max((item.convergence_gap for item in fits), default=0.0)
        rationale = "; ".join(item.rationale for item in fits[:3])
        return OptimizationDiagnostic(
            diagnostic_id="diagnostic.m0704.gbm-irls",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective=request.configuration.objective,
            iteration_count=iterations,
            objective_value=objective,
            convergence_gap=gap,
            message=(
                "Deterministic Huber-IRLS Normal updates converged for the typed dosage "
                f"observations ({rationale})."
            ),
        )
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m0704.abstain",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective=request.configuration.objective,
        iteration_count=0,
        message=reason,
    )


def _build_result(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> EstimateCopyNumberDosageProbabilisticResult:
    request_hash = canonical_request_digest(request)
    reason = (
        "The selected estimator family or optimizer is not authorized by the provisional "
        "M07-04 execution boundary."
    )
    estimates: tuple[PosteriorEstimate, ...] | None = None
    fits: tuple[_PosteriorFit, ...] = ()
    if (
        request.configuration.estimator_family is ProbabilisticEstimatorFamily.MECHANISM_GUIDED
        and request.configuration.optimizer in _SUPPORTED_OPTIMIZERS
    ):
        posterior_bundle = _posteriors(request)
        if posterior_bundle is None:
            reason = (
                "At least one observation is categorical, non-finite, unresolved, or "
                "incompatible with the locked GBM dosage model; no negative finding is emitted."
            )
        else:
            estimates, fits = posterior_bundle
        if estimates is not None and not estimates:
            reason = "The request contains no estimable observations."
    status = (
        ProbabilisticResultStatus.ESTIMATED if estimates else ProbabilisticResultStatus.ABSTAINED
    )
    candidate = EstimateCopyNumberDosageProbabilisticResult.model_construct(
        result_id=f"result.{request_hash.removeprefix('sha256:')}",
        result_version=M0704_CONTRACT_VERSION,
        request_digest=request_hash,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimates=estimates or (),
        diagnostics=(_diagnostic(request, status, reason, fits),),
        abstention_reason=None if status is ProbabilisticResultStatus.ESTIMATED else reason,
        parent_target="proteotype",
        emits_parent=False,
        support_decision=_support(status, reason),
        uncertainty=expected_uncertainty(),
        provenance=_provenance(request, request_hash),
        evidence=_evidence(request),
        limitations=_limitations(),
        human_review_required=status is not ProbabilisticResultStatus.ESTIMATED,
    )
    payload = candidate.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(candidate)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0704ProbabilisticEstimatorEngine:
    """Execute the provisional proxy or return a typed safe abstention."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateCopyNumberDosageProbabilisticRequest:
        return _prepare_request(request)

    def estimate(self, request: object) -> EstimateCopyNumberDosageProbabilisticResult:
        return _build_result(_prepare_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> EstimateCopyNumberDosageProbabilisticResult:
        """Verify the self-digest and optionally replay the exact request."""

        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorReplayError from error
        if not verify_result_digest(typed):
            raise ProbabilisticEstimatorReplayError
        if replay:
            replayed = self.estimate(typed.request)
            if replayed != typed:
                raise ProbabilisticEstimatorReplayError
        return typed


def estimate_copy_number_dosage_probabilistic(
    request: object,
) -> EstimateCopyNumberDosageProbabilisticResult:
    """Estimate one strict request, abstaining when the proxy cannot run."""

    return M0704ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M0704_GBM_OPTIMIZER",
    "M0704_PROXY_OPTIMIZER",
    "M0704ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "ProbabilisticEstimatorReplayError",
    "estimate_copy_number_dosage_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
