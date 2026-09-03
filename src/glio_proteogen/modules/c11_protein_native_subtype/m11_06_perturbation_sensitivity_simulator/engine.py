"""Deterministic, safety-gated M11-06 sensitivity simulation runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from math import sqrt, tanh
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_06 import (
    M1106_CONTRACT_VERSION,
    M1106_EVIDENCE_CLAIM,
    M1106_MINIMUM_REPLICATES_PER_ARM,
    M1106_PARENT,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivityDiagnostic,
    SensitivityDiagnosticStatus,
    SensitivityFindingCode,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateVariantPeptidePerturbationsRequest,
    VariantPeptideSensitivitySimulationResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m11_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateVariantPeptidePerturbationsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideSensitivitySimulationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_REJECTED_MARKERS: Final = frozenset(
    {"abstain", "fail", "incomplete", "missing", "n/a", "novel", "ood", "unknown", "unsupported"}
)
_PROHIBITED_MARKERS: Final = frozenset({"all_omics", "kinase", "treatment", "therapy"})
_HUBER_DELTA: Final = 1.5
_HUBER_ITERATIONS: Final = 24
_HUBER_DAMPING: Final = 0.7
_MAD_SCALE_FACTOR: Final = 1.4826
_MINIMUM_SCALE: Final = 1e-6
_BOOTSTRAP_QUANTILE: Final = 0.05
_RESPONSE_SCALE: Final = 3.0


class M1106AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for simulation."""

    def __init__(self) -> None:
        super().__init__(
            "M11-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1106ReplayVerificationError(ValueError):
    """A sensitivity result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M11-06 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_sensitivity_authorization(candidate: object) -> None:
    """Validate all seven controls before traversing any caller payload."""

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
        raise M1106AuthorizationError from None
    if states != expected:
        raise M1106AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_sensitivity_authorization(candidate)
    return candidate


def _evidence(
    request: SimulateVariantPeptidePerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    """Preserve caller evidence as references, never as traversed payloads."""

    refs = request.context.references
    artifacts = [
        *request.source_artifacts,
        request.upstream_result,
        request.configuration.reference_artifact,
        *(item.reference for item in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    if request.configuration.negative_control_artifact is not None:
        artifacts.append(request.configuration.negative_control_artifact)
    artifacts.extend(
        item.reference for perturbation in request.perturbations for item in perturbation.evidence
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1106_EVIDENCE_CLAIM)
        for artifact in artifacts[:64]
    )


def _text_is_unsafe(value: str) -> bool:
    tokens = {token for token in value.lower().replace("-", "_").split("_") if token}
    return bool(tokens & _REJECTED_MARKERS)


def _text_is_prohibited(value: str) -> bool:
    tokens = {token for token in value.lower().replace("-", "_").split("_") if token}
    return bool(tokens & _PROHIBITED_MARKERS)


def _huber_location(values: tuple[float, ...]) -> tuple[float, float]:
    """Estimate a proteomic arm location and robust standard error."""

    estimate = sum(values) / len(values)
    for _ in range(_HUBER_ITERATIONS):
        residuals = tuple(value - estimate for value in values)
        scale = max(
            _MAD_SCALE_FACTOR * sorted(abs(value) for value in residuals)[len(values) // 2],
            _MINIMUM_SCALE,
        )
        weights = tuple(
            1.0
            if abs(residual) / scale <= _HUBER_DELTA
            else _HUBER_DELTA / (abs(residual) / scale)
            for residual in residuals
        )
        denominator = sum(weights)
        updated = (
            sum(weight * value for weight, value in zip(weights, values, strict=True))
            / denominator
        )
        damped = _HUBER_DAMPING * updated + (1.0 - _HUBER_DAMPING) * estimate
        if abs(damped - estimate) <= _MINIMUM_SCALE / 100.0:
            estimate = damped
            break
        estimate = damped
    residuals = tuple(value - estimate for value in values)
    weighted_variance = sum(
        weight * residual * residual
        for weight, residual in zip(weights, residuals, strict=True)
    ) / max(sum(weights) - 1.0, 1.0)
    return estimate, sqrt(max(weighted_variance / len(values), _MINIMUM_SCALE**2))


def _bootstrap_deltas(
    baseline: tuple[float, ...],
    perturbed: tuple[float, ...],
    seed: int,
    draws: int,
) -> tuple[float, ...]:
    """Generate deterministic paired-arm bootstrap deltas for replayable bounds."""

    deltas: list[float] = []
    for draw in range(draws):
        sampled_baseline = tuple(
            baseline[
                int.from_bytes(
                    hashlib.sha256(f"{seed}:{draw}:baseline:{index}".encode())
                    .digest()[:8],
                    "big",
                )
                % len(baseline)
            ]
            for index in range(len(baseline))
        )
        sampled_perturbed = tuple(
            perturbed[
                int.from_bytes(
                    hashlib.sha256(f"{seed}:{draw}:perturbed:{index}".encode())
                    .digest()[:8],
                    "big",
                )
                % len(perturbed)
            ]
            for index in range(len(perturbed))
        )
        deltas.append(_huber_location(sampled_perturbed)[0] - _huber_location(sampled_baseline)[0])
    return tuple(deltas)


def _bounded_response(
    request: SimulateVariantPeptidePerturbationsRequest,
    perturbation: PerturbationSpecification,
) -> SensitivityResponse:
    """Fit a robust finite-difference response from typed replicate evidence."""

    baseline = perturbation.baseline_measurements
    perturbed = perturbation.perturbed_measurements
    baseline_estimate, baseline_error = _huber_location(baseline)
    perturbed_estimate, perturbed_error = _huber_location(perturbed)
    raw_delta = perturbed_estimate - baseline_estimate
    standard_error = max(sqrt(baseline_error**2 + perturbed_error**2), _MINIMUM_SCALE)
    standardized = perturbation.quality_weight * raw_delta / standard_error
    value = tanh(standardized / _RESPONSE_SCALE)
    seed_material = f"{canonical_request_digest(request)}:{perturbation.perturbation_id}"
    seed = int.from_bytes(hashlib.sha256(seed_material.encode("utf-8")).digest()[:8], "big")
    deltas = _bootstrap_deltas(
        baseline,
        perturbed,
        seed,
        request.configuration.bootstrap_replicates,
    )
    transformed = tuple(
        tanh(perturbation.quality_weight * delta / standard_error / _RESPONSE_SCALE)
        for delta in deltas
    )
    ordered = sorted(transformed)
    lower_index = max(0, int(_BOOTSTRAP_QUANTILE * (len(ordered) - 1)))
    upper_index = min(len(ordered) - 1, int((1.0 - _BOOTSTRAP_QUANTILE) * (len(ordered) - 1)))
    lower = min(value, ordered[lower_index])
    upper = max(value, ordered[upper_index])
    return SensitivityResponse(
        scenario_id=perturbation.perturbation_id,
        status=PerturbationResponseStatus.BOUNDED,
        response_value=round(value, 8),
        lower_bound=round(max(-1.0, lower), 8),
        upper_bound=round(min(1.0, upper), 8),
        raw_effect_delta=round(raw_delta, 8),
        sensitivity_standard_error=round(standard_error, 8),
        replicate_count=len(baseline) + len(perturbed),
        assumptions=(
            "Arm locations use quality-weighted Huber IRLS over typed proteomic replicates.",
            "The bounded response is a finite-difference sensitivity, not a causal effect.",
            (
                f"{request.configuration.bootstrap_replicates} deterministic bootstrap draws "
                "provide the interval."
            ),
            f"Perturbation kind {perturbation.kind.value} is evaluated as a bounded stress test.",
        ),
        evidence=perturbation.evidence,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="bounded_not_causal",
            statement=(
                "Sensitivity responses are bounded stress-test projections, not causal effects."
            ),
        ),
        Limitation(
            code="opaque_artifacts",
            statement=(
                "External artifacts remain immutable references and are never traversed; only "
                "typed replicate values in the request are fitted."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "No kinase state, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported or unresolved perturbations publish no sensitivity surface.",
            )
        )
    return tuple(values)


class M1106SensitivityEngine:
    """Evaluate caller-declared perturbations without hidden biological claims."""

    __slots__ = ()

    def register(self, request: object) -> VariantPeptideSensitivitySimulationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: SimulateVariantPeptidePerturbationsRequest,
    ) -> VariantPeptideSensitivitySimulationResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        unsafe: list[SensitivityFindingCode] = []
        for perturbation in request.perturbations:
            declared = (
                perturbation.parameter,
                perturbation.baseline_value,
                perturbation.perturbed_value,
                *perturbation.target_ids,
            )
            if any(_text_is_prohibited(value) for value in declared):
                unsafe.append(SensitivityFindingCode.ASSUMPTION_UNRESOLVED)
            elif any(_text_is_unsafe(value) for value in declared):
                unsafe.append(SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE)
            if (
                len(perturbation.baseline_measurements) < M1106_MINIMUM_REPLICATES_PER_ARM
                or len(perturbation.perturbed_measurements) < M1106_MINIMUM_REPLICATES_PER_ARM
                or perturbation.quality_weight <= 0.0
            ):
                unsafe.append(SensitivityFindingCode.INPUT_INCOMPLETE)
        if request.configuration.negative_control_artifact is None:
            unsafe.append(SensitivityFindingCode.NEGATIVE_CONTROL_FAILED)
        if len(request.perturbations) > request.configuration.maximum_scenarios:
            unsafe.append(SensitivityFindingCode.INPUT_INCOMPLETE)
        if unsafe:
            diagnostics = (
                SensitivityDiagnostic(
                    diagnostic_id="diagnostic.safety_gate",
                    status=SensitivityDiagnosticStatus.FAIL,
                    message="One or more perturbations failed the locked safety envelope.",
                    evidence=evidence,
                ),
                SensitivityDiagnostic(
                    diagnostic_id="diagnostic.surface",
                    status=SensitivityDiagnosticStatus.NOT_EVALUABLE,
                    message="No sensitivity surface is published after safe abstention.",
                    evidence=evidence,
                ),
            )
            payload: dict[str, object] = {
                "output_type": "variant_peptide_sensitivity_surface",
                "result_id": f"result.{request_hash.removeprefix('sha256:')}",
                "result_version": M1106_CONTRACT_VERSION,
                "request_digest": request_hash,
                "result_digest": _ZERO_DIGEST,
                "request": request,
                "status": SensitivitySimulationStatus.ABSTAINED,
                "surface": None,
                "diagnostics": diagnostics,
                "findings": tuple(dict.fromkeys(unsafe)),
                "abstention_reason": (
                    "At least one perturbation or negative-control gate is not safely evaluable."
                ),
                "parent_target": M1106_PARENT,
                "emits_parent": False,
                "support_decision": SupportDecision(
                    status=SupportStatus.UNSUPPORTED,
                    reason_code="m1106_safety_gate_abstained",
                    rationale=(
                        "Unsupported perturbations never become negative findings "
                        "or bounded claims."
                    ),
                ),
                "uncertainty": expected_uncertainty(supported=False),
                "provenance": expected_provenance(request, request_hash),
                "evidence": evidence,
                "limitations": _limitations(supported=False),
                "human_review_required": True,
            }
            constructed = VariantPeptideSensitivitySimulationResult.model_construct(
                **cast("dict[str, Any]", payload)
            )
            payload["result_digest"] = result_payload_digest(constructed)
            return _RESULT_ADAPTER.validate_python(payload, strict=True)

        responses = tuple(_bounded_response(request, item) for item in request.perturbations)
        diagnostics = (
            SensitivityDiagnostic(
                diagnostic_id="diagnostic.safety_gate",
                status=SensitivityDiagnosticStatus.PASS,
                message=(
                    "All controls, negative-control gating, and perturbation envelope "
                    "checks passed."
                ),
                evidence=evidence,
            ),
            SensitivityDiagnostic(
                diagnostic_id="diagnostic.surface",
                status=SensitivityDiagnosticStatus.PASS,
                message="Every declared perturbation has exactly one bounded response.",
                evidence=evidence,
            ),
        )
        surface = SensitivitySurface(
            surface_id=f"surface.{request_hash.removeprefix('sha256:')}",
            version=M1106_CONTRACT_VERSION,
            baseline_result=request.upstream_result,
            perturbations=request.perturbations,
            responses=responses,
            configuration=request.configuration,
            evidence=evidence,
        )
        payload = {
            "output_type": "variant_peptide_sensitivity_surface",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1106_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": SensitivitySimulationStatus.SIMULATED,
            "surface": surface,
            "diagnostics": diagnostics,
            "findings": (),
            "abstention_reason": None,
            "parent_target": M1106_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1106_surface_supported",
                rationale=(
                    "All declared perturbations yielded deterministic responses inside "
                    "the envelope."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=True),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=True),
            "human_review_required": False,
        }
        constructed = VariantPeptideSensitivitySimulationResult.model_construct(
            **cast("dict[str, Any]", payload)
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideSensitivitySimulationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1106ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1106ReplayVerificationError
        if replay:
            expected = self.register(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1106ReplayVerificationError
        return validated


def simulate_variant_peptide_perturbations(
    request: object,
) -> VariantPeptideSensitivitySimulationResult:
    """Public provisional M11-06 operation."""

    return M1106SensitivityEngine().register(request)


__all__ = [
    "M1106AuthorizationError",
    "M1106ReplayVerificationError",
    "M1106SensitivityEngine",
    "preflight_sensitivity_authorization",
    "simulate_variant_peptide_perturbations",
]
