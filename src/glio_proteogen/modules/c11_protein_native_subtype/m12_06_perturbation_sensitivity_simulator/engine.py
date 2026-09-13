"""Pure, deterministic M12-06 bounded perturbation execution."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from math import sqrt
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_06 import (
    M1206_CONTRACT_VERSION,
    M1206_GLIOMA_MODEL_FAMILY,
    M1206_MINIMUM_REPLICATES_PER_ARM,
    M1206_MODULE_ID,
    BiomarkerPanelPerturbationSensitivityResult,
    PerturbationFinding,
    PerturbationFindingCode,
    PerturbationResponse,
    PerturbationResponseStatus,
    PerturbationScenario,
    PerturbationStatus,
    SensitivityMetric,
    SensitivitySurface,
    SimulateBiomarkerPanelPerturbationRequest,
    SimulatorStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateBiomarkerPanelPerturbationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelPerturbationSensitivityResult)
_RESULT_MEDIA_TYPE: Final = "application/json"
_HUBER_DELTA: Final = 1.5
_HUBER_ITERATIONS: Final = 32
_HUBER_DAMPING: Final = 0.72
_MAD_SCALE_FACTOR: Final = 1.4826
_MINIMUM_SCALE: Final = 1e-6
_OBJECTIVE_TOLERANCE: Final = 1e-12
_BACKTRACKING_STEPS: Final = 12
_BACKTRACKING_FACTOR: Final = 0.5
_BOOTSTRAP_LOW_QUANTILE: Final = 0.05
_BOOTSTRAP_HIGH_QUANTILE: Final = 0.95
_RESPONSE_SCALE: Final = 3.0
_LIMITATIONS: Final = (
    Limitation(
        code="m1206_provisional_abi",
        statement="M12-06 ABI is provisional pending dossier-owner confirmation.",
    ),
    Limitation(
        code="bounded_perturbation_only",
        statement="Output is a bounded sensitivity surface, not a treatment recommendation.",
    ),
    Limitation(
        code="opaque_upstream_evidence",
        statement="Upstream consequence artifacts are referenced but never traversed or mutated.",
    ),
)


class M1206AuthorizationError(ValueError):
    """Required caller-declared controls are not authorized."""

    def __init__(self) -> None:
        super().__init__("M12-06 controls do not authorize perturbation simulation")


class M1206ReplayError(ValueError):
    """A result cannot be replayed against its exact request."""

    def __init__(self, message: str = "M12-06 result failed replay verification") -> None:
        super().__init__(message)


def _member(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def preflight_m1206_authorization(candidate: object) -> None:
    """Check all controls before typed conversion or payload interpretation."""

    context = _member(candidate, "context")
    references = _member(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _member(_member(references, role), "state") != state for role, state in expected.items()
    ):
        raise M1206AuthorizationError


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration, None),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage, refs.identity_lineage.binding_digest),
        (ControlRole.PROVENANCE, refs.provenance, None),
        (ControlRole.CONSENT, refs.consent, None),
        (ControlRole.QUALITY, refs.quality, None),
        (ControlRole.SUPPORT, refs.support, None),
        (ControlRole.INTENDED_USE, refs.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _estimate(probability: float, rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(
        state=EstimateState.ESTIMATED, probability=probability, rationale=rationale
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty(*, simulated: bool, typed: bool = False) -> UncertaintyProfile:
    if simulated:
        return UncertaintyProfile(
            measurement=_estimate(0.90, "Declared assay perturbation units are bounded."),
            sampling=_estimate(
                0.90 if typed else 0.85,
                (
                    "Deterministic bootstrap perturbations quantify replicate sampling."
                    if typed
                    else "Sensitivity is conditional on the submitted scenario set."
                ),
            ),
            parameter=_estimate(
                0.88, "Parameter values are caller-declared and configuration-locked."
            ),
            model_form=_estimate(
                0.80,
                (
                    "Robust Huber IRLS finite-difference response is conditional on typed assay "
                    "replicates."
                    if typed
                    else "Deterministic bounded baseline is the declared reference model."
                ),
            ),
            identification=_estimate(0.95, "Identity and lineage controls were accepted."),
            support=_estimate(0.90, "All scenarios remained inside the declared support envelope."),
            transport=_estimate(
                0.75, "Transport beyond the declared assay envelope is not established."
            ),
            sensitivity_notes=(
                "Probabilities are support-quality indicators, not clinical probabilities.",
            ),
        )
    rationale = (
        "Simulation abstained because a required support, control, or bound invariant failed."
    )
    return UncertaintyProfile(
        measurement=_not_estimable(rationale),
        sampling=_not_estimable(rationale),
        parameter=_not_estimable(rationale),
        model_form=_not_estimable(rationale),
        identification=_not_estimable(rationale),
        support=_not_estimable(rationale),
        transport=_not_estimable(rationale),
        sensitivity_notes=("No perturbation response is emitted after abstention.",),
    )


def _evidence(reference: ArtifactReference, claim: str) -> EvidenceReference:
    return EvidenceReference(reference=reference, role="evidence", claim=claim)


def _result_evidence(
    request: SimulateBiomarkerPanelPerturbationRequest,
) -> tuple[EvidenceReference, ...]:
    values: list[EvidenceReference] = [
        _evidence(
            request.upstream_consequence_result,
            "Opaque upstream driver-to-protein consequence result.",
        ),
        *(_evidence(item, "Declared M12-06 source artifact.") for item in request.source_artifacts),
        *request.policy.configuration.evidence,
    ]
    for scenario in request.scenarios:
        values.extend(scenario.evidence)
        values.append(_evidence(scenario.source_artifact, "Declared perturbation source artifact."))
    unique: dict[str, EvidenceReference] = {item.reference.digest: item for item in values}
    return tuple(unique[key] for key in sorted(unique))


def _provenance(
    request: SimulateBiomarkerPanelPerturbationRequest,
    request_digest: str,
    configuration_digest: str,
) -> ProvenanceRecord:
    context = request.context
    controls = _control_records(context)
    input_digests = {
        request_digest,
        request.upstream_consequence_result.digest,
        configuration_digest,
        *(item.digest for item in request.source_artifacts),
        *(item.source_artifact.digest for item in request.scenarios),
        *(item.evidence_digest for item in controls),
    }
    refs = context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1206.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id=M1206_MODULE_ID,
        module_version=M1206_CONTRACT_VERSION,
        generated_at=context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _response(scenario: PerturbationScenario, lower: float, upper: float) -> PerturbationResponse:
    return PerturbationResponse(
        scenario_id=scenario.scenario_id,
        status=PerturbationResponseStatus.EVALUATED,
        metric=SensitivityMetric.ABSOLUTE_DELTA,
        baseline_response=scenario.baseline_value,
        perturbed_response=scenario.perturbed_value,
        delta=scenario.perturbed_value - scenario.baseline_value,
        envelope_lower=lower,
        envelope_upper=upper,
        evidence=scenario.evidence,
    )


def _huber_location(values: tuple[float, ...]) -> tuple[float, float]:
    """Fit a robust arm location and standard error from typed replicates.

    The iterative re-weighting is intentionally kept explicit: this is a
    finite-difference estimator over assay replicates, not a formula that
    simply copies the two caller-declared scalar values.
    """

    estimate = sum(values) / len(values)
    weights: tuple[float, ...] = (1.0,) * len(values)
    for _ in range(_HUBER_ITERATIONS):
        residuals = tuple(value - estimate for value in values)
        # Use the conventional midpoint median for even replicate counts.  The
        # upper order statistic systematically inflates the robust scale when
        # a pair of central residuals straddles an assay batch boundary,
        # weakening Huber down-weighting and making replayed intervals wider
        # than the evidence supports.
        scale = max(_MAD_SCALE_FACTOR * _median_abs(residuals), _MINIMUM_SCALE)
        weights = tuple(
            1.0 if abs(residual) / scale <= _HUBER_DELTA else _HUBER_DELTA / (abs(residual) / scale)
            for residual in residuals
        )
        denominator = max(sum(weights), _MINIMUM_SCALE)
        updated = (
            sum(weight * value for weight, value in zip(weights, values, strict=True)) / denominator
        )
        proposal = estimate + _HUBER_DAMPING * (updated - estimate)
        baseline_objective = _huber_objective(values, estimate, scale)
        proposal_objective = _huber_objective(values, proposal, scale)
        accepted = proposal
        if not math.isfinite(proposal_objective) or (
            proposal_objective > baseline_objective + _OBJECTIVE_TOLERANCE
        ):
            direction = proposal - estimate
            accepted = estimate
            step = _BACKTRACKING_FACTOR
            for _ in range(_BACKTRACKING_STEPS):
                trial = estimate + step * direction
                trial_objective = _huber_objective(values, trial, scale)
                if math.isfinite(trial_objective) and (
                    trial_objective <= baseline_objective + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    break
                step *= _BACKTRACKING_FACTOR
        if abs(accepted - estimate) <= _MINIMUM_SCALE / 100.0:
            estimate = accepted
            break
        estimate = accepted
    residuals = tuple(value - estimate for value in values)
    scale = max(_MAD_SCALE_FACTOR * _median_abs(residuals), _MINIMUM_SCALE)
    weights = tuple(
        1.0 if abs(residual) / scale <= _HUBER_DELTA else _HUBER_DELTA / (abs(residual) / scale)
        for residual in residuals
    )
    variance = sum(
        weight * residual * residual for weight, residual in zip(weights, residuals, strict=True)
    ) / max(sum(weights) - 1.0, 1.0)
    return estimate, sqrt(max(variance / len(values), _MINIMUM_SCALE**2))


def _huber_objective(values: tuple[float, ...], center: float, scale: float) -> float:
    """Evaluate the frozen-scale Huber objective used by the arm line search."""

    return float(
        sum(_huber_loss((value - center) / max(scale, _MINIMUM_SCALE)) for value in values)
    )


def _huber_loss(residual: float) -> float:
    """Return the standard Huber loss for a standardized residual."""

    absolute = abs(residual)
    return (
        0.5 * residual * residual
        if absolute <= _HUBER_DELTA
        else _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)
    )


def _median_abs(values: tuple[float, ...]) -> float:
    """Return the midpoint median of absolute residuals for a stable MAD scale."""

    ordered = sorted(abs(value) for value in values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return 0.5 * (ordered[midpoint - 1] + ordered[midpoint])


def _hash_index(seed: str, draw: int, arm: str, index: int, length: int) -> int:
    digest = hashlib.sha256(f"{seed}:{draw}:{arm}:{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % length


def _bounded_transform(value: float, lower: float, upper: float, quality: float = 1.0) -> float:
    """Map an assay location to a finite response without exponential overflow."""

    scaled = max(-60.0, min(60.0, quality * value / _RESPONSE_SCALE))
    if scaled >= 0.0:
        probability = 1.0 / (1.0 + math.exp(-scaled))
    else:
        exponential = math.exp(scaled)
        probability = exponential / (1.0 + exponential)
    return lower + (upper - lower) * probability


def _bootstrap_response_values(
    scenario: PerturbationScenario,
    request_digest: str,
    lower: float,
    upper: float,
    draws: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Generate digest-seeded response-arm bootstrap values."""

    baseline = tuple(sorted(scenario.baseline_measurements))
    perturbed = tuple(sorted(scenario.perturbed_measurements))
    baseline_draws: list[float] = []
    perturbed_draws: list[float] = []
    seed = f"{request_digest}:{scenario.scenario_id}"
    for draw in range(draws):
        baseline_sample = tuple(
            baseline[_hash_index(seed, draw, "baseline", index, len(baseline))]
            for index in range(len(baseline))
        )
        perturbed_sample = tuple(
            perturbed[_hash_index(seed, draw, "perturbed", index, len(perturbed))]
            for index in range(len(perturbed))
        )
        baseline_estimate = _huber_location(baseline_sample)[0]
        perturbed_estimate = _huber_location(perturbed_sample)[0]
        baseline_draws.append(_bounded_transform(baseline_estimate, lower, upper))
        perturbed_draws.append(_bounded_transform(perturbed_estimate, lower, upper))
    return tuple(baseline_draws), tuple(perturbed_draws)


