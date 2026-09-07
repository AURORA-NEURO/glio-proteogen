"""Deterministic, replay-bound M15-03 mechanistic feature construction."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_03 import (
    M1503_CONTRACT_VERSION,
    M1503_MAX_EFFECT,
    M1503_PARENT,
    ComplexActivityMechanisticFeatureResult,
    ConstructComplexActivityMechanisticFeaturesRequest,
    FeatureConstructorStatus,
    FeatureFinding,
    FeatureFindingCode,
    FeatureKind,
    FeatureSupportStatus,
    GliomaFeatureProgram,
    MechanisticEvidenceState,
    MechanisticFeature,
    MechanisticFeatureObject,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m15_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructComplexActivityMechanisticFeaturesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityMechanisticFeatureResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset(
    {
        "curated_rule",
        "enrichment",
        "mechanistic_baseline",
        "orthogonal_consensus",
        "bayesian_graph",
        "state_space",
        "mechanistic_model",
        "foundation_assisted",
    }
)
_ALLOWED_UNITS: Final = frozenset(
    {
        "dimensionless",
        "fraction",
        "activity",
        "abundance",
        "rate",
        "score",
        "state_probability",
        "spatial_index",
        "timepoint",
    }
)
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_EDGE_STRENGTH: Final = 0.45
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_PROGRAM_ORDER: Final = tuple(GliomaFeatureProgram)
_PROGRAM_EDGES: Final = (
    (GliomaFeatureProgram.RTK_PI3K_AKT_MTOR, GliomaFeatureProgram.PROLIFERATION, 1.0),
    (GliomaFeatureProgram.P53_CELL_CYCLE, GliomaFeatureProgram.PROLIFERATION, -1.0),
    (GliomaFeatureProgram.IDH_HIF1A, GliomaFeatureProgram.MESENCHYMAL_PROGRAM, -1.0),
    (GliomaFeatureProgram.RTK_PI3K_AKT_MTOR, GliomaFeatureProgram.MESENCHYMAL_PROGRAM, 1.0),
    (GliomaFeatureProgram.MESENCHYMAL_PROGRAM, GliomaFeatureProgram.PROLIFERATION, 1.0),
)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    feature_id: str
    program: GliomaFeatureProgram
    state: MechanisticEvidenceState
    effect: float
    standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _TypedFit:
    values: tuple[float, ...]
    converged: bool
    iterations: int
    objective: float
    max_update: float
    objective_trace: tuple[float, ...]


class M1503AuthorizationError(PermissionError):
    """Caller controls do not authorize feature construction."""

    def __init__(self) -> None:
        super().__init__(
            "M15-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1503ReplayVerificationError(ValueError):
    """A feature result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-03 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1503_authorization(candidate: object) -> None:
    """Check all seven controls before typed traversal of feature material."""

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
    except Exception:  # noqa: BLE001
        raise M1503AuthorizationError from None
    if states != expected:
        raise M1503AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1503_authorization(candidate)
    return candidate


def _evidence(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.longitudinal_recurrence_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        request.policy.configuration.units_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    for feature in request.candidate_features:
        artifacts.extend(feature.source_artifacts)
        artifacts.extend(item.reference for item in feature.evidence)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared mechanistic feature evidence; issuer authority is not "
                "authenticated."
            ),
        )
        for artifact in tuple(unique.values())[:64]
    )


