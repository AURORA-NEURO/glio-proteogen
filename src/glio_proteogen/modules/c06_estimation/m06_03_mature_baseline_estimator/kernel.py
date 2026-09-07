"""Transparent deterministic kernel for the provisional M06-03 estimator."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from glio_proteogen.contracts.m06_01 import FormalStateFeatureValue, FormalStateMissingness
from glio_proteogen.contracts.m06_03 import (
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    EstimateProteinAbundanceBaselineRequest,
    GliomaBaselineProgram,
    GliomaProgramBaselineState,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from glio_proteogen.kernel.models import EvidenceReference


@dataclass(frozen=True, slots=True)
class BaselineKernelOutput:
    estimates: tuple[BaselineEstimate, ...]
    diagnostics: tuple[BaselineDiagnostic, ...]
    abstention_reason: str | None


@dataclass(frozen=True, slots=True)
class GliomaBaselineOutput:
    """Typed glioma program states plus diagnostics and safe-abstention reason."""

    states: tuple[GliomaProgramBaselineState, ...]
    diagnostics: tuple[BaselineDiagnostic, ...]
    abstention_reason: str | None


@dataclass(frozen=True, slots=True)
class _Observation:
    feature_id: str
    program: GliomaBaselineProgram
    direction: int
    value: float
    standard_error: float
    quality_weight: float
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class _Fit:
    values: tuple[float, ...]
    objective: float
    converged: bool


_PROGRAM_ORDER: Final = tuple(GliomaBaselineProgram)
_PROGRAM_EDGES: Final = (
    (GliomaBaselineProgram.RTK_PI3K_AKT_MTOR, GliomaBaselineProgram.PROLIFERATION, 1.0),
    (GliomaBaselineProgram.P53_CELL_CYCLE, GliomaBaselineProgram.PROLIFERATION, -1.0),
    (GliomaBaselineProgram.IDH_HIF1A, GliomaBaselineProgram.MESENCHYMAL_PROGRAM, -1.0),
    (GliomaBaselineProgram.RTK_PI3K_AKT_MTOR, GliomaBaselineProgram.MESENCHYMAL_PROGRAM, 1.0),
    (GliomaBaselineProgram.MESENCHYMAL_PROGRAM, GliomaBaselineProgram.PROLIFERATION, 1.0),
)
_EDGE_STRENGTH: Final = 0.35
_RIDGE: Final = 0.03
_DAMPING: Final = 0.7
_HUBER_DELTA: Final = 1.5
_SOLVER_TOLERANCE: Final = 1e-5
_SOLVER_ITERATIONS: Final = 120
_MIN_SCALE: Final = 1e-6
_ZSCORE_LIMIT: Final = 4.0
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95


class M0603BaselineKernel:
    """Run only caller-declared preprocessing and transparent value reduction."""

    def estimate(self, request: EstimateProteinAbundanceBaselineRequest) -> BaselineKernelOutput:
        definitions = {item.feature_id: item for item in request.state_schema.features}
        estimates: list[BaselineEstimate] = []
        diagnostics: list[BaselineDiagnostic] = []
        for value in request.feature_values:
            definition = definitions[value.feature_id]
            if value.state is not FormalStateMissingness.OBSERVED:
                diagnostics.append(
                    BaselineDiagnostic(
                        diagnostic_id=f"diagnostic.{value.feature_id}",
                        status=BaselineDiagnosticStatus.NOT_EVALUABLE,
                        message="Feature is not observed; baseline estimation abstains.",
                        metric_name="missingness",
                    )
                )
                return BaselineKernelOutput(
                    estimates=(),
                    diagnostics=tuple(diagnostics),
                    abstention_reason="formal-state feature is missing or unsupported",
                )
            if definition.value_kind.value == "scalar":
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.SCALAR,
                        unit=value.unit,
                        estimate_value=value.scalar_value,
                    )
                )
            elif definition.value_kind.value == "interval":
                if value.interval_lower is None or value.interval_upper is None:
                    return BaselineKernelOutput(
                        estimates=(),
                        diagnostics=tuple(diagnostics),
                        abstention_reason="interval feature lacks ordered bounds",
                    )
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.INTERVAL,
                        unit=value.unit,
                        estimate_value=(value.interval_lower + value.interval_upper) / 2,
                        lower_bound=value.interval_lower,
                        upper_bound=value.interval_upper,
                    )
                )
            else:
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.CATEGORICAL,
                        unit=value.unit,
                        category=value.category,
                    )
                )
            diagnostics.append(
                BaselineDiagnostic(
                    diagnostic_id=f"diagnostic.{value.feature_id}",
                    status=BaselineDiagnosticStatus.PASS,
                    message=(
                        "Transparent baseline reduction completed with "
                        f"{request.configuration.estimator_family.value} family."
                    ),
                    metric_name="feature_observed",
                    metric_value=1.0,
                )
            )
        return BaselineKernelOutput(
            estimates=tuple(estimates),
            diagnostics=tuple(diagnostics),
            abstention_reason=None,
        )

    def estimate_typed(
        self,
        request: EstimateProteinAbundanceBaselineRequest,
        request_digest: str,
    ) -> GliomaBaselineOutput:
        """Fit normalized glioma programs from explicitly annotated state values."""

        observations, reason = _observations(request)
        if reason is not None:
            return GliomaBaselineOutput(states=(), diagnostics=(), abstention_reason=reason)
        if not observations:
            return GliomaBaselineOutput(
                states=(),
                diagnostics=(),
                abstention_reason=(
                    "typed glioma baseline requires observed scalar or interval evidence"
                ),
            )
        center, scale = _robust_location_scale(observation.value for observation in observations)
        fit = _fit(observations, center, scale)
        if not fit.converged:
            return GliomaBaselineOutput(
                states=(),
                diagnostics=(),
                abstention_reason="typed glioma baseline solver did not converge",
            )
        topology_free = _fit(observations, center, scale, include_edges=False)
        if not topology_free.converged:
            return GliomaBaselineOutput(
                states=(),
                diagnostics=(),
                abstention_reason="typed glioma baseline topology ablation did not converge",
            )
        draws = _bootstrap_draws(request, observations, request_digest)
        if draws is None:
            return GliomaBaselineOutput(
                states=(),
                diagnostics=(),
                abstention_reason="typed glioma baseline bootstrap did not converge",
            )
        index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
        present = tuple(
            sorted({item.program for item in observations}, key=lambda item: item.value)
        )
        states: list[GliomaProgramBaselineState] = []
        diagnostics: list[BaselineDiagnostic] = []
        for program in present:
            position = index[program]
            samples = tuple(item[position] for item in draws)
            lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
            upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
            program_observations = tuple(item for item in observations if item.program is program)
            drivers = _drivers(program_observations, center, scale)
            direct_without = _fit(
                tuple(item for item in observations if item.program is not program),
                center,
                scale,
            )
            direct_delta = fit.values[position] - direct_without.values[position]
            topology_delta = fit.values[position] - topology_free.values[position]
            evidence = tuple(
                item
                for observation in program_observations
                for item in observation.evidence
                if hasattr(item, "reference")
            )[:32]
            states.append(
                GliomaProgramBaselineState(
                    program=program,
                    score=fit.values[position],
                    lower_bound=lower,
                    upper_bound=upper,
                    stability=_quantize(
                        max(0.0, min(1.0, 1.0 - (upper - lower) / (2.0 * _ZSCORE_LIMIT)))
                    ),
                    discordance=_quantize(
                        min(1.0, (abs(direct_delta) + abs(topology_delta)) / 2.0)
                    ),
                    evidence_count=len(program_observations),
                    top_drivers=drivers,
                    ablation_effects=(
                        f"feature_ablation:{_quantize(direct_delta):.8f}",
                        f"signed_program_edges_removed:{_quantize(topology_delta):.8f}",
                    ),
                    evidence=evidence,
                )
            )
            diagnostics.append(
                BaselineDiagnostic(
                    diagnostic_id=f"diagnostic.glioma.{program.value}",
                    status=BaselineDiagnosticStatus.PASS,
                    message=(
                        "Robust median/MAD normalization and signed program graph fit completed."
                    ),
                    metric_name="program_score",
                    metric_value=fit.values[position],
                    evidence=evidence,
                )
            )
        return GliomaBaselineOutput(
            states=tuple(states), diagnostics=tuple(diagnostics), abstention_reason=None
        )


def _observations(
    request: EstimateProteinAbundanceBaselineRequest,
) -> tuple[tuple[_Observation, ...], str | None]:
    values = {item.feature_id: item for item in request.feature_values}
    observations: list[_Observation] = []
    for annotation in sorted(
        request.configuration.glioma_annotations, key=lambda item: item.feature_id
    ):
        value = values[annotation.feature_id]
        if value.state is not FormalStateMissingness.OBSERVED:
            continue
        numeric, interval_error = _numeric_value(value)
        if numeric is None:
            continue
        standard_error = max(annotation.standard_error, interval_error or 0.0, _MIN_SCALE)
        if not math.isfinite(numeric) or not math.isfinite(standard_error):
            return (), "typed glioma baseline contains non-finite evidence"
        observations.append(
            _Observation(
                feature_id=annotation.feature_id,
                program=annotation.program,
                direction=annotation.direction,
                value=numeric,
                standard_error=standard_error,
                quality_weight=annotation.quality_weight,
                evidence=(*annotation.evidence, *value.evidence),
            )
        )
    return tuple(observations), None


def _numeric_value(value: FormalStateFeatureValue) -> tuple[float | None, float | None]:
    if value.scalar_value is not None:
        return value.scalar_value, None
    if value.interval_lower is not None and value.interval_upper is not None:
        return (
            (value.interval_lower + value.interval_upper) / 2.0,
            (value.interval_upper - value.interval_lower) / 2.0,
        )
    return None, None


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _robust_location_scale(values: Iterable[float]) -> tuple[float, float]:
    material = tuple(float(value) for value in values)
    center = _median(material)
    mad = _median(tuple(abs(value - center) for value in material))
    return center, max(_MIN_SCALE, 1.4826 * mad if mad > _MIN_SCALE else 1.0)


def _zscore(value: float, center: float, scale: float) -> float:
    return max(-_ZSCORE_LIMIT, min(_ZSCORE_LIMIT, (value - center) / scale))


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    return 1.0 if absolute <= _HUBER_DELTA else _HUBER_DELTA / absolute


def _objective(
    values: list[float],
    observations: tuple[_Observation, ...],
    center: float,
    scale: float,
    *,
    include_edges: bool,
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for observation in observations:
        target = observation.direction * _zscore(observation.value, center, scale)
        residual = values[index[observation.program]] - target
        scaled = residual / max(_MIN_SCALE, observation.standard_error / scale)
        absolute = abs(scaled)
        loss = 0.5 * scaled * scaled if absolute <= _HUBER_DELTA else _HUBER_DELTA * (
            absolute - 0.5 * _HUBER_DELTA
        )
        objective += observation.quality_weight * loss
    if include_edges:
        for edge_source, edge_target, sign in _PROGRAM_EDGES:
            residual = (
                values[index[edge_target]]
                - sign * _EDGE_STRENGTH * values[index[edge_source]]
            )
            objective += 0.5 * residual * residual
    return objective


def _fit(  # noqa: C901 - explicit coordinate updates keep the signed graph auditable.
    observations: tuple[_Observation, ...],
    center: float,
    scale: float,
    *,
    include_edges: bool = True,
) -> _Fit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaBaselineProgram, list[_Observation]] = {
        program: [] for program in _PROGRAM_ORDER
    }
    for observation in observations:
        grouped[observation.program].append(observation)
    values = [0.0] * len(_PROGRAM_ORDER)
    for program, items in grouped.items():
        if items:
            weights = tuple(item.quality_weight for item in items)
            values[index[program]] = sum(
                weight * item.direction * _zscore(item.value, center, scale)
                for weight, item in zip(weights, items, strict=True)
            ) / max(_MIN_SCALE, sum(weights))
    previous = _objective(values, observations, center, scale, include_edges=include_edges)
    converged = False
    for _ in range(_SOLVER_ITERATIONS):
        old = values.copy()
        for position, program in enumerate(_PROGRAM_ORDER):
            current = values[position]
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for observation in grouped[program]:
                target = observation.direction * _zscore(observation.value, center, scale)
                residual = (current - target) / max(
                    _MIN_SCALE, observation.standard_error / scale
                )
                information = observation.quality_weight * _huber_weight(residual) / max(
                    _MIN_SCALE, (observation.standard_error / scale) ** 2
                )
                gradient += information * (current - target)
                hessian += information
            if include_edges:
                for edge_source, edge_target, sign in _PROGRAM_EDGES:
                    if program is edge_source:
                        residual = values[index[edge_target]] - sign * _EDGE_STRENGTH * current
                        gradient += -sign * _EDGE_STRENGTH * residual
                        hessian += _EDGE_STRENGTH**2
                    elif program is edge_target:
                        residual = current - sign * _EDGE_STRENGTH * values[index[edge_source]]
                        gradient += residual
                        hessian += 1.0
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            values[position] = current + _DAMPING * (proposal - current)
        update = max(abs(new - old_value) for new, old_value in zip(values, old, strict=True))
        objective = _objective(values, observations, center, scale, include_edges=include_edges)
        if update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            previous = objective
            break
        previous = objective
    return _Fit(
        values=tuple(_quantize(value) for value in values),
        objective=_quantize(previous),
        converged=converged,
    )


def _drivers(
    observations: tuple[_Observation, ...], center: float, scale: float
) -> tuple[str, ...]:
    ranked = sorted(
        observations,
        key=lambda item: (
            -abs(item.quality_weight * item.direction * _zscore(item.value, center, scale)),
            item.feature_id,
        ),
    )
    return tuple(item.feature_id for item in ranked[:3]) or ("no_observed_driver",)


def _hash_normal(material: str) -> float:
    def uniform(suffix: str) -> float:
        digest = hashlib.sha256((material + suffix).encode("utf-8")).digest()
        return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)

    first = max(_MIN_SCALE, uniform(":u1"))
    second = uniform(":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _bootstrap_draws(
    request: EstimateProteinAbundanceBaselineRequest,
    observations: tuple[_Observation, ...],
    request_digest: str,
) -> tuple[tuple[float, ...], ...] | None:
    draws: list[tuple[float, ...]] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbed = tuple(
            _Observation(
                feature_id=item.feature_id,
                program=item.program,
                direction=item.direction,
                value=item.value
                + item.standard_error
                * _hash_normal(f"{request_digest}:{draw}:{item.feature_id}"),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
                evidence=item.evidence,
            )
            for item in observations
        )
        center, scale = _robust_location_scale(item.value for item in perturbed)
        fit = _fit(perturbed, center, scale)
        if not fit.converged:
            return None
        draws.append(fit.values)
    return tuple(draws)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[position])


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


__all__ = ["BaselineKernelOutput", "GliomaBaselineOutput", "M0603BaselineKernel"]