def _bounded_from_typed_replicates(
    request: SimulateBiomarkerPanelPerturbationRequest,
    scenario: PerturbationScenario,
    request_digest: str,
) -> PerturbationResponse:
    """Compute a bounded response from robust glioma assay replicates."""

    baseline_estimate, baseline_error = _huber_location(scenario.baseline_measurements)
    perturbed_estimate, perturbed_error = _huber_location(scenario.perturbed_measurements)
    quality = scenario.quality_weight
    lower = request.policy.response_lower_bound
    upper = request.policy.response_upper_bound

    def bound(value: float) -> float:
        return _bounded_transform(value, lower, upper, quality)

    baseline_response = bound(baseline_estimate)
    perturbed_response = bound(perturbed_estimate)
    raw_delta = perturbed_estimate - baseline_estimate
    standard_error = max(sqrt(baseline_error**2 + perturbed_error**2), _MINIMUM_SCALE)
    baseline_draws, perturbed_draws = _bootstrap_response_values(
        scenario,
        request_digest,
        lower,
        upper,
        request.policy.configuration.bootstrap_replicates,
    )
    interval_values = (*baseline_draws, *perturbed_draws, baseline_response, perturbed_response)
    ordered = sorted(interval_values)
    low_index = max(0, math.ceil(_BOOTSTRAP_LOW_QUANTILE * len(ordered)) - 1)
    high_index = min(
        len(ordered) - 1,
        math.ceil(_BOOTSTRAP_HIGH_QUANTILE * len(ordered)) - 1,
    )
    interval_lower = max(lower, ordered[low_index])
    interval_upper = min(upper, ordered[high_index])
    if interval_upper <= interval_lower:
        epsilon = min(1e-6, (upper - lower) / 4.0)
        interval_lower = max(lower, interval_lower - epsilon)
        interval_upper = min(upper, interval_upper + epsilon)
        if interval_upper <= interval_lower:
            interval_lower, interval_upper = lower, upper
    rounded_baseline = float(f"{baseline_response:.8f}")
    rounded_perturbed = float(f"{perturbed_response:.8f}")
    return PerturbationResponse(
        scenario_id=scenario.scenario_id,
        status=PerturbationResponseStatus.EVALUATED,
        metric=SensitivityMetric.ABSOLUTE_DELTA,
        baseline_response=rounded_baseline,
        perturbed_response=rounded_perturbed,
        delta=rounded_perturbed - rounded_baseline,
        envelope_lower=float(f"{interval_lower:.8f}"),
        envelope_upper=float(f"{interval_upper:.8f}"),
        raw_effect_delta=float(f"{raw_delta:.8f}"),
        sensitivity_standard_error=float(f"{standard_error:.8f}"),
        replicate_count=len(scenario.baseline_measurements) + len(scenario.perturbed_measurements),
        evidence=scenario.evidence,
    )


