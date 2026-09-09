"""Deterministic, replay-bound M12-04 mechanism inference runtime.

The implementation deliberately evaluates only a documented caller-declared
method grammar.  It never opens artifact references, infers identity or
consent, mutates upstream evidence, or converts unknown evidence to a
negative biological finding.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_04 import (
    M1204_CONTRACT_VERSION,
    M1204_EVIDENCE_CLAIM,
    M1204_GLIOMA_MODEL_FAMILY,
    M1204_PARENT,
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    MechanismObservationState,
    MechanismRelationKind,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m12_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import EvidenceReference as KernelEvidenceReference

_REQUEST_ADAPTER: Final = TypeAdapter(InferBiomarkerPanelMechanismRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelMechanismInferenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset({"posterior", "state"})
_ABSTAIN_METHODS: Final = frozenset({"abstain", "unsupported", "not_calibrated"})
_SUPPORTED_STATES: Final = frozenset(
    {"active", "inactive", "present", "absent", "upregulated", "downregulated", "stable"}
)
_POSTERIOR_PARTS: Final = 6
_STATE_PARTS: Final = 4
_M1204_RIDGE: Final = 0.04
_M1204_DAMPING: Final = 0.72
_M1204_HUBER_DELTA: Final = 1.5
_M1204_SOLVER_ITERATIONS: Final = 160
_M1204_SOLVER_TOLERANCE: Final = 1e-6
_M1204_MIN_SCALE: Final = 1e-6
_M1204_MIN_TYPED_MECHANISMS: Final = 2


@dataclass(frozen=True, slots=True)
class _TypedFit:
    mechanism_ids: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool


class M1204MechanismAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize mechanism inference."""

    def __init__(self) -> None:
        super().__init__(
            "M12-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1204ReplayVerificationError(ValueError):
    """A mechanism result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M12-04 replay verification failed")


class M1204MechanismInferenceError(ValueError):
    """A caller-declared mechanism method cannot be evaluated safely."""


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
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise M1204MechanismAuthorizationError from None
    if states != expected:
        raise M1204MechanismAuthorizationError


def _evidence(request: InferBiomarkerPanelMechanismRequest) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.hypothesis_registry_result,
        *request.source_artifacts,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
        *(item.reference for item in request.configuration.evidence),
        *(e.reference for item in request.typed_observations for e in item.evidence),
        *(e.reference for item in request.typed_relations for e in item.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1204_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: InferBiomarkerPanelMechanismRequest,
) -> tuple[KernelEvidenceReference, ...]:
    """Project caller-declared source references without opening them."""

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
    """Parse the closed provisional method grammar.

    ``posterior:mechanism-id:label:probability:lower:upper`` and
    ``state:mechanism-id:label:state`` are the only evaluable forms.
    ``abstain:<reason>`` is an explicit safe failure path.
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
                    "The upstream biomarker-panel hypothesis result is treated as opaque evidence.",
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
                "The upstream biomarker-panel hypothesis result is treated as opaque evidence.",
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


def _huber(value: float) -> float:
    absolute = abs(value)
    return (
        0.5 * value * value
        if absolute <= _M1204_HUBER_DELTA
        else _M1204_HUBER_DELTA * (absolute - 0.5 * _M1204_HUBER_DELTA)
    )


def _hash_normal(material: str) -> float:
    first = (
        int.from_bytes(hashlib.sha256((material + ":u1").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    second = (
        int.from_bytes(hashlib.sha256((material + ":u2").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    return math.sqrt(-2.0 * math.log(max(_M1204_MIN_SCALE, first))) * math.cos(
        2.0 * math.pi * second
    )


def _relation_coefficient(kind: MechanismRelationKind, weight: float) -> float:
    magnitude = max(_M1204_MIN_SCALE, abs(weight))
    if kind is MechanismRelationKind.INHIBITS:
        return -magnitude
    if kind is MechanismRelationKind.ACTIVATES:
        return magnitude
    return math.copysign(magnitude, weight if abs(weight) > _M1204_MIN_SCALE else 1.0)


def _fit_typed(  # noqa: C901, PLR0912 - explicit coordinate updates are auditable.
    request: InferBiomarkerPanelMechanismRequest,
    *,
    perturbation: Mapping[str, float] | None = None,
) -> _TypedFit | None:
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
    if len(mechanism_ids) < _M1204_MIN_TYPED_MECHANISMS:
        return None
    index = {mechanism_id: position for position, mechanism_id in enumerate(mechanism_ids)}
    observations: list[tuple[int, float, float, float, MechanismObservationState]] = []
    for item in sorted(usable, key=lambda value: (value.mechanism_id, value.observation_id)):
        effect = item.standardized_effect
        uncertainty = item.standard_error
        if effect is None or uncertainty is None:
            continue
        observations.append(
            (
                index[item.mechanism_id],
                effect + (perturbation or {}).get(item.observation_id, 0.0),
                uncertainty,
                item.quality_weight,
                item.state,
            )
        )
    # ``weight`` has a schema default for the legacy ABI. In the typed
    # research lane, an omitted field is not an asserted unit-strength edge.
    if any(
        item.source_mechanism_id in index
        and item.target_mechanism_id in index
        and "weight" not in item.model_fields_set
        for item in request.typed_relations
    ):
        return None
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
    values = [0.0] * len(mechanism_ids)
    for position in range(len(values)):
        terms = [item for item in observations if item[0] == position]
        total = sum(item[3] / max(_M1204_MIN_SCALE, item[2] ** 2) for item in terms)
        values[position] = sum(
            item[1] * item[3] / max(_M1204_MIN_SCALE, item[2] ** 2) for item in terms
        ) / max(_M1204_MIN_SCALE, total)
    objective = float("inf")
    for iteration in range(1, _M1204_SOLVER_ITERATIONS + 1):
        previous = values.copy()
        for position, current in enumerate(values):
            gradient = 2.0 * _M1204_RIDGE * current
            hessian = 2.0 * _M1204_RIDGE
            for index_value, target, uncertainty, quality, state in observations:
                if index_value != position:
                    continue
                scale = max(_M1204_MIN_SCALE, uncertainty)
                residual = (current - target) / scale
                if state is MechanismObservationState.LEFT_CENSORED:
                    residual = max(0.0, residual)
                if state is MechanismObservationState.LEFT_CENSORED and residual == 0.0:
                    continue
                influence = (
                    1.0
                    if abs(residual) <= _M1204_HUBER_DELTA
                    else _M1204_HUBER_DELTA / max(_M1204_MIN_SCALE, abs(residual))
                )
                information = quality * influence / (scale * scale)
                gradient += information * (current - target)
                hessian += information
            for source, target, coefficient in relations:
                if position == source:
                    residual = values[target] - coefficient * current
                    gradient -= coefficient * residual
                    hessian += coefficient * coefficient
                elif position == target:
                    residual = current - coefficient * values[source]
                    gradient += residual
                    hessian += 1.0
            proposal = current - gradient / max(_M1204_MIN_SCALE, hessian)
            values[position] = current + _M1204_DAMPING * (proposal - current)
        next_objective = _M1204_RIDGE * sum(value * value for value in values)
        next_objective += sum(
            quality
            * _huber(
                max(0.0, (value - target) / max(_M1204_MIN_SCALE, uncertainty))
                if state is MechanismObservationState.LEFT_CENSORED
                else (value - target) / max(_M1204_MIN_SCALE, uncertainty)
            )
            for index_value, target, uncertainty, quality, state in observations
            for value in (values[index_value],)
        )
        next_objective += sum(
            0.5 * (values[target] - coefficient * values[source]) ** 2
            for source, target, coefficient in relations
        )
        update = max(abs(after - before) for after, before in zip(values, previous, strict=True))
        if (
            update <= _M1204_SOLVER_TOLERANCE
            and abs(objective - next_objective) <= 2.0 * _M1204_SOLVER_TOLERANCE
        ):
            return _TypedFit(
                mechanism_ids=mechanism_ids,
                values=tuple(float(f"{value:.8f}") for value in values),
                objective=float(f"{next_objective:.8f}"),
                iterations=iteration,
                converged=True,
            )
        objective = next_objective
    return _TypedFit(
        mechanism_ids=mechanism_ids,
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{objective:.8f}"),
        iterations=_M1204_SOLVER_ITERATIONS,
        converged=False,
    )


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-min(40.0, value)))
    exponential = math.exp(max(-40.0, value))
    return exponential / (1.0 + exponential)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return float(f"{ordered[index]:.8f}")


def _typed_estimates(
    request: InferBiomarkerPanelMechanismRequest,
    request_hash: str,
    evidence: tuple[KernelEvidenceReference, ...],
    counter_evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[tuple[MechanismEstimate, ...], _TypedFit | None, str | None]:
    fit = _fit_typed(request)
    if fit is None:
        return (
            (),
            None,
            "typed glioma panel graph requires two supported mechanisms and a signed relation",
        )
    if not fit.converged:
        return (), fit, "typed glioma panel graph did not converge"
    draws: dict[str, list[float]] = {mechanism_id: [] for mechanism_id in fit.mechanism_ids}
    usable = tuple(
        item
        for item in request.typed_observations
        if item.state
        in {MechanismObservationState.OBSERVED, MechanismObservationState.LEFT_CENSORED}
        and item.standard_error is not None
        and item.standardized_effect is not None
    )
    for draw in range(request.configuration.bootstrap_replicates):
        perturbation: dict[str, float] = {}
        for item in usable:
            if item.standard_error is not None:
                perturbation[item.observation_id] = item.standard_error * _hash_normal(
                    f"{request_hash}:{draw}:{item.observation_id}"
                )
        sample = _fit_typed(request, perturbation=perturbation)
        if sample is None or not sample.converged:
            return (), sample, "typed glioma panel bootstrap fit did not converge"
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
            lower_bound=min(_quantile(tuple(draws[mechanism_id]), 0.05), _sigmoid(value)),
            upper_bound=max(_quantile(tuple(draws[mechanism_id]), 0.95), _sigmoid(value)),
            assumptions=(
                "Biomarker effects are standardized caller-declared observations.",
                "Signed relations encode panel activation, inhibition, or coupling constraints.",
            ),
            alternatives=(
                "Unmeasured mechanisms and alternative panel topologies remain possible.",
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


class M1204MechanismEngine:
    """Infer a caller-declared mechanism estimate with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelMechanismInferenceResult:
        preflight_mechanism_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: InferBiomarkerPanelMechanismRequest
    ) -> BiomarkerPanelMechanismInferenceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        counter_evidence = _counter_evidence(request)
        typed = request.configuration.model_family == M1204_GLIOMA_MODEL_FAMILY
        fit: _TypedFit | None = None
        finding_code: MechanismFindingCode | None = None
        if typed:
            estimates, fit, finding_message = _typed_estimates(
                request, request_hash, evidence, counter_evidence
            )
            finding_code = MechanismFindingCode.MODEL_NOT_CALIBRATED
            safe = bool(estimates) and bool(counter_evidence) and fit is not None and fit.converged
            if not counter_evidence:
                safe = False
                finding_code = MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED
                finding_message = "At least one counter-evidence reference is required."
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
            "output_type": "biomarker_panel_mechanism_inference",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1204_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismInferenceStatus.INFERRED
            if safe
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": findings,
            "abstention_reason": (
                None if safe else (finding_message or "Mechanism inference abstained.")
            ),
            "parent_target": M1204_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if safe else SupportStatus.UNSUPPORTED,
                reason_code="m1204_mechanism_inferred" if safe else "m1204_mechanism_abstained",
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
            "model_profile": request.configuration.model_family if typed else None,
            "solver_iterations": fit.iterations if fit is not None else 0,
            "solver_objective": fit.objective if fit is not None else None,
            "converged": fit.converged if fit is not None else True,
        }
        constructed = BiomarkerPanelMechanismInferenceResult.model_construct(
            **cast("dict[str, Any]", payload)
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1204ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1204ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1204ReplayVerificationError
        return validated


def infer_biomarker_panel_mechanism(
    request: object,
) -> BiomarkerPanelMechanismInferenceResult:
    """Public provisional M12-04 operation."""

    return M1204MechanismEngine().infer(request)


__all__ = [
    "M1204MechanismAuthorizationError",
    "M1204MechanismEngine",
    "M1204MechanismInferenceError",
    "M1204ReplayVerificationError",
    "infer_biomarker_panel_mechanism",
    "preflight_mechanism_authorization",
]
