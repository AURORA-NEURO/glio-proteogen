"""Deterministic, replay-bound M14-06 perturbation simulation runtime.

The dossier does not freeze a numerical model ABI.  This implementation uses a
closed caller-declared numeric perturbation grammar and never opens opaque
artifacts.  It emits a bounded sensitivity surface only when every scenario is
supported, finite, and authorized; otherwise it abstains safely.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_06 import (
    M1406_CONTRACT_VERSION,
    M1406_EVIDENCE_CLAIM,
    M1406_PARENT,
    PerturbationResponseStatus,
    PerturbationSpecification,
    ProteinSubtypeSensitivitySimulationResult,
    SensitivityDiagnostic,
    SensitivityDiagnosticStatus,
    SensitivityFindingCode,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateProteinSubtypePerturbationsRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_06.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateProteinSubtypePerturbationsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeSensitivitySimulationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_FAMILIES: Final = frozenset(
    {
        "curated_rule",
        "bayesian_graph",
        "state_space",
        "mechanistic_baseline",
        "proteome_autoencoder",
        "foundation_assisted",
        "orthogonal_consensus",
    }
)
_MISSING_VALUES: Final = frozenset({"", "na", "n/a", "missing", "null", "unsupported"})


class M1406SensitivityAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize sensitivity simulation."""

    def __init__(self) -> None:
        super().__init__(
            "M14-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1406ReplayVerificationError(ValueError):
    """A sensitivity result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-06 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_sensitivity_authorization(candidate: object) -> None:
    """Check all seven controls before opaque traversal or numeric parsing."""

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
        raise M1406SensitivityAuthorizationError from None
    if states != expected:
        raise M1406SensitivityAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_sensitivity_authorization(candidate)
    return candidate


def _all_evidence(
    request: SimulateProteinSubtypePerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
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
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1406_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: SimulateProteinSubtypePerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim=(
                "Caller-declared negative-control and counter-evidence reference; "
                "issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts[:64]
    )


def _decimal(value: str) -> Decimal | None:
    if value.strip().lower() in _MISSING_VALUES:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _response(
    perturbation: PerturbationSpecification,
    *,
    evidence: tuple[EvidenceReference, ...],
    counter_evidence: tuple[EvidenceReference, ...],
) -> SensitivityResponse | None:
    baseline = _decimal(perturbation.baseline_value)
    perturbed = _decimal(perturbation.perturbed_value)
    if baseline is None or perturbed is None or not counter_evidence:
        return None
    denominator = max(abs(baseline), Decimal(1))
    effect = abs(perturbed - baseline) / denominator
    response = float(effect)
    lower = max(Decimal(0), effect * Decimal("0.9"))
    upper = effect * Decimal("1.1")
    perturbation_evidence = list(evidence) + list(perturbation.evidence)
    if perturbation.alternative_prior is not None:
        perturbation_evidence.append(
            EvidenceReference(
                reference=perturbation.alternative_prior,
                role="evidence",
                claim="Caller-declared alternative prior for sensitivity stress testing.",
            )
        )
    if perturbation.assay_artifact is not None:
        perturbation_evidence.append(
            EvidenceReference(
                reference=perturbation.assay_artifact,
                role="evidence",
                claim="Caller-declared assay perturbation artifact.",
            )
        )
    return SensitivityResponse(
        scenario_id=perturbation.perturbation_id,
        status=PerturbationResponseStatus.BOUNDED,
        response_value=response,
        lower_bound=float(lower),
        upper_bound=float(upper),
        assumptions=(
            (
                "The locked configuration and caller-declared numeric perturbation values "
                "are treated as opaque evidence."
            ),
            (
                "The response is a deterministic sensitivity magnitude, not a treatment "
                "recommendation."
            ),
        ),
        counter_evidence=counter_evidence,
        evidence=tuple(perturbation_evidence[:64]),
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="counter_evidence_preserved",
            statement=(
                "Assumptions, alternative priors, assay references, and counter-evidence "
                "remain attached."
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
                    "No sensitivity response is published outside the closed numeric "
                    "support domain."
                ),
            )
        )
    return tuple(values)


class M1406SensitivityEngine:
    """Simulate caller-declared perturbations with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeSensitivitySimulationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: SimulateProteinSubtypePerturbationsRequest
    ) -> ProteinSubtypeSensitivitySimulationResult:
        request_hash = canonical_request_digest(request)
        evidence = _all_evidence(request)
        counter_evidence = _counter_evidence(request)
        supported = request.configuration.model_family in _SUPPORTED_FAMILIES
        responses: list[SensitivityResponse] = []
        failure_code: SensitivityFindingCode | None = None
        failure_message: str | None = None
        if len(request.perturbations) > request.configuration.maximum_scenarios:
            supported = False
            failure_code = SensitivityFindingCode.INPUT_INCOMPLETE
            failure_message = "Perturbation count exceeds the locked scenario budget."
        elif not supported:
            failure_code = SensitivityFindingCode.METHOD_OUTSIDE_SUPPORT
            failure_message = "Model family is outside the declared deterministic support domain."
        else:
            for perturbation in request.perturbations:
                response = _response(
                    perturbation,
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                )
                if response is None:
                    supported = False
                    failure_code = SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE
                    failure_message = (
                        "Perturbation values are missing, non-finite, unsupported, or "
                        "lack counter-evidence."
                    )
                    break
                responses.append(response)
        if supported:
            surface = SensitivitySurface(
                surface_id=f"surface.{request_hash.removeprefix('sha256:')}",
                version=M1406_CONTRACT_VERSION,
                baseline_result=request.upstream_result,
                perturbations=request.perturbations,
                responses=tuple(responses),
                configuration=request.configuration,
                evidence=evidence,
            )
            diagnostics = tuple(
                SensitivityDiagnostic(
                    diagnostic_id=f"diagnostic.{item.scenario_id}",
                    status=SensitivityDiagnosticStatus.PASS,
                    message=(
                        "Perturbation response is finite, bounded, and counter-evidence attached."
                    ),
                    evidence=item.evidence,
                )
                for item in responses
            )
            findings: tuple[SensitivityFindingCode, ...] = ()
            abstention_reason = None
        else:
            surface = None
            code = failure_code or SensitivityFindingCode.INPUT_INCOMPLETE
            message = failure_message or "Sensitivity simulation was not safely evaluable."
            diagnostics = (
                SensitivityDiagnostic(
                    diagnostic_id=f"diagnostic.{request.request_id}",
                    status=SensitivityDiagnosticStatus.NOT_EVALUABLE,
                    message=message,
                    evidence=evidence,
                ),
            )
            findings = (code,)
            abstention_reason = message
        payload: dict[str, object] = {
            "output_type": "protein_subtype_sensitivity_surface",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1406_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": SensitivitySimulationStatus.SIMULATED
            if supported
            else SensitivitySimulationStatus.ABSTAINED,
            "surface": surface,
            "diagnostics": diagnostics,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": M1406_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1406_sensitivity_simulated"
                if supported
                else "m1406_sensitivity_abstained",
                rationale=(
                    "All locked perturbations are finite and bounded with counter-evidence."
                    if supported
                    else "The request is outside the safely evaluable perturbation support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinSubtypeSensitivitySimulationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeSensitivitySimulationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1406ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1406ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1406ReplayVerificationError
        return validated


def simulate_protein_subtype_perturbations(
    request: object,
) -> ProteinSubtypeSensitivitySimulationResult:
    """Public provisional M14-06 operation."""

    return M1406SensitivityEngine().infer(request)


__all__ = [
    "M1406ReplayVerificationError",
    "M1406SensitivityAuthorizationError",
    "M1406SensitivityEngine",
    "preflight_sensitivity_authorization",
    "result_payload_digest",
    "simulate_protein_subtype_perturbations",
]