def _finding(
    code: PerturbationFindingCode, message: str, request: SimulateBiomarkerPanelPerturbationRequest
) -> PerturbationFinding:
    return PerturbationFinding(
        finding_id=f"finding.m1206.{code.value}",
        code=code,
        message=message,
        evidence=_result_evidence(request)[:1],
    )


def _abstained(
    request: SimulateBiomarkerPanelPerturbationRequest,
    request_digest: str,
    code: PerturbationFindingCode,
    reason: str,
    *,
    typed: bool = False,
) -> BiomarkerPanelPerturbationSensitivityResult:
    configuration_digest = sha256_digest(request.policy.configuration)
    finding = _finding(code, reason, request)
    return BiomarkerPanelPerturbationSensitivityResult(
        result_id=f"result.m1206.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        request=request,
        status=SimulatorStatus.ABSTAINED,
        findings=(finding,),
        abstention_reason=reason,
        material_assumptions=tuple(sorted({item.assumption for item in request.scenarios})),
        support_decision=SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code=code.value,
            rationale=reason,
        ),
        uncertainty=_uncertainty(simulated=False, typed=typed),
        provenance=_provenance(request, request_digest, configuration_digest),
        evidence=_result_evidence(request),
        limitations=_LIMITATIONS,
        human_review_required=True,
        typed_model=typed,
        model_profile=M1206_GLIOMA_MODEL_FAMILY if typed else None,
        bootstrap_replicates=(request.policy.configuration.bootstrap_replicates if typed else None),
    )


