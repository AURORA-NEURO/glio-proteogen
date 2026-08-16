"""Deterministic, replay-bound M15-06 sensitivity simulation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_06 import (
    M1506_CONTRACT_VERSION,
    M1506_EVIDENCE_CLAIM,
    M1506_PARENT,
    ComplexActivitySensitivitySimulationResult,
    PerturbationKind,
    PerturbationResponseStatus,
    SensitivityDiagnostic,
    SensitivityDiagnosticStatus,
    SensitivityFindingCode,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateComplexActivityPerturbationsRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m15_06.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateComplexActivityPerturbationsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySensitivitySimulationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_MODELS: Final = frozenset(
    {
        "curated_rule",
        "enrichment",
        "mechanistic_baseline",
        "bayesian_graph",
        "state_space",
        "mechanistic_model",
        "foundation_assisted",
        "orthogonal_consensus",
    }
)
_MAX_ABS_RESPONSE: Final = 10.0


class M1506AuthorizationError(PermissionError):
    """Caller controls do not authorize sensitivity simulation."""

    def __init__(self) -> None:
        super().__init__(
            "M15-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1506ReplayVerificationError(ValueError):
    """A sensitivity result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-06 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1506_authorization(candidate: object) -> None:
    """Check all seven controls before traversing perturbation material."""

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
        raise M1506AuthorizationError from None
    if states != expected:
        raise M1506AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1506_authorization(candidate)
    return candidate


def _evidence(
    request: SimulateComplexActivityPerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
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
    for perturbation in request.perturbations:
        artifacts.extend(item.reference for item in perturbation.evidence)
        if perturbation.alternative_prior is not None:
            artifacts.append(perturbation.alternative_prior)
        if perturbation.assay_artifact is not None:
            artifacts.append(perturbation.assay_artifact)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1506_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _failure_diagnostic(
    code: SensitivityDiagnosticStatus, message: str, evidence: tuple[EvidenceReference, ...]
) -> SensitivityDiagnostic:
    return SensitivityDiagnostic(
        diagnostic_id="diagnostic.m1506",
        status=code,
        message=message,
        evidence=evidence,
    )


def _evaluate_request(
    request: SimulateComplexActivityPerturbationsRequest,
) -> tuple[bool, SensitivityFindingCode | None, str | None]:
    if request.configuration.model_family not in _SUPPORTED_MODELS:
        return (
            False,
            SensitivityFindingCode.UPSTREAM_UNSUPPORTED,
            "Model family is outside the closed sensitivity support domain.",
        )
    for perturbation in request.perturbations:
        if (
            perturbation.kind is PerturbationKind.MECHANISM_STRESS
            and "negative control" not in perturbation.rationale.lower()
        ):
            return (
                False,
                SensitivityFindingCode.NEGATIVE_CONTROL_FAILED,
                "Mechanism stress perturbations require explicit negative-control gating.",
            )
        try:
            baseline = float(perturbation.baseline_value)
            perturbed = float(perturbation.perturbed_value)
        except ValueError:
            return (
                False,
                SensitivityFindingCode.INPUT_INCOMPLETE,
                "Perturbation values must be numeric for the deterministic bounded simulator.",
            )
        if abs(perturbed - baseline) > _MAX_ABS_RESPONSE:
            return (
                False,
                SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE,
                "Perturbation response exceeds the declared bounded envelope.",
            )
    return True, None, None


def _surface(
    request: SimulateComplexActivityPerturbationsRequest,
    evidence: tuple[EvidenceReference, ...],
) -> SensitivitySurface:
    responses: list[SensitivityResponse] = []
    for perturbation in request.perturbations:
        baseline = float(perturbation.baseline_value)
        perturbed = float(perturbation.perturbed_value)
        response = perturbed - baseline
        responses.append(
            SensitivityResponse(
                scenario_id=perturbation.perturbation_id,
                status=PerturbationResponseStatus.BOUNDED,
                response_value=response,
                lower_bound=response - 0.01,
                upper_bound=response + 0.01,
                assumptions=(
                    "Caller-declared numeric perturbation values are deterministic inputs.",
                    "The bounded interval is a software envelope and not biological calibration.",
                ),
                evidence=evidence[:1],
            )
        )
    return SensitivitySurface(
        surface_id="surface.m1506",
        version=request.configuration.version,
        baseline_result=request.upstream_result,
        perturbations=request.perturbations,
        responses=tuple(responses),
        configuration=request.configuration,
        evidence=evidence,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_perturbations",
            statement=(
                "Perturbation values and evidence are caller-declared and not externally "
                "authenticated."
            ),
        ),
        Limitation(
            code="software_envelope",
            statement=(
                "Bounds are deterministic software envelopes, not biological calibration or "
                "treatment effect estimates."
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
                statement="No sensitivity surface is published outside the closed support domain.",
            )
        )
    return tuple(values)


class M1506SensitivitySimulatorEngine:
    """Simulate bounded perturbation responses with replay and safe abstention."""

    __slots__ = ()

    def infer(self, request: object) -> ComplexActivitySensitivitySimulationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: SimulateComplexActivityPerturbationsRequest
    ) -> ComplexActivitySensitivitySimulationResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, failure_code, failure_message = _evaluate_request(request)
        surface = _surface(request, evidence) if supported else None
        diagnostics = (
            (
                _failure_diagnostic(
                    SensitivityDiagnosticStatus.PASS,
                    "All perturbations are bounded and assumptions are explicit.",
                    evidence,
                ),
            )
            if supported
            else (
                _failure_diagnostic(
                    SensitivityDiagnosticStatus.FAIL,
                    failure_message or "Sensitivity request was not safely evaluable.",
                    evidence,
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_sensitivity_surface",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1506_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": SensitivitySimulationStatus.SIMULATED
            if supported
            else SensitivitySimulationStatus.ABSTAINED,
            "surface": surface,
            "diagnostics": diagnostics,
            "findings": ()
            if supported
            else (failure_code or SensitivityFindingCode.INPUT_INCOMPLETE,),
            "abstention_reason": None
            if supported
            else (failure_message or "Sensitivity request was not safely evaluable."),
            "parent_target": M1506_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1506_simulation_supported"
                if supported
                else "m1506_simulation_abstained",
                rationale="All perturbations have bounded responses and explicit assumptions."
                if supported
                else "The perturbation request is outside the safely simulated support domain.",
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ComplexActivitySensitivitySimulationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ComplexActivitySensitivitySimulationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1506ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1506ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1506ReplayVerificationError
        return validated


def simulate_complex_activity_perturbations(
    request: object,
) -> ComplexActivitySensitivitySimulationResult:
    """Public provisional M15-06 operation."""

    return M1506SensitivitySimulatorEngine().infer(request)


__all__ = [
    "M1506AuthorizationError",
    "M1506ReplayVerificationError",
    "M1506SensitivitySimulatorEngine",
    "preflight_m1506_authorization",
    "simulate_complex_activity_perturbations",
]
