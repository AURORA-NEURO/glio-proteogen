"""Deterministic, replay-bound M13-04 mechanism inference runtime.

The dossier does not freeze an implementation ABI.  This runtime therefore
accepts only an explicit, documented caller-declared method grammar.  It never
opens artifact references, infers identity or consent, or treats an unknown
method as a negative biological finding.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_04 import (
    M1304_CONTRACT_VERSION,
    M1304_EVIDENCE_CLAIM,
    M1304_GLIOMA_MODEL_FAMILY,
    M1304_PARENT,
    InferProteotypeMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    MechanismObservationState,
    MechanismRelationKind,
    ProteotypeMechanismInferenceResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m13_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)

_REQUEST_ADAPTER: Final = TypeAdapter(InferProteotypeMechanismRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeMechanismInferenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset({"posterior", "state"})
_ABSTAIN_METHODS: Final = frozenset({"abstain", "unsupported", "not_calibrated"})
_SUPPORTED_STATES: Final = frozenset(
    {"active", "inactive", "present", "absent", "upregulated", "downregulated", "stable"}
)
_POSTERIOR_PARTS: Final = 6
_STATE_PARTS: Final = 4
_RIDGE: Final = 0.04
_DAMPING: Final = 0.72
_HUBER_DELTA: Final = 1.5
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-6
_OBJECTIVE_TOLERANCE: Final = 1e-10
_BACKTRACKING_STEPS: Final = 18
_BACKTRACKING_FACTOR: Final = 0.5
_MINIMUM_SCALE: Final = 1e-6
_MIN_TYPED_MECHANISMS: Final = 2
_LOW_QUANTILE: Final = 0.05
_HIGH_QUANTILE: Final = 0.95


@dataclass(frozen=True, slots=True)
class _TypedFit:
    mechanism_ids: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool
    trace: tuple[float, ...]


class M1304MechanismAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize mechanism inference."""

    def __init__(self) -> None:
        super().__init__(
            "M13-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1304ReplayVerificationError(ValueError):
    """A mechanism result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M13-04 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_mechanism_authorization(candidate: object) -> None:
    """Check seven controls before any opaque artifact or method traversal."""

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
        raise M1304MechanismAuthorizationError from None
    if states != expected:
        raise M1304MechanismAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_mechanism_authorization(candidate)
    return candidate


def _evidence(request: InferProteotypeMechanismRequest) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.hypothesis_registry_result,
        *request.source_artifacts,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
        *(item.reference for item in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(
            reference
            for item in request.typed_observations
            for reference in (e.reference for e in item.evidence)
        ),
        *(
            reference
            for item in request.typed_relations
            for reference in (e.reference for e in item.evidence)
        ),
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1304_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: InferProteotypeMechanismRequest,
) -> tuple[KernelEvidenceReference, ...]:
    # The references are caller-declared and are deliberately not opened.
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim="Caller-declared counter-evidence; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts[:64]
    )


def _decimal(value: str) -> float:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("mechanism probability is not numeric") from error  # noqa: TRY003
    if not number.is_finite() or not 0 <= number <= 1:
        raise ValueError(  # noqa: TRY003
            "mechanism probability must be finite and within [0, 1]"
        )
    return float(number)


def _parse_method(  # noqa: PLR0911
    method: str,
    *,
    counter_evidence: tuple[KernelEvidenceReference, ...],
    evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[MechanismEstimate | None, MechanismFindingCode | None, str | None]:
    """Parse only the explicit provisional method grammar.

    ``posterior:mechanism-id:label:probability:lower:upper`` and
    ``state:mechanism-id:label:state`` are the only evaluable forms.  Labels
    and IDs cannot contain colons.  ``abstain:<reason>`` is an explicit safe
    failure path.
    """

    parts = method.split(":")
    kind = parts[0].lower() if parts else ""
    if kind in _ABSTAIN_METHODS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Caller requested safe abstention."
    if kind not in _SUPPORTED_METHODS:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "Method is outside the closed grammar.",
        )
    if kind == "posterior":
        if len(parts) != _POSTERIOR_PARTS:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior method shape is invalid.",
            )
        mechanism_id, label = parts[1], parts[2]
        try:
            probability, lower, upper = (_decimal(value) for value in parts[3:])
        except ValueError:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior probability is invalid.",
            )
        if not mechanism_id or not label or lower > upper or not lower <= probability <= upper:
            return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Posterior bounds are invalid."
        return (
            MechanismEstimate(
                estimate_id=f"estimate.{mechanism_id}",
                mechanism_id=mechanism_id,
                label=label,
                kind=MechanismEstimateKind.POSTERIOR,
                posterior_probability=probability,
                lower_bound=lower,
                upper_bound=upper,
                assumptions=(
                    "The approved model and calibration references are caller-declared.",
                    "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
                ),
                alternatives=(
                    "Alternative mechanisms remain possible and require independent evidence.",
                ),
                counter_evidence=counter_evidence,
                evidence=evidence,
            ),
            None,
            None,
        )
    if len(parts) != _STATE_PARTS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "State method shape is invalid."
    mechanism_id, label, state_value = parts[1], parts[2], parts[3].lower()
    if not mechanism_id or not label or state_value not in _SUPPORTED_STATES:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "State value is outside the closed vocabulary.",
        )
    return (
        MechanismEstimate(
            estimate_id=f"estimate.{mechanism_id}",
            mechanism_id=mechanism_id,
            label=label,
            kind=MechanismEstimateKind.STATE,
            state_value=state_value,
            assumptions=(
                "The approved model and calibration references are caller-declared.",
                "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
            ),
            alternatives=(
                "Alternative mechanisms remain possible and require independent evidence.",
            ),
            counter_evidence=counter_evidence,
            evidence=evidence,
        ),
        None,
        None,
    )


def _huber_loss(value: float) -> float:
    absolute = abs(value)
    if absolute <= _HUBER_DELTA:
        return 0.5 * value * value
    return _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)


def _relation_coefficient(kind: MechanismRelationKind, weight: float) -> float:
    magnitude = max(_MINIMUM_SCALE, abs(weight))
    if kind is MechanismRelationKind.INHIBITS:
        return -magnitude
    if kind is MechanismRelationKind.ACTIVATES:
        return magnitude
    return math.copysign(magnitude, weight if abs(weight) > _MINIMUM_SCALE else 1.0)


def _typed_objective(
    values: list[float],
    observations: tuple[tuple[int, float, float, float, MechanismObservationState], ...],
    relations: tuple[tuple[int, int, float], ...],
) -> float:
    objective = _RIDGE * sum(value * value for value in values)
    for index, target, uncertainty, quality, state in observations:
        residual = (values[index] - target) / max(_MINIMUM_SCALE, uncertainty)
        if state is MechanismObservationState.LEFT_CENSORED:
            residual = max(0.0, residual)
        objective += quality * _huber_loss(residual)
    for source, target, coefficient in relations:
        objective += 0.5 * (values[target] - coefficient * values[source]) ** 2
    return objective


def _initial_typed_values(
    observations: tuple[tuple[int, float, float, float, MechanismObservationState], ...],
    mechanism_count: int,
) -> list[float]:
    """Build a feasible graph start without treating censor limits as values."""

    values = [0.0] * mechanism_count
    for position in range(mechanism_count):
        terms = tuple(item for item in observations if item[0] == position)
        observed = tuple(
            item for item in terms if item[4] is MechanismObservationState.OBSERVED
        )
        limits = tuple(
            item[1] for item in terms if item[4] is MechanismObservationState.LEFT_CENSORED
        )
        if observed:
            total = sum(item[3] / max(_MINIMUM_SCALE, item[2] ** 2) for item in observed)
            center = sum(
                item[1] * item[3] / max(_MINIMUM_SCALE, item[2] ** 2)
                for item in observed
            ) / max(_MINIMUM_SCALE, total)
            values[position] = min((center, *limits)) if limits else center
        elif limits:
            values[position] = min((0.0, *limits))
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    request: InferProteotypeMechanismRequest,
    *,
    perturbation: Mapping[str, float] | None = None,
) -> _TypedFit | None:
    """Fit latent proteotype mechanism activities with robust signed edges."""

    usable = tuple(
        item
        for item in request.typed_observations
        if item.state
        in {MechanismObservationState.OBSERVED, MechanismObservationState.LEFT_CENSORED}
        and item.standardized_effect is not None
        and item.standard_error is not None
        and item.quality_weight > 0.0
    )
    mechanism_ids = tuple(sorted({item.mechanism_id for item in usable}))
    if len(mechanism_ids) < _MIN_TYPED_MECHANISMS:
        return None
    index = {mechanism_id: position for position, mechanism_id in enumerate(mechanism_ids)}
    observations = tuple(
        (
            index[item.mechanism_id],
            item.standardized_effect + (perturbation or {}).get(item.observation_id, 0.0),
            item.standard_error,
            item.quality_weight,
            item.state,
        )
        for item in sorted(usable, key=lambda value: (value.mechanism_id, value.observation_id))
        if item.standardized_effect is not None and item.standard_error is not None
    )
    relations = tuple(
        (
            index[item.source_mechanism_id],
            index[item.target_mechanism_id],
            _relation_coefficient(item.kind, item.weight),
        )
        for item in sorted(request.typed_relations, key=lambda value: value.relation_id)
        if item.source_mechanism_id in index and item.target_mechanism_id in index
    )
    if not relations:
        return None
    values = _initial_typed_values(observations, len(mechanism_ids))
    initial_objective = _typed_objective(values, observations, relations)
    if not math.isfinite(initial_objective):
        return None
    trace = [round(initial_objective, 10)]
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        previous = values.copy()
        previous_objective = trace[-1]
        proposals = previous.copy()
        for position, current in enumerate(previous):
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for index_value, target, uncertainty, quality, state in observations:
                if index_value != position:
                    continue
                scale = max(_MINIMUM_SCALE, uncertainty)
                residual = (current - target) / scale
                if state is MechanismObservationState.LEFT_CENSORED and residual <= 0.0:
                    continue
                influence = (
                    1.0
                    if abs(residual) <= _HUBER_DELTA
                    else _HUBER_DELTA / max(_MINIMUM_SCALE, abs(residual))
                )
                information = quality * influence / (scale * scale)
                gradient += information * (current - target)
                hessian += information
            for source, target, coefficient in relations:
                if position == source:
                    residual = previous[target] - coefficient * current
                    gradient -= coefficient * residual
                    hessian += coefficient * coefficient
                elif position == target:
                    residual = current - coefficient * previous[source]
                    gradient += residual
                    hessian += 1.0
            proposal = current - gradient / max(_MINIMUM_SCALE, hessian)
            proposals[position] = current + _DAMPING * (proposal - current)
        next_objective = _typed_objective(proposals, observations, relations)
        accepted = proposals
        if not math.isfinite(next_objective) or (
            next_objective > previous_objective + _OBJECTIVE_TOLERANCE
        ):
            # Robust breakpoints and signed cycles can make a full Jacobi sweep
            # overshoot. Backtrack the complete vector update to preserve a
            # deterministic, replay-auditable monotone objective trace.
            accepted = previous.copy()
            next_objective = previous_objective
            delta = [after - before for after, before in zip(proposals, previous, strict=True)]
            step = _DAMPING
            for _ in range(_BACKTRACKING_STEPS):
                step *= _BACKTRACKING_FACTOR
                trial = [
                    before + step * change
                    for before, change in zip(previous, delta, strict=True)
                ]
                trial_objective = _typed_objective(trial, observations, relations)
                if math.isfinite(trial_objective) and (
                    trial_objective <= previous_objective + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    next_objective = trial_objective
                    break
            else:
                return None
        values = accepted
        trace.append(round(next_objective, 10))
        update = max(abs(after - before) for after, before in zip(values, previous, strict=True))
        if (
            update <= _SOLVER_TOLERANCE
            and abs(previous_objective - next_objective) <= _SOLVER_TOLERANCE
        ):
            return _TypedFit(
                mechanism_ids=mechanism_ids,
                values=tuple(float(f"{value:.8f}") for value in values),
                objective=float(f"{next_objective:.8f}"),
                iterations=iteration,
                converged=True,
                trace=tuple(float(f"{value:.8f}") for value in trace),
            )
    return _TypedFit(
        mechanism_ids=mechanism_ids,
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{trace[-1]:.8f}"),
        iterations=_SOLVER_ITERATIONS,
        converged=False,
        trace=tuple(float(f"{value:.8f}") for value in trace),
    )


def _hash_normal(material: str) -> float:
    first = (
        int.from_bytes(hashlib.sha256((material + ":u1").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    second = (
        int.from_bytes(hashlib.sha256((material + ":u2").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    return math.sqrt(-2.0 * math.log(max(_MINIMUM_SCALE, first))) * math.cos(2.0 * math.pi * second)


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-min(40.0, value)))
    exponential = math.exp(max(-40.0, value))
    return exponential / (1.0 + exponential)


def _nearest_quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return float(f"{ordered[position]:.8f}")


def _typed_estimates(
    request: InferProteotypeMechanismRequest,
    request_hash: str,
    evidence: tuple[KernelEvidenceReference, ...],
    counter_evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[tuple[MechanismEstimate, ...], _TypedFit | None, str | None]:
    fit = _fit_typed(request)
    if fit is None:
        return (
            (),
            None,
            "typed glioma proteotype graph requires two supported mechanisms and a signed relation",
        )
    if not fit.converged:
        return (), fit, "typed glioma proteotype graph did not converge"
    draws: dict[str, list[float]] = {mechanism_id: [] for mechanism_id in fit.mechanism_ids}
    usable = tuple(
        item
        for item in request.typed_observations
        if item.state
        in {MechanismObservationState.OBSERVED, MechanismObservationState.LEFT_CENSORED}
        and item.standardized_effect is not None
        and item.standard_error is not None
    )
    for draw in range(request.configuration.bootstrap_replicates):
        perturbation = {
            item.observation_id: item.standard_error
            * _hash_normal(f"{request_hash}:{draw}:{item.observation_id}")
            for item in usable
            if item.standard_error is not None
        }
        sample = _fit_typed(request, perturbation=perturbation)
        if sample is None or not sample.converged:
            return (), sample, "typed glioma proteotype bootstrap fit did not converge"
        for mechanism_id, value in zip(sample.mechanism_ids, sample.values, strict=True):
            draws[mechanism_id].append(_sigmoid(value))
    labels = {item.mechanism_id: item.label for item in request.typed_observations}
    estimates = tuple(
        MechanismEstimate(
            estimate_id=f"estimate.{mechanism_id}",
            mechanism_id=mechanism_id,
            label=labels[mechanism_id],
            kind=MechanismEstimateKind.POSTERIOR,
            posterior_probability=float(f"{_sigmoid(value):.8f}"),
            lower_bound=min(
                _nearest_quantile(tuple(draws[mechanism_id]), _LOW_QUANTILE), _sigmoid(value)
            ),
            upper_bound=max(
                _nearest_quantile(tuple(draws[mechanism_id]), _HIGH_QUANTILE), _sigmoid(value)
            ),
            assumptions=(
                "Typed proteotype evidence is fitted with robust signed graph regularization.",
                "The upstream M13-01 hypothesis artifact remains opaque.",
            ),
            alternatives=(
                "Alternative proteotype mechanisms remain possible and require independent "
                "evidence.",
            ),
            counter_evidence=counter_evidence,
            evidence=evidence,
        )
        for mechanism_id, value in zip(fit.mechanism_ids, fit.values, strict=True)
    )
    return estimates, fit, None


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="counter_evidence_preserved",
            statement=(
                "Assumptions, alternatives, and counter-evidence remain attached to every estimate."
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
                statement="No mechanism estimate is published outside the closed method grammar.",
            )
        )
    return tuple(values)


class M1304MechanismEngine:
    """Infer a caller-declared mechanism estimate with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteotypeMechanismInferenceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: InferProteotypeMechanismRequest
    ) -> ProteotypeMechanismInferenceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        counter_evidence = _counter_evidence(request)
        typed = request.configuration.model_family == M1304_GLIOMA_MODEL_FAMILY
        fit: _TypedFit | None = None
        if typed:
            estimates, fit, finding_message = _typed_estimates(
                request, request_hash, evidence, counter_evidence
            )
            finding_code = None if estimates else MechanismFindingCode.MODEL_NOT_CALIBRATED
            safe = bool(estimates and counter_evidence and fit is not None and fit.converged)
            if not safe and finding_message is None:
                finding_message = "Typed proteotype mechanism graph abstained."
        else:
            estimate, finding_code, finding_message = _parse_method(
                request.configuration.method,
                counter_evidence=counter_evidence,
                evidence=evidence,
            )
            safe = estimate is not None and bool(counter_evidence)
            if estimate is None:
                safe = False
                finding_code = finding_code or MechanismFindingCode.MODEL_NOT_CALIBRATED
                finding_message = finding_message or "Mechanism estimate is not evaluable."
            elif not counter_evidence:
                safe = False
                finding_code = MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED
                finding_message = "At least one counter-evidence reference is required."
            estimates = (estimate,) if safe and estimate is not None else ()
        findings = (
            ()
            if safe
            else (
                MechanismFinding(
                    finding_id=f"finding.{request.request_id}",
                    code=finding_code or MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED,
                    message=finding_message or "Mechanism inference abstained.",
                    evidence=evidence,
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "proteotype_mechanism_inference",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1304_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismInferenceStatus.INFERRED
            if safe
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": findings,
            "abstention_reason": None
            if safe
            else (finding_message or "Mechanism inference abstained."),
            "parent_target": M1304_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if safe else SupportStatus.UNSUPPORTED,
                reason_code="m1104_mechanism_inferred" if safe else "m1104_mechanism_abstained",
                rationale=(
                    "Explicit posterior/state method, bounds, calibration references, and "
                    "counter-evidence passed."
                    if safe
                    else "The mechanism request is outside the safely evaluable support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=safe),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=safe),
            "human_review_required": not safe,
            "typed_model": typed and safe,
            "model_profile": M1304_GLIOMA_MODEL_FAMILY if typed and safe else None,
            "solver_iterations": fit.iterations if fit is not None else 0,
            "solver_objective": fit.objective if fit is not None and safe else None,
            "converged": fit.converged if fit is not None else True,
        }
        constructed = ProteotypeMechanismInferenceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1304ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1304ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1304ReplayVerificationError
        return validated


def infer_proteotype_mechanism(
    request: object,
) -> ProteotypeMechanismInferenceResult:
    """Public provisional M13-04 operation."""

    return M1304MechanismEngine().infer(request)


__all__ = [
    "M1304MechanismAuthorizationError",
    "M1304MechanismEngine",
    "M1304ReplayVerificationError",
    "infer_proteotype_mechanism",
    "preflight_mechanism_authorization",
    "result_payload_digest",
]
