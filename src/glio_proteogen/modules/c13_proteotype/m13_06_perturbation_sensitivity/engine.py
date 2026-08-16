"""Deterministic, schema-first M13-06 perturbation simulation.

The dossier leaves the model ABI open.  This implementation therefore evaluates
caller-declared bounded response values and never pretends to execute a kinase,
all-omics, treatment, or subtype-inference model.  Every supported response is
replayable from the request and policy; unsupported or out-of-envelope scenarios
close as an explicit abstention.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_06 import (
    M1306_CONTRACT_VERSION,
    M1306_MODULE_ID,
    M1306_PARENT,
    PerturbationFinding,
    PerturbationFindingCode,
    PerturbationResponse,
    PerturbationResponseStatus,
    PerturbationScenario,
    PerturbationStatus,
    ProteotypePerturbationSensitivityResult,
    SensitivityMetric,
    SensitivitySurface,
    SimulateProteotypePerturbationRequest,
    SimulatorStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_LIMITATIONS: Final = (
    Limitation(
        code="no_calibration",
        statement=(
            "Responses are bounded deterministic replay values, not calibrated probabilities."
        ),
    ),
    Limitation(
        code="no_biological_inference",
        statement="The simulator does not infer subtype, mechanism, identity, or treatment effect.",
    ),
    Limitation(
        code="no_kinase_or_all_omics",
        statement=(
            "Kinase activity, all-omics fusion, and treatment recommendation remain out of scope."
        ),
    ),
)


class M1306AuthorizationError(PermissionError):
    """Raised before scenario traversal when caller controls are not accepted."""

    def __init__(self) -> None:
        super().__init__("M13-06 requires accepted upstream controls")


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value[name]
    return cast("object", getattr(value, name))


def _state_text(value: object) -> str:
    return str(getattr(value, "value", value))


def preflight_m1306_authorization(candidate: object) -> None:
    """Check the seven caller controls without traversing scenario payloads."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception as error:
        raise M1306AuthorizationError from error
    if states != _EXPECTED_CONTROL_STATES:
        raise M1306AuthorizationError


def _as_request(candidate: object) -> SimulateProteotypePerturbationRequest:
    if type(candidate) is SimulateProteotypePerturbationRequest:
        return candidate
    if isinstance(candidate, Mapping):
        return TypeAdapter(SimulateProteotypePerturbationRequest).validate_python(candidate)
    raise TypeError


def _controls(request: SimulateProteotypePerturbationRequest) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    records: list[ControlDecisionRecord] = []
    for role, reference in values:
        evidence = reference.evidence
        subject_digest = getattr(reference, "binding_digest", None)
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=_state_text(reference.state),
                policy_version=reference.policy_version,
                evidence_digest=evidence.digest,
                subject_digest=subject_digest,
            )
        )
    return tuple(records)


def _uncertainty() -> UncertaintyProfile:
    dimensions = {
        "measurement": "Measurement uncertainty is not estimable from caller-declared bounds.",
        "sampling": "Sampling uncertainty is not estimable from a bounded scenario request.",
        "parameter": "Parameter uncertainty is represented only by explicit perturbations.",
        "model_form": "Model-form uncertainty is not estimable while the ABI is provisional.",
        "identification": "Identification uncertainty is inherited and not inferred here.",
        "support": "Support uncertainty is governed by the caller controls and policy envelope.",
        "transport": "Transport uncertainty is not estimable from synthetic replay evidence.",
    }
    value = UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale="placeholder")
    return UncertaintyProfile(
        **{
            name: value.model_copy(update={"rationale": rationale})
            for name, rationale in dimensions.items()
        },
        sensitivity_notes=(
            "No calibration, prevalence, clinical performance, or biological effect is estimated.",
            "Sensitivity is limited to the caller-declared perturbation envelope.",
        ),
    )


def _provenance(request: SimulateProteotypePerturbationRequest) -> ProvenanceRecord:
    input_digests = tuple(
        [request.variant_peptide_result.digest]
        + [artifact.digest for artifact in request.source_artifacts]
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1306.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1306_MODULE_ID,
        module_version=M1306_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.configuration.model_dump(mode="json")),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _finding(
    code: PerturbationFindingCode,
    message: str,
    request: SimulateProteotypePerturbationRequest,
) -> PerturbationFinding:
    evidence = request.source_artifacts[0]
    return PerturbationFinding(
        finding_id=f"finding.m1306.{code.value}",
        code=code,
        message=message,
        evidence=(
            EvidenceReference(
                reference=evidence,
                role=(
                    "evidence"
                    if code is not PerturbationFindingCode.NEGATIVE_CONTROL_FAILED
                    else "counter_evidence"
                ),
                claim="Caller-declared bounded perturbation evidence.",
            ),
        ),
    )


