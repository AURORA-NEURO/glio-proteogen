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
M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER: Final = (
    "locked_glioma_abundance_program_irls_v1"
)
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
_GLIOMA_OBJECTIVE_TOLERANCE: Final = 1e-10
_GLIOMA_BACKTRACKING_STEPS: Final = 40
_GLIOMA_BACKTRACKING_FACTOR: Final = 0.5
_MIN_PRIOR_PARAMETERS: Final = 2
_VALUE_CONSTRAINT = re.compile(
    r"(?:abundance|protein|value)?\s*(>=|<=|==|>)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)

# A small, explicit GBM proteotype prior.  These are pathway-level marker
# identities, not a learned classifier: the graph is deliberately visible and
# replayable at the transport boundary.  Aliases keep common feature naming
# conventions (``protein.TP53``/``p53``) equivalent without fuzzy matching.
_GLIOMA_PROGRAM_MARKERS: Final[dict[str, frozenset[str]]] = {
    "RTK_PI3K_AKT_MTOR": frozenset(
        {"egfr", "pdgfra", "pik3ca", "pik3r1", "akt1", "akt2", "mtor", "pten", "nf1"}
    ),
    "P53_CELL_CYCLE": frozenset(
        {"tp53", "p53", "mdm2", "cdkn2a", "cdkn2b", "cdk4", "rb1", "chek2", "atrx"}
    ),
    "IDH_HIF1A": frozenset({"idh1", "idh2", "hif1a", "vhl", "epas1", "dnmt1"}),
    "MESENCHYMAL_PROGRAM": frozenset(
        {"nf1", "stat3", "cebpb", "tgfb1", "rela", "chi3l1", "fn1", "fibronectin"}
    ),
    "PROLIFERATION": frozenset(
        {"mki67", "pcna", "top2a", "mcm2", "mcm7", "ccnd1", "ccne1", "aurka"}
    ),
}
_GLIOMA_PROGRAM_EDGES: Final[tuple[tuple[str, str, float, float], ...]] = (
    ("RTK_PI3K_AKT_MTOR", "P53_CELL_CYCLE", -1.0, 0.35),
    ("RTK_PI3K_AKT_MTOR", "PROLIFERATION", 1.0, 0.45),
    ("IDH_HIF1A", "MESENCHYMAL_PROGRAM", -0.35, 0.30),
    ("MESENCHYMAL_PROGRAM", "PROLIFERATION", 0.5, 0.30),
)
_GLIOMA_PROGRAM_MIN_MARKERS: Final = 4
_GLIOMA_PROGRAM_MIN_PROGRAMS: Final = 2
# Some GBM drivers are biologically pleiotropic. Keep their disambiguation
# explicit instead of relying on dictionary or lexical ordering. NF1 loss is
# primarily a mesenchymal state marker in this abundance-effect model.
_GLIOMA_MARKER_PRIORITY: Final[dict[str, tuple[str, ...]]] = {
    "nf1": ("MESENCHYMAL_PROGRAM", "RTK_PI3K_AKT_MTOR"),
}
_COMPOUND_IDENTIFIER_PATTERN: Final = re.compile(
    r"[a-z0-9]+(?:[-_][a-z0-9]+)+"
)


def _identifier_tokens(value: str) -> frozenset[str]:
    """Return exact identifier tokens plus compact HGNC compound spellings."""

    normalized = value.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    tokens.update(
        compound.replace("-", "").replace("_", "")
        for compound in _COMPOUND_IDENTIFIER_PATTERN.findall(normalized)
    )
    return frozenset(tokens)


@dataclass(frozen=True, slots=True)
class _AbundanceFit:
    estimate: PosteriorEstimate
    iterations: int
    objective: float
    convergence_gap: float


@dataclass(frozen=True, slots=True)
class _GliomaProgramFit:
    estimates: tuple[PosteriorEstimate, ...]
    iterations: int
    objective: float
    convergence_gap: float
    marker_count: int
    program_count: int


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


def _uncertainty(*, glioma_program: bool = False) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "The coupled glioma program lane emits deterministic analytic intervals; "
            "external calibration is not claimed."
            if glioma_program
            else "M06-04 calibration and uncertainty decomposition are not frozen; "
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
            (
                "Coupled program intervals are deterministic research intervals, not "
                "calibrated biological probabilities."
                if glioma_program
                else "Deterministic proxy intervals are not calibrated posterior intervals."
            ),
        ),
    )