def _failure(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
    *,
    code: FeatureFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[FeatureFinding, ...]:
    return (
        FeatureFinding(
            finding_id=f"finding.{request.request_id}",
            code=code,
            message=message,
            evidence=evidence,
        ),
    )


def _evaluate_features(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
) -> tuple[bool, FeatureFindingCode | None, str | None]:
    method = request.policy.configuration.method
    if method not in _SUPPORTED_METHODS:
        return (
            False,
            FeatureFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
            "Feature construction method is outside the closed provisional support domain.",
        )
    if any(feature.unit not in _ALLOWED_UNITS for feature in request.candidate_features):
        return (
            False,
            FeatureFindingCode.UNIT_INVARIANT_FAILED,
            "Every mechanistic feature unit must be in the locked unit domain.",
        )
    if any(
        feature.support_status
        in {
            FeatureSupportStatus.CONFLICTED,
            FeatureSupportStatus.UNRESOLVED,
            FeatureSupportStatus.ABSTAINED,
        }
        for feature in request.candidate_features
    ):
        return (
            False,
            FeatureFindingCode.UPSTREAM_UNSUPPORTED,
            "Unresolved or abstained feature evidence requires safe abstention.",
        )
    if (
        request.policy.configuration.model_dump(mode="python").get("topology_invariants_required")
        is not True
    ):
        return (
            False,
            FeatureFindingCode.TOPOLOGY_INVARIANT_FAILED,
            "Topology invariant was not required.",
        )
    if (
        request.policy.configuration.model_dump(mode="python").get(
            "perturbation_invariants_required"
        )
        is not True
    ):
        return (
            False,
            FeatureFindingCode.PERTURBATION_INVARIANT_FAILED,
            "Perturbation invariant was not required.",
        )
    return True, None, None


def _has_typed_features(features: tuple[MechanisticFeature, ...]) -> bool:
    return any(
        feature.program is not None
        or feature.evidence_state is not None
        or feature.standard_error is not None
        for feature in features
    )


def _typed_terms(features: tuple[MechanisticFeature, ...]) -> tuple[_TypedTerm, ...]:
    active = {
        MechanisticEvidenceState.OBSERVED,
        MechanisticEvidenceState.LEFT_CENSORED,
    }
    terms: list[_TypedTerm] = []
    for feature in features:
        if (
            feature.program is None
            or feature.evidence_state not in active
            or feature.standard_error is None
            or feature.numeric_value is None
        ):
            continue
        terms.append(
            _TypedTerm(
                feature_id=feature.feature_id,
                program=feature.program,
                state=feature.evidence_state,
                effect=max(-M1503_MAX_EFFECT, min(M1503_MAX_EFFECT, feature.numeric_value)),
                standard_error=feature.standard_error,
                quality_weight=feature.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.feature_id)))


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    return 1.0 if absolute <= _HUBER_DELTA else _HUBER_DELTA / absolute


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    return (
        0.5 * residual * residual
        if absolute <= _HUBER_DELTA
        else _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)
    )


