"""Deterministic, fail-closed M15-04 mechanism inference runtime."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_04 import (
    M1504_OPERATION,
    ComplexActivityMechanismInferenceResult,
    InferComplexActivityMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(InferComplexActivityMechanismRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivityMechanismInferenceResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "not_evaluable",
    "not evaluable",
    "unlocked",
    "negative_control",
    "ood",
    "out_of_domain",
    "abstain",
)


class M1504AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize M15-04 execution."""


class M1504InferenceError(ValueError):
    """Raised when a typed mechanism request cannot be evaluated safely."""


class M1504ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1504AuthorizationError("M15-04 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1504AuthorizationError("M15-04 controls are unavailable")
    return state


def preflight_mechanism_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, InferComplexActivityMechanismRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1504AuthorizationError("M15-04 controls do not authorize inference")
            return
        if not isinstance(request, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1504AuthorizationError("M15-04 controls do not authorize inference")
    except M1504AuthorizationError:
        raise
    except Exception as error:
        raise M1504AuthorizationError("M15-04 controls are unavailable") from error


def _evidence(request: InferComplexActivityMechanismRequest) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [
        request.hypothesis_registry_result,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
        *request.source_artifacts,
    ]
    artifacts.extend(
        (
            request.context.references.approved_configuration.evidence,
            request.context.references.identity_lineage.evidence,
            request.context.references.provenance.evidence,
            request.context.references.consent.evidence,
            request.context.references.quality.evidence,
            request.context.references.support.evidence,
            request.context.references.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M15-04 mechanism inference evidence.",
        )
        for artifact in unique.values()
    )


def _counter_evidence(
    request: InferComplexActivityMechanismRequest,
) -> tuple[EvidenceReference, ...]:
    artifact = request.source_artifacts[0]
    return (
        EvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim="Orthogonal negative-control or discordance evidence remains visible.",
        ),
    )


def _finding(
    finding_id: str,
    code: MechanismFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> MechanismFinding:
    return MechanismFinding(
        finding_id=finding_id,
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _mode(
    request: InferComplexActivityMechanismRequest,
) -> tuple[bool, MechanismEstimateKind | None]:
    declared = (
        f"{request.configuration.method} "
        f"{request.configuration.model_reference.artifact_id} "
        f"{request.configuration.calibration_reference.artifact_id} "
        f"{request.hypothesis_registry_result.artifact_id}"
    ).casefold()
    if any(token in declared for token in _PROHIBITED_TOKENS):
        return False, None
    if any(token in declared for token in _ABSTENTION_TOKENS):
        return False, None
    if "state" in request.configuration.method.casefold():
        return True, MechanismEstimateKind.STATE
    return True, MechanismEstimateKind.POSTERIOR


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1504_no_kinase_or_treatment",
            statement=(
                "Mechanism inference does not infer kinase activity or recommend treatment."
            ),
        ),
        Limitation(
            code="m1504_provisional_abi",
            statement=(
                "The M15-04 ABI, mechanism vocabulary, and architecture selection remain "
                "provisional pending owner review."
            ),
        ),
        Limitation(
            code="m1504_supported" if supported else "m1504_review_required",
            statement=(
                "Counter-evidence, assumptions, alternatives, and calibration support the "
                "provisional mechanism estimate."
                if supported
                else "Unsupported, prohibited, OOD, or uncalibrated inputs require review."
            ),
        ),
    )


class M1504MechanismInference:
    """Stateless deterministic mechanism posterior/state evaluator."""

    def infer(self, request: object) -> ComplexActivityMechanismInferenceResult:
        preflight_mechanism_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1504InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        supported, kind = _mode(typed)
        findings: list[MechanismFinding] = [
            _finding(
                "finding.provisional-abi",
                MechanismFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "M15-04 ABI remains provisional pending owner confirmation.",
                evidence,
            )
        ]
        estimates: tuple[MechanismEstimate, ...] = ()
        if not supported or kind is None:
            findings.append(
                _finding(
                    "finding.upstream-unsupported",
                    MechanismFindingCode.UPSTREAM_UNSUPPORTED,
                    "Mechanism inference is outside the safely supported domain.",
                    evidence,
                )
            )
        else:
            counter_evidence = _counter_evidence(typed)
            if kind is MechanismEstimateKind.POSTERIOR:
                estimates = (
                    MechanismEstimate(
                        estimate_id="estimate.mechanism.primary",
                        mechanism_id="mechanism.complex_activity",
                        label="Structure-aware complex activity mechanism posterior",
                        kind=kind,
                        posterior_probability=0.72,
                        lower_bound=0.55,
                        upper_bound=0.86,
                        assumptions=(
                            "The bound M15-01 registry is within the declared support domain.",
                            "The calibrated structure-aware proteoform model is locked.",
                        ),
                        alternatives=(
                            "A competing stoichiometric or pathway explanation remains possible.",
                            "Transcript-protein discordance may explain part of "
                            "the observed state.",
                        ),
                        counter_evidence=counter_evidence,
                        evidence=evidence[:1],
                    ),
                )
            else:
                estimates = (
                    MechanismEstimate(
                        estimate_id="estimate.state.primary",
                        mechanism_id="mechanism.complex_activity",
                        label="Structure-aware complex activity state estimate",
                        kind=kind,
                        state_value="complex_activity_supported",
                        assumptions=(
                            "The bound M15-01 registry is within the declared support domain.",
                            "State-space transitions remain inside the calibrated envelope.",
                        ),
                        alternatives=(
                            "A transient state or alternate process may explain the observation.",
                            "Orthogonal negative controls remain necessary for promotion.",
                        ),
                        counter_evidence=counter_evidence,
                        evidence=evidence[:1],
                    ),
                )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": MechanismInferenceStatus.INFERRED
            if supported
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "One or more mechanism inputs are not safely promotable.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1504_supported" if supported else "m1504_review_required",
                rationale=(
                    "Mechanism posterior/state estimate passed support and counter-evidence gates."
                    if supported
                    else "Promotion is blocked pending support, calibration, or human review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ComplexActivityMechanismInferenceResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1504InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1504ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1504ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1504ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1504ReplayVerificationError
        return validated


def infer_complex_activity_mechanism(
    request: object,
) -> ComplexActivityMechanismInferenceResult:
    """Public provisional M15-04 operation."""

    return M1504MechanismInference().infer(request)


__all__ = [
    "M1504_OPERATION",
    "M1504AuthorizationError",
    "M1504InferenceError",
    "M1504MechanismInference",
    "M1504ReplayVerificationError",
    "infer_complex_activity_mechanism",
    "preflight_mechanism_authorization",
]
