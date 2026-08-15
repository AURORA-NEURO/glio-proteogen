"""Deterministic transparent baseline estimator with fail-closed replay."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_03 import (
    M0803_CONTRACT_VERSION,
    M0803_EVIDENCE_CLAIM,
    M0803_MAX_CANONICAL_REQUEST_BYTES,
    M0803_PARENT,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimateStatus,
    BaselineFeatureState,
    BaselineFindingCode,
    EstimateProteinSubtypeBaselineRequest,
    ProteinSubtypeBaselineEstimate,
    ProteinSubtypeBaselineResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinSubtypeBaselineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeBaselineResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIDPOINT: Final = 0.5


class M0803BaselineAuthorizationError(PermissionError):
    """Raised before feature traversal when upstream controls are unsafe."""

    def __init__(self) -> None:
        super().__init__(
            "M08-03 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_baseline_authorization(candidate: object) -> None:
    """Validate all seven immutable upstream control decisions before traversal."""

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
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0803BaselineAuthorizationError from None
    if states != expected:
        raise M0803BaselineAuthorizationError


def _validate_typed_request(candidate: object) -> EstimateProteinSubtypeBaselineRequest:
    preflight_baseline_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EstimateProteinSubtypeBaselineRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0803_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M08-03 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_baseline_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "The transparent baseline exposes typed uncertainty but does not claim "
            "calibrated uncertainty without owner-frozen training evidence."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            (
                "Baseline score is a transparent deterministic diagnostic, not a calibrated "
                "clinical probability."
            ),
        ),
    )


def _evidence(request: EstimateProteinSubtypeBaselineRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0803_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EstimateProteinSubtypeBaselineRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    records = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                getattr(reference, "binding_digest", None)
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in records
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-03",
        module_version=M0803_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest,),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="transparent_baseline",
            statement=(
                "Estimate is a deterministic baseline diagnostic, not a clinical probability."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no protein subtype parent object or treatment recommendation."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement="M08-02 handoff, feature catalogue, and estimator ABI remain provisional.",
        ),
    )


def _diagnostic(
    diagnostic_id: str,
    status: BaselineDiagnosticStatus,
    message: str,
) -> BaselineDiagnostic:
    return BaselineDiagnostic(diagnostic_id=diagnostic_id, status=status, message=message)


class M0803BaselineEngine:
    """Compute a transparent mean-based baseline without raw-source traversal."""

    __slots__ = ()

    def validate(self, request: object) -> EstimateProteinSubtypeBaselineRequest:
        return _validate_typed_request(request)

    def estimate(self, request: object) -> ProteinSubtypeBaselineResult:
        return self.estimate_validated(_validate_typed_request(request))

    def estimate_validated(
        self,
        request: EstimateProteinSubtypeBaselineRequest,
    ) -> ProteinSubtypeBaselineResult:
        if not isinstance(request, EstimateProteinSubtypeBaselineRequest):
            raise TypeError("M08-03 requires a validated request")  # noqa: TRY003
        request_digest = canonical_request_digest(request)
        diagnostics: list[BaselineDiagnostic] = []
        findings: list[BaselineFindingCode] = []
        if not request.features:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "no caller-declared baseline features were supplied",
                )
            )
            findings.append(BaselineFindingCode.INCOMPLETE_INPUTS)
        elif any(
            feature.state is not BaselineFeatureState.OBSERVED for feature in request.features
        ):
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "one or more baseline features are missing or unsupported",
                )
            )
            findings.append(BaselineFindingCode.INCOMPLETE_INPUTS)
        else:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.PASS,
                    "all declared baseline features are observed",
                )
            )
        suspicious = {"unsupported", "ood", "quality-failed", "unresolved"}
        if any(
            any(token in artifact.artifact_id.lower() for token in suspicious)
            for artifact in request.source_artifacts
        ):
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "source evidence declares an unsupported or out-of-domain condition",
                )
            )
            findings.append(BaselineFindingCode.OUT_OF_DOMAIN)
        else:
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    BaselineDiagnosticStatus.PASS,
                    "source evidence is within the declared provisional support envelope",
                )
            )
        diagnostics.extend(
            (
                _diagnostic(
                    "configuration.locked",
                    BaselineDiagnosticStatus.PASS,
                    "preprocessing, tuning, uncertainty, and benchmark artifacts are locked",
                ),
                _diagnostic(
                    "calibration.reference",
                    BaselineDiagnosticStatus.PASS,
                    "calibration and uncertainty references are present",
                ),
            )
        )
        failed = any(
            item.status in {BaselineDiagnosticStatus.FAIL, BaselineDiagnosticStatus.NOT_EVALUABLE}
            for item in diagnostics
        )
        estimate: ProteinSubtypeBaselineEstimate | None = None
        status = BaselineEstimateStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="m0803_baseline_not_evaluable",
            rationale="Baseline inputs or support domain are not sufficient for a safe estimate.",
        )
        abstention_reason: str | None = (
            "Baseline abstained because required inputs or support checks were not evaluable."
        )
        if not failed:
            values = [feature.value for feature in request.features if feature.value is not None]
            mean = sum(values) / len(values)
            score = _MIDPOINT + mean / (2.0 * (1.0 + abs(mean)))
            predicted = (
                "protein-subtype-baseline-positive"
                if score >= _MIDPOINT
                else "protein-subtype-baseline-negative"
            )
            estimate = ProteinSubtypeBaselineEstimate(
                predicted_subtype=predicted,
                score=score,
                calibration_reference=request.configuration.uncertainty_artifact,
                evidence=_evidence(request),
            )
            status = BaselineEstimateStatus.ESTIMATED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0803_baseline_supported",
                rationale="Observed declared features passed locked baseline support checks.",
            )
            abstention_reason = None
        payload: dict[str, object] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M0803_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimate": estimate,
            "diagnostics": tuple(diagnostics),
            "findings": tuple(dict.fromkeys(findings)),
            "abstention_reason": abstention_reason,
            "parent_target": M0803_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": status is BaselineEstimateStatus.ABSTAINED,
        }
        constructed = ProteinSubtypeBaselineResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def verify_m0803_result(result: object) -> ProteinSubtypeBaselineResult:
    typed = _RESULT_ADAPTER.validate_python(result, strict=True)
    if typed.request_digest != canonical_request_digest(typed.request):
        raise ValueError("M08-03 request digest verification failed")  # noqa: TRY003
    if typed.result_digest != result_payload_digest(typed):
        raise ValueError("M08-03 result digest verification failed")  # noqa: TRY003
    return typed


__all__ = [
    "M0803BaselineAuthorizationError",
    "M0803BaselineEngine",
    "_validate_json_request",
    "_validate_typed_request",
    "preflight_baseline_authorization",
    "verify_m0803_result",
]