class M1206SimulatorEngine:
    """Execute one immutable request without persistence or upstream traversal."""

    __slots__ = ()

    def simulate(self, request: object) -> BiomarkerPanelPerturbationSensitivityResult:
        preflight_m1206_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return _simulate_validated(validated)


def _simulate_validated(
    request: SimulateBiomarkerPanelPerturbationRequest,
) -> BiomarkerPanelPerturbationSensitivityResult:
    # Carry the canonical semantic order into the receipt itself, not only its
    # digest, so reordering scenarios or replicate vectors cannot change the
    # replayed result payload.
    canonical_scenarios = tuple(
        sorted(
            (
                item.model_copy(
                    update={
                        "baseline_measurements": tuple(sorted(item.baseline_measurements)),
                        "perturbed_measurements": tuple(sorted(item.perturbed_measurements)),
                    }
                )
                for item in request.scenarios
            ),
            key=lambda item: item.scenario_id,
        )
    )
    request = request.model_copy(update={"scenarios": canonical_scenarios})
    request_digest = canonical_request_digest(request)
    policy = request.policy
    typed = policy.configuration.model_family == M1206_GLIOMA_MODEL_FAMILY
    if any(item.status is not PerturbationStatus.SUPPORTED for item in request.scenarios):
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
            (
                "At least one perturbation is outside the declared support envelope; "
                "simulation abstained."
            ),
            typed=typed,
        )
    if any(
        not (policy.response_lower_bound <= item.baseline_value <= policy.response_upper_bound)
        for item in request.scenarios
    ):
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
            "A baseline response is outside the configured bounded response envelope.",
            typed=typed,
        )
    if any(
        not (policy.response_lower_bound <= item.perturbed_value <= policy.response_upper_bound)
        for item in request.scenarios
    ):
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
            "A perturbed response is outside the configured bounded response envelope.",
            typed=typed,
        )
    if typed and any(
        len(item.baseline_measurements) < M1206_MINIMUM_REPLICATES_PER_ARM
        or len(item.perturbed_measurements) < M1206_MINIMUM_REPLICATES_PER_ARM
        for item in request.scenarios
    ):
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.TYPED_INPUT_INCOMPLETE,
            (
                "The glioma perturbation response graph requires at least three baseline and "
                "three perturbed replicates for every supported scenario."
            ),
            typed=True,
        )
    try:
        responses = tuple(
            (
                _bounded_from_typed_replicates(request, item, request_digest)
                if typed
                else _response(item, policy.response_lower_bound, policy.response_upper_bound)
            )
            for item in sorted(request.scenarios, key=lambda item: item.scenario_id)
        )
    except (OverflowError, ValueError):
        if not typed:
            raise
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.TYPED_INPUT_INCOMPLETE,
            "Typed replicate values cannot be represented as a finite bounded response.",
            typed=True,
        )
    surface = SensitivitySurface(
        surface_id=f"surface.m1206.{request_digest.removeprefix('sha256:')}",
        axes=tuple(sorted({item.parameter for item in request.scenarios})),
        responses=responses,
        assumptions=tuple(sorted({item.assumption for item in request.scenarios})),
        evidence=_result_evidence(request)[:64],
    )
    configuration_digest = sha256_digest(policy.configuration)
    return BiomarkerPanelPerturbationSensitivityResult(
        result_id=f"result.m1206.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        request=request,
        status=SimulatorStatus.SIMULATED,
        sensitivity_surface=surface,
        material_assumptions=surface.assumptions,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="perturbation_support_confirmed",
            rationale="All declared perturbations are supported and bounded.",
        ),
        uncertainty=_uncertainty(simulated=True, typed=typed),
        provenance=_provenance(request, request_digest, configuration_digest),
        evidence=_result_evidence(request),
        limitations=_LIMITATIONS,
        human_review_required=False,
        typed_model=typed,
        model_profile=M1206_GLIOMA_MODEL_FAMILY if typed else None,
        bootstrap_replicates=(policy.configuration.bootstrap_replicates if typed else None),
    )


def simulate_biomarker_panel_perturbation(
    request: object,
) -> BiomarkerPanelPerturbationSensitivityResult:
    """Public stateless M12-06 entry point."""

    return M1206SimulatorEngine().simulate(request)


def verify_m1206_result(
    request: object,
    result: object,
) -> BiomarkerPanelPerturbationSensitivityResult:
    """Strictly replay a result against the exact request digest and payload."""

    preflight_m1206_authorization(request)
    validated_request = _REQUEST_ADAPTER.validate_python(request, strict=True)
    validated_result = _RESULT_ADAPTER.validate_python(result, strict=True)
    expected_request_digest = canonical_request_digest(validated_request)
    if validated_result.request_digest != expected_request_digest:
        raise M1206ReplayError
    expected = M1206SimulatorEngine().simulate(validated_request)
    if validated_result.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise M1206ReplayError
    return validated_result


__all__ = [
    "M1206AuthorizationError",
    "M1206ReplayError",
    "M1206SimulatorEngine",
    "preflight_m1206_authorization",
    "simulate_biomarker_panel_perturbation",
    "verify_m1206_result",
]