def _typed_objective(
    values: list[float], terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        residual = (
            max(0.0, values[index[term.program]] - term.effect)
            if term.state is MechanisticEvidenceState.LEFT_CENSORED
            else values[index[term.program]] - term.effect
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    if include_edges:
        for source, target, sign in _PROGRAM_EDGES:
            residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
            objective += _huber_loss(residual)
    return objective


def _fit_typed(  # noqa: C901 - explicit coordinate updates keep signed edges auditable.
    terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaFeatureProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = [0.0] * len(_PROGRAM_ORDER)
    for program, program_terms in grouped.items():
        values[index[program]] = sum(
            term.quality_weight * term.effect for term in program_terms
        ) / max(_MIN_SCALE, sum(term.quality_weight for term in program_terms))
    previous = _typed_objective(values, terms, include_edges=include_edges)
    trace = [_quantize(previous)]
    converged = False
    max_update = math.inf
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = values.copy()
        for position, program in enumerate(_PROGRAM_ORDER):
            current = values[position]
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for term in grouped.get(program, ()):
                if (
                    term.state is MechanisticEvidenceState.LEFT_CENSORED
                    and current <= term.effect
                ):
                    continue
                residual = (
                    max(0.0, current - term.effect)
                    if term.state is MechanisticEvidenceState.LEFT_CENSORED
                    else current - term.effect
                ) / max(_MIN_SCALE, term.standard_error)
                information = (
                    term.quality_weight
                    * _huber_weight(residual)
                    / max(_MIN_SCALE, term.standard_error**2)
                )
                gradient += information * (current - term.effect)
                hessian += information
            if include_edges:
                for source, target, sign in _PROGRAM_EDGES:
                    if program is source:
                        residual = values[index[target]] - sign * _EDGE_STRENGTH * current
                        gradient += -sign * _EDGE_STRENGTH * _huber_weight(residual) * residual
                        hessian += _EDGE_STRENGTH**2
                    elif program is target:
                        residual = current - sign * _EDGE_STRENGTH * values[index[source]]
                        gradient += _huber_weight(residual) * residual
                        hessian += 1.0
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            values[position] = max(
                -M1503_MAX_EFFECT,
                min(M1503_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        objective = _typed_objective(values, terms, include_edges=include_edges)
        trace.append(_quantize(objective))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            previous = objective
            break
        previous = objective
    return _TypedFit(
        values=tuple(_quantize(value) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(previous),
        max_update=_quantize(max_update if math.isfinite(max_update) else 0.0),
        objective_trace=tuple(trace),
    )


def _hash_uniform(material: str) -> float:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)


def _hash_normal(material: str) -> float:
    first = max(_MIN_SCALE, _hash_uniform(material + ":u1"))
    second = _hash_uniform(material + ":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _typed_trace_digest(fit: _TypedFit) -> str:
    material = ",".join(str(value) for value in fit.objective_trace)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _typed_feature_outputs(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
    *,
    evidence: tuple[EvidenceReference, ...],
    request_digest: str,
) -> tuple[tuple[MechanisticFeature, ...], _TypedFit]:
    terms = _typed_terms(request.candidate_features)
    if not terms:
        raise ValueError("typed feature construction requires observed or left-censored evidence")  # noqa: TRY003
    fit = _fit_typed(terms)
    if not fit.converged:
        raise ValueError("typed feature solver did not converge")  # noqa: TRY003
    topology_free = _fit_typed(terms, include_edges=False)
    if not topology_free.converged:
        raise ValueError("typed feature topology ablation did not converge")  # noqa: TRY003
    draws: list[tuple[float, ...]] = []
    for draw in range(request.policy.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
                feature_id=term.feature_id,
                program=term.program,
                state=term.state,
                effect=max(
                    -M1503_MAX_EFFECT,
                    min(
                        M1503_MAX_EFFECT,
                        term.effect
                        + 0.5
                        * term.standard_error
                        * _hash_normal(f"{request_digest}:{draw}:{term.feature_id}"),
                    ),
                ),
                standard_error=term.standard_error,
                quality_weight=term.quality_weight,
            )
            for term in terms
        )
        draw_fit = _fit_typed(perturbed)
        if not draw_fit.converged:
            raise ValueError("typed feature bootstrap solver did not converge")  # noqa: TRY003
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaFeatureProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    drivers = tuple(
        program.value
        for program, value in sorted(
            zip(_PROGRAM_ORDER, fit.values, strict=True),
            key=lambda pair: (-abs(pair[1]), pair[0].value),
        )[:3]
    )
    derived: list[MechanisticFeature] = []
    for program in _PROGRAM_ORDER:
        position = index[program]
        samples = tuple(draw[position] for draw in draws)
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        width = max(_MIN_SCALE, upper - lower)
        topology_delta = fit.values[position] - topology_free.values[position]
        direct = grouped.get(program, ())
        quality = sum(item.quality_weight for item in direct) / max(1, len(direct))
        derived.append(
            MechanisticFeature(
                feature_id=f"feature.derived.{program.value.lower()}",
                kind=FeatureKind.PATHWAY,
                label=f"derived {program.value.replace('_', ' ').lower()} activity",
                value=f"{fit.values[position]:.8f}",
                numeric_value=fit.values[position],
                unit="activity",
                support_status=FeatureSupportStatus.SUPPORTED,
                source_artifacts=(request.policy.configuration.model_reference,),
                evidence=evidence,
                program=program,
                evidence_state=MechanisticEvidenceState.OBSERVED,
                standard_error=max(_MIN_SCALE, width / 3.0),
                quality_weight=max(_MIN_SCALE, min(1.0, quality)),
                lower_bound=lower,
                upper_bound=upper,
                stability=_quantize(max(0.0, min(1.0, 1.0 - width / (2.0 * M1503_MAX_EFFECT)))),
                discordance=_quantize(min(1.0, abs(topology_delta))),
                evidence_count=len(direct),
                top_drivers=drivers,
                ablation_effects=(
                    f"signed_network_edges_removed:{_quantize(topology_delta):.8f}",
                    f"measurement_weight:{_quantize(quality):.8f}",
                ),
            )
        )
    return (*request.candidate_features, *derived), fit


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_features",
            statement=(
                "Feature values and source artifacts are caller-declared and not externally "
                "authenticated."
            ),
        ),
        Limitation(
            code="invariant_scope",
            statement=(
                "Unit, topology, and perturbation flags are deterministic gates, not "
                "biological validation."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "No mechanistic feature object is published outside the closed support domain."
                ),
            )
        )
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_feature_network",
                    statement=(
                        "Typed feature effects are fitted over signed glioma program edges "
                        "with robust coordinate descent and deterministic bootstrap intervals."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Derived program features are research-use-only and are not causal, "
                        "clinical, prognostic, or treatment claims."
                    ),
                ),
            )
        )
    return tuple(values)


