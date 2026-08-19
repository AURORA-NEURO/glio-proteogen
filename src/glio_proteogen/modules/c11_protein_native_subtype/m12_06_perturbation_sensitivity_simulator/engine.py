"""Pure, deterministic M12-06 bounded perturbation execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_06 import (
    M1206_CONTRACT_VERSION,
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


def _uncertainty(*, simulated: bool) -> UncertaintyProfile:
    if simulated:
        return UncertaintyProfile(
            measurement=_estimate(0.90, "Declared assay perturbation units are bounded."),
            sampling=_estimate(0.85, "Sensitivity is conditional on the submitted scenario set."),
            parameter=_estimate(
                0.88, "Parameter values are caller-declared and configuration-locked."
            ),
            model_form=_estimate(
                0.80, "Deterministic bounded baseline is the declared reference model."
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
        uncertainty=_uncertainty(simulated=False),
        provenance=_provenance(request, request_digest, configuration_digest),
        evidence=_result_evidence(request),
        limitations=_LIMITATIONS,
        human_review_required=True,
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
    request_digest = canonical_request_digest(request)
    policy = request.policy
    if any(item.status is not PerturbationStatus.SUPPORTED for item in request.scenarios):
        return _abstained(
            request,
            request_digest,
            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
            (
                "At least one perturbation is outside the declared support envelope; "
                "simulation abstained."
            ),
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
        )
    responses = tuple(
        _response(item, policy.response_lower_bound, policy.response_upper_bound)
        for item in sorted(request.scenarios, key=lambda item: item.scenario_id)
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
        uncertainty=_uncertainty(simulated=True),
        provenance=_provenance(request, request_digest, configuration_digest),
        evidence=_result_evidence(request),
        limitations=_LIMITATIONS,
        human_review_required=False,
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
    """Strictly replay a result against the exact request and full payload.

    Request-digest equality alone permits a caller to alter a result projection
    (for example material assumptions) and recompute its envelope digest.  The
    simulator is deterministic, so compare the complete re-execution result as
    well as the request binding.
    """

    preflight_m1206_authorization(request)
    validated_request = _REQUEST_ADAPTER.validate_python(request, strict=True)
    validated_result = _RESULT_ADAPTER.validate_python(result, strict=True)
    expected_request_digest = canonical_request_digest(validated_request)
    if validated_result.request_digest != expected_request_digest:
        raise M1206ReplayError
    expected_result = _simulate_validated(validated_request)
    if expected_result.model_dump(mode="json") != validated_result.model_dump(mode="json"):
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