def _limitations(*, glioma_program: bool = False) -> tuple[Limitation, ...]:
    if glioma_program:
        return (
            Limitation(
                code="glioma_program_research_only",
                statement=(
                    "The coupled RTK/PI3K/AKT/mTOR, p53/cell-cycle, IDH/HIF1A, "
                    "mesenchymal, and proliferation graph is a synthetic research model; "
                    "it is not a clinical classifier or calibrated biological posterior."
                ),
            ),
            Limitation(
                code="glioma_program_support_gate",
                statement=(
                    "At least four observed marker proteins spanning two programs are "
                    "required; missing, censored, and unsupported values never become "
                    "negative evidence."
                ),
            ),
            Limitation(
                code="caller_declared_evidence",
                statement=(
                    "Source artifacts, configuration, and controls are caller-declared; "
                    "issuer authority is not authenticated."
                ),
            ),
        )
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

    feature_tokens = _identifier_tokens(feature_id) - {
        "protein",
        "abundance",
        "feature",
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
        prior_tokens = _identifier_tokens(prior.prior_id)
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


def _glioma_marker_program(feature_id: str) -> str | None:
    """Map an exact feature token to the locked GBM program catalogue."""

    tokens = _identifier_tokens(feature_id) - {"protein", "abundance", "feature"}
    matches = tuple(
        program
        for program, markers in _GLIOMA_PROGRAM_MARKERS.items()
        if tokens & markers
    )
    if not matches:
        return None
    for token in sorted(tokens):
        preferred = _GLIOMA_MARKER_PRIORITY.get(token)
        if preferred:
            for program in preferred:
                if program in matches:
                    return program
    # Non-ambiguous markers retain their catalogue order; the explicit
    # priority table above owns every known overlap.
    return next(program for program in _GLIOMA_PROGRAM_MARKERS if program in matches)


def _glioma_numeric_observations(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[tuple[str, str, float, float, FormalStateFeatureValue], ...]:
    observations: list[tuple[str, str, float, float, FormalStateFeatureValue]] = []
    for value in sorted(request.feature_values, key=lambda item: item.feature_id):
        program = _glioma_marker_program(value.feature_id)
        if program is None or value.state is not FormalStateMissingness.OBSERVED:
            continue
        scalar = value.scalar_value
        if scalar is not None and isfinite(scalar):
            observations.append((value.feature_id, program, scalar, 0.25, value))
            continue
        lower, upper = value.interval_lower, value.interval_upper
        if lower is None or upper is None or not all(isfinite(item) for item in (lower, upper)):
            continue
        observations.append(
            (
                value.feature_id,
                program,
                (lower + upper) / 2.0,
                max(0.01, (upper - lower) / (2.0 * _POSTERIOR_Z90)),
                value,
            )
        )
    return tuple(observations)


def _glioma_program_objective(
    states: Mapping[str, float],
    observations: tuple[tuple[str, str, float, float, FormalStateFeatureValue], ...],
    prior_means: Mapping[str, float],
    prior_sds: Mapping[str, float],
) -> float:
    objective = 0.0
    for _feature_id, program, observed, assay_sd, _value in observations:
        standardized = abs(observed - states[program]) / assay_sd
        data_loss = (
            0.5 * standardized * standardized
            if standardized <= _HUBER_K
            else _HUBER_K * standardized - 0.5 * _HUBER_K * _HUBER_K
        )
        objective += data_loss
    for program, state in states.items():
        objective += 0.5 * (state - prior_means[program]) ** 2 / (prior_sds[program] ** 2)
    for source, target, sign, weight in _GLIOMA_PROGRAM_EDGES:
        objective += weight * (states[target] - sign * states[source]) ** 2
    return objective


def _fit_glioma_program_graph(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> _GliomaProgramFit | None:
    """Fit coupled GBM programs with robust coordinate descent and signed edges."""

    observations = _glioma_numeric_observations(request)
    observed_programs = tuple(sorted({item[1] for item in observations}))
    if (
        len(observations) < _GLIOMA_PROGRAM_MIN_MARKERS
        or len(observed_programs) < _GLIOMA_PROGRAM_MIN_PROGRAMS
    ):
        return None
    # Keep unobserved programs in the latent graph so signed edges can carry
    # prior information without inventing observations for those programs.
    programs = tuple(sorted(_GLIOMA_PROGRAM_MARKERS))
    prior_means: dict[str, float] = {}
    prior_sds: dict[str, float] = {}
    for program in programs:
        mean, scale, _ = _prior_for_feature(request, f"program.{program.casefold()}")
        prior_means[program] = mean
        prior_sds[program] = max(0.05, scale)
    states = {program: prior_means[program] for program in programs}
    robust_weights = [1.0] * len(observations)
    damping = 0.68
    convergence_gap = float("inf")
    objective = _glioma_program_objective(states, observations, prior_means, prior_sds)
    if not isfinite(objective):
        return None
    iterations = 0
    max_iterations = min(request.configuration.max_iterations, _MAX_IRLS_ITERATIONS)
    for iteration in range(max_iterations):
        iterations = iteration + 1
        previous = dict(states)
        previous_objective = objective
        for index, (_feature_id, program, observed, assay_sd, _value) in enumerate(observations):
            residual = (observed - previous[program]) / assay_sd
            robust_weights[index] = min(1.0, _HUBER_K / max(1.0, abs(residual)))
        proposals = dict(previous)
        for program in programs:
            prior_precision = 1.0 / (prior_sds[program] * prior_sds[program])
            numerator = prior_precision * prior_means[program]
            denominator = prior_precision
            for index, (_feature_id, observed_program, observed, assay_sd, _value) in enumerate(
                observations
            ):
                if observed_program != program:
                    continue
                precision = robust_weights[index] / (assay_sd * assay_sd)
                numerator += precision * observed
                denominator += precision
            for source, target, sign, weight in _GLIOMA_PROGRAM_EDGES:
                if source == program and target in states:
                    numerator += weight * sign * previous[target]
                    denominator += weight
                elif target == program and source in states:
                    numerator += weight * sign * previous[source]
                    denominator += weight
            candidate = numerator / denominator
            # Program coordinates are standardized abundance effects.  A loose
            # bound prevents one extreme assay from destabilizing the graph.
            candidate = max(-12.0, min(12.0, candidate))
            proposals[program] = damping * candidate + (1.0 - damping) * previous[program]
        objective = _glioma_program_objective(proposals, observations, prior_means, prior_sds)
        accepted = proposals
        if not isfinite(objective) or objective > previous_objective + _GLIOMA_OBJECTIVE_TOLERANCE:
            accepted = previous.copy()
            objective = previous_objective
            delta = {
                program: proposals[program] - previous[program] for program in programs
            }
            step = damping
            for _ in range(_GLIOMA_BACKTRACKING_STEPS):
                step *= _GLIOMA_BACKTRACKING_FACTOR
                trial = {
                    program: previous[program] + step * delta[program] for program in programs
                }
                trial_objective = _glioma_program_objective(
                    trial, observations, prior_means, prior_sds
                )
                if isfinite(trial_objective) and (
                    trial_objective <= previous_objective + _GLIOMA_OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    objective = trial_objective
                    break
            else:
                return None
        states = accepted
        convergence_gap = max(abs(states[name] - previous[name]) for name in programs)
        if (
            convergence_gap <= _IRLS_TOLERANCE
            and abs(previous_objective - objective) <= _GLIOMA_OBJECTIVE_TOLERANCE
        ):
            break
    if not all(isfinite(value) for value in (*states.values(), objective, convergence_gap)):
        return None
    definitions = {item.feature_id: item for item in request.state_schema.features}
    estimates: list[PosteriorEstimate] = []
    for feature_id, program, observed, assay_sd, value in observations:
        _prior_mean, prior_sd, _ = _prior_for_feature(request, feature_id)
        data_precision = robust_weights[
            next(index for index, item in enumerate(observations) if item[0] == feature_id)
        ] / (assay_sd * assay_sd)
        network_precision = sum(
            weight
            for source, target, _sign, weight in _GLIOMA_PROGRAM_EDGES
            if program in (source, target)
        )
        posterior_sd = sqrt(
            1.0
            / max(1e-8, data_precision + network_precision + 1.0 / (prior_sd**2))
        )
        center = 0.70 * states[program] + 0.30 * observed
        bounds = _abundance_bounds(request, feature_id)
        if bounds is None:
            return None
        lower = center - _POSTERIOR_Z90 * posterior_sd
        upper = center + _POSTERIOR_Z90 * posterior_sd
        if bounds[0] is not None:
            center, lower = max(bounds[0], center), max(bounds[0], lower)
        if bounds[1] is not None:
            center, upper = min(bounds[1], center), min(bounds[1], upper)
        if lower > upper or not all(isfinite(item) for item in (center, lower, upper)):
            return None
        estimates.append(
            PosteriorEstimate(
                feature_id=feature_id,
                kind=PosteriorEstimateKind.INTERVAL,
                unit=definitions[feature_id].unit,
                estimate_value=round(center, 8),
                lower_bound=round(lower, 8),
                upper_bound=round(upper, 8),
                posterior_mass=0.9,
                evidence=value.evidence,
            )
        )
    return _GliomaProgramFit(
        estimates=tuple(estimates),
        iterations=iterations,
        objective=round(objective, 8),
        convergence_gap=round(convergence_gap, 8),
        marker_count=len(observations),
        program_count=len(observed_programs),
    )


def _support(status: ProbabilisticResultStatus, reason: str) -> SupportDecision:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code=(
                "provisional_glioma_program_estimate"
                if "coupled GBM" in reason
                else "provisional_proxy_estimate"
            ),
            rationale=(
                "All declared controls passed and the locked estimator accepted the "
                "observed numeric representation."
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
    diagnostic_id: str | None = None,
) -> OptimizationDiagnostic:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return OptimizationDiagnostic(
            diagnostic_id=diagnostic_id or "diagnostic.m0604.proxy",
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
            in {
                M0604_PROXY_OPTIMIZER,
                M0604_GLIOMA_IRLS_OPTIMIZER,
                M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER,
            }
        ):
            if canonical.configuration.optimizer == M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER:
                fitted_program = _fit_glioma_program_graph(canonical)
                if fitted_program is not None:
                    estimates = fitted_program.estimates
                    diagnostic_iterations = fitted_program.iterations
                    diagnostic_objective = fitted_program.objective
                    diagnostic_gap = fitted_program.convergence_gap
                    reason = (
                        "Locked coupled GBM abundance program IRLS converged over "
                        f"{fitted_program.marker_count} markers and "
                        f"{fitted_program.program_count} signed programs."
                    )
                else:
                    reason = (
                        "The coupled GBM abundance graph abstained: at least four observed "
                        "marker proteins spanning two programs are required."
                    )
            elif canonical.configuration.optimizer == M0604_GLIOMA_IRLS_OPTIMIZER:
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
            diagnostic_id=(
                "diagnostic.m0604.glioma_program"
                if canonical.configuration.optimizer == M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER
                and status is ProbabilisticResultStatus.ESTIMATED
                else None
            ),
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
            uncertainty=_uncertainty(
                glioma_program=(
                    canonical.configuration.optimizer == M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER
                )
            ),
            provenance=_provenance(canonical, request_hash),
            evidence=_evidence(canonical),
            limitations=_limitations(
                glioma_program=(
                    canonical.configuration.optimizer == M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER
                )
            ),
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
    "M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER",
    "M0604_PROXY_OPTIMIZER",
    "M0604ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "estimate_protein_abundance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
