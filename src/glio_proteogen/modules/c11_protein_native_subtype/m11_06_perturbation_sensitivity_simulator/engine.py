"""Deterministic, safety-gated M11-06 sensitivity simulation runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_06 import (
    M1106_CONTRACT_VERSION,
    M1106_EVIDENCE_CLAIM,
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
from glio_proteogen.kernel.canonical import canonical_json_bytes
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


def _bounded_response(
    request: SimulateVariantPeptidePerturbationsRequest,
    perturbation: PerturbationSpecification,
) -> SensitivityResponse:
    """Derive a deterministic bounded response from declared inputs only."""

    material = canonical_json_bytes(
        {
            "module": "GLIO-PROTEOGEN-M11-06",
            "upstream": request.upstream_result.digest,
            "perturbation": perturbation,
        }
    )
    fraction = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") / 2**64
    value = round((fraction * 2.0) - 1.0, 6)
    half_width = 0.2
    lower = round(max(-1.0, value - half_width), 6)
    upper = round(min(1.0, value + half_width), 6)
    return SensitivityResponse(
        scenario_id=perturbation.perturbation_id,
        status=PerturbationResponseStatus.BOUNDED,
        response_value=value,
        lower_bound=lower,
        upper_bound=upper,
        assumptions=(
            "The locked provisional response envelope is used.",
            "Caller-declared evidence references are not interpreted or mutated.",
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
            statement="External artifacts remain immutable references and are never traversed.",
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