class M1503FeatureConstructorEngine:
    """Construct a deterministic feature object with replay and safe abstention."""

    __slots__ = ()

    def infer(self, request: object) -> ComplexActivityMechanisticFeatureResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: ConstructComplexActivityMechanisticFeaturesRequest
    ) -> ComplexActivityMechanisticFeatureResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, failure_code, failure_message = _evaluate_features(request)
        typed_model = _has_typed_features(request.candidate_features)
        typed_fit: _TypedFit | None = None
        output_features = request.candidate_features
        if supported and typed_model:
            try:
                output_features, typed_fit = _typed_feature_outputs(
                    request, evidence=evidence, request_digest=request_hash
                )
            except ValueError as error:
                supported = False
                failure_code = FeatureFindingCode.UPSTREAM_UNSUPPORTED
                failure_message = str(error)
        findings = (
            ()
            if supported
            else _failure(
                request,
                code=failure_code or FeatureFindingCode.UPSTREAM_UNSUPPORTED,
                message=failure_message
                or "Mechanistic feature construction was not safely evaluable.",
                evidence=evidence,
            )
        )
        feature_object = (
            MechanisticFeatureObject(
                feature_object_id=f"feature-object.{request_hash.removeprefix('sha256:')}",
                version=request.policy.configuration.version,
                features=output_features,
                material_assumptions=(
                    "Caller-declared feature values are preserved without external content "
                    "traversal.",
                    "Topology and perturbation invariants are deterministic release gates.",
                ),
                locked_reference=request.policy.configuration.model_reference,
                evidence=evidence,
                typed_model=typed_model,
                solver_iterations=typed_fit.iterations if typed_fit is not None else None,
                solver_objective=typed_fit.objective if typed_fit is not None else None,
                solver_max_update=typed_fit.max_update if typed_fit is not None else None,
                objective_trace_digest=(
                    _typed_trace_digest(typed_fit) if typed_fit is not None else None
                ),
            )
            if supported
            else None
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_mechanistic_features",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1503_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": FeatureConstructorStatus.CONSTRUCTED
            if supported
            else FeatureConstructorStatus.ABSTAINED,
            "feature_object": feature_object,
            "findings": findings,
            "abstention_reason": None
            if supported
            else (failure_message or "Mechanistic feature construction was not safely evaluable."),
            "parent_target": M1503_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1503_features_constructed"
                if supported
                else "m1503_features_abstained",
                rationale=(
                    "Units, topology, perturbation, parent binding, and source evidence are closed."
                    if supported
                    else "The feature request is outside the safely constructed support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported, typed=typed_model),
            "human_review_required": not supported,
        }
        constructed = ComplexActivityMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanisticFeatureResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1503ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1503ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1503ReplayVerificationError
        return validated


def construct_complex_activity_mechanistic_features(
    request: object,
) -> ComplexActivityMechanisticFeatureResult:
    """Public provisional M15-03 operation."""

    return M1503FeatureConstructorEngine().infer(request)


__all__ = [
    "M1503AuthorizationError",
    "M1503FeatureConstructorEngine",
    "M1503ReplayVerificationError",
    "construct_complex_activity_mechanistic_features",
    "preflight_m1503_authorization",
]