def _response(
    scenario: PerturbationScenario,
    request: SimulateProteotypePerturbationRequest,
) -> PerturbationResponse:
    lower = request.policy.response_lower_bound
    upper = request.policy.response_upper_bound
    baseline = scenario.baseline_value
    perturbed = scenario.perturbed_value
    if not lower <= baseline <= upper or not lower <= perturbed <= upper:
        raise ValueError
    metric = SensitivityMetric.ABSOLUTE_DELTA
    return PerturbationResponse(
        scenario_id=scenario.scenario_id,
        status=PerturbationResponseStatus.EVALUATED,
        metric=metric,
        baseline_response=baseline,
        perturbed_response=perturbed,
        delta=perturbed - baseline,
        envelope_lower=lower,
        envelope_upper=upper,
        evidence=scenario.evidence,
    )


class M1306PerturbationSensitivityEngine:
    """Execute one bounded, deterministic M13-06 request."""

    __slots__ = ()

    def compute(self, candidate: object) -> ProteotypePerturbationSensitivityResult:
        preflight_m1306_authorization(candidate)
        request = _as_request(candidate)
        request_digest = canonical_request_digest(request)
        findings: list[PerturbationFinding] = [
            _finding(
                PerturbationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The M13-06 ABI remains provisional pending owner confirmation.",
                request,
            )
        ]
        responses: list[PerturbationResponse] = []
        failure: str | None = None
        for scenario in request.scenarios:
            if scenario.status is not PerturbationStatus.SUPPORTED:
                findings.append(
                    _finding(
                        PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
                        f"Scenario {scenario.scenario_id} is not supported and cannot be scored.",
                        request,
                    )
                )
                failure = "one or more perturbation scenarios are unsupported"
                break
            try:
                responses.append(_response(scenario, request))
            except ValueError:
                findings.append(
                    _finding(
                        PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
                        (
                            f"Scenario {scenario.scenario_id} falls outside the bounded "
                            "response envelope."
                        ),
                        request,
                    )
                )
                failure = "one or more perturbation responses exceed the configured envelope"
                break
        if failure is None:
            surface = SensitivitySurface(
                surface_id=f"surface.m1306.{request_digest.removeprefix('sha256:')}",
                axes=tuple(sorted({scenario.parameter for scenario in request.scenarios})),
                responses=tuple(responses),
                assumptions=tuple(sorted({scenario.assumption for scenario in request.scenarios})),
                evidence=request.scenarios[0].evidence,
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="bounded_replay",
                rationale=(
                    "Every caller-declared scenario is supported and within the locked envelope."
                ),
            )
            status = SimulatorStatus.SIMULATED
            abstention_reason = None
        else:
            surface = None
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="explicit_abstention",
                rationale=failure,
            )
            status = SimulatorStatus.ABSTAINED
            abstention_reason = failure
        payload: dict[str, object] = {
            "output_type": "proteotype_perturbation_sensitivity",
            "result_id": f"result.m1306.{request_digest.removeprefix('sha256:')}",
            "result_version": M1306_CONTRACT_VERSION,
            "request_digest": request_digest,
            "request": request,
            "status": status,
            "sensitivity_surface": surface,
            "findings": tuple(findings),
            "abstention_reason": abstention_reason,
            "material_assumptions": tuple(
                sorted({scenario.assumption for scenario in request.scenarios})
            ),
            "parent_target": M1306_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": request.scenarios[0].evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        digest_source = ProteotypePerturbationSensitivityResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(digest_source)
        return ProteotypePerturbationSensitivityResult.model_validate(payload)


def simulate_proteotype_perturbation_sensitivity(
    candidate: object,
) -> ProteotypePerturbationSensitivityResult:
    """Public stateless M13-06 operation."""

    return M1306PerturbationSensitivityEngine().compute(candidate)


__all__ = [
    "M1306AuthorizationError",
    "M1306PerturbationSensitivityEngine",
    "preflight_m1306_authorization",
    "simulate_proteotype_perturbation_sensitivity",
]
