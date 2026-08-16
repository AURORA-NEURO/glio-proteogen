"""Strict replay and execution boundary for the provisional M06-03 estimator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_01 import (
    FormalStateValidationStatus,
)
from glio_proteogen.contracts.m06_03 import (
    M0603_CONTRACT_VERSION,
    M0603_EVIDENCE_CLAIM,
    M0603_MAX_CANONICAL_REQUEST_BYTES,
    M0603_MODULE_ID,
    M0603_PARENT,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineResultStatus,
    EstimateProteinAbundanceBaselineRequest,
    EstimateProteinAbundanceBaselineResult,
)
from glio_proteogen.contracts.m06_03.canonical import (
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
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.kernel import (
    M0603BaselineKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceBaselineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceBaselineResult)


class PtmBaselineAuthorizationError(PermissionError):
    """The seven caller-declared controls do not authorize baseline execution."""

    def __init__(self, message: str = "M06-03 authorization failed") -> None:
        super().__init__(message)


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0603_authorization(candidate: object) -> None:
    """Check all controls before formal-state or feature traversal."""

    if not isinstance(candidate, Mapping) and not isinstance(
        candidate, EstimateProteinAbundanceBaselineRequest
    ):
        raise PtmBaselineAuthorizationError
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
    except Exception as error:
        raise PtmBaselineAuthorizationError from error
    if states != expected:
        raise PtmBaselineAuthorizationError


def _validate_typed_request(candidate: object) -> EstimateProteinAbundanceBaselineRequest:
    preflight_m0603_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EstimateProteinAbundanceBaselineRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0603_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M06-03 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_m0603_authorization(candidate)
    body = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(body, strict=True)


def _uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable("No measurement error model is installed."),
        sampling=unavailable("No sampling design is supplied."),
        parameter=unavailable("No fitted baseline parameters are installed."),
        model_form=unavailable("Estimator family is transparent, not calibrated."),
        identification=unavailable("Feature identity authority remains caller-declared."),
        support=unavailable("Support is inherited from formal-state validation."),
        transport=unavailable("No transport or external-content model is installed."),
        sensitivity_notes=(
            "Missing and unsupported formal-state values abstain.",
            "Estimates are aggregate caller-declared values, not measurements.",
        ),
    )


def _provenance(request: EstimateProteinAbundanceBaselineRequest, digest: str) -> ProvenanceRecord:
    refs = request.context.references
    entries = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration, None),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage, refs.identity_lineage.binding_digest),
        (ControlRole.PROVENANCE, refs.provenance, None),
        (ControlRole.CONSENT, refs.consent, None),
        (ControlRole.QUALITY, refs.quality, None),
        (ControlRole.SUPPORT, refs.support, None),
        (ControlRole.INTENDED_USE, refs.intended_use, None),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0603.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0603_MODULE_ID,
        module_version=M0603_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request.formal_state_result.result_digest,
                    *(item.digest for item in request.source_artifacts),
                }
            )
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
                subject_digest=subject,
            )
            for role, reference, subject in entries
        ),
    )


def _evidence(request: EstimateProteinAbundanceBaselineRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M0603_EVIDENCE_CLAIM)
        for reference in request.source_artifacts
    )


class M0603MatureBaselineEngine:
    """Replay M06-01, then execute transparent baseline reduction."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0603BaselineKernel | None = None) -> None:
        self._kernel = kernel or M0603BaselineKernel()

    def estimate(self, request: object) -> EstimateProteinAbundanceBaselineResult:
        return self.estimate_validated(_validate_typed_request(request))

    def estimate_validated(
        self,
        request: EstimateProteinAbundanceBaselineRequest,
    ) -> EstimateProteinAbundanceBaselineResult:
        if not isinstance(request, EstimateProteinAbundanceBaselineRequest):
            raise TypeError(  # noqa: TRY003
                "M06-03 validated execution requires the declared request type"
            )
        state_result = request.formal_state_result
        if state_result.request_digest != canonical_request_digest(state_result.request):
            raise ValueError("M06-01 result digest is stale")  # noqa: TRY003
        if state_result.request.state_schema != request.state_schema:
            raise ValueError("M06-01 schema replay does not bind the request")  # noqa: TRY003
        if state_result.request.values != request.feature_values:
            raise ValueError("M06-01 feature replay does not bind the request")  # noqa: TRY003
        return self._result(request)

    def _result(
        self,
        request: EstimateProteinAbundanceBaselineRequest,
    ) -> EstimateProteinAbundanceBaselineResult:
        request_digest = canonical_request_digest(request)
        diagnostics: tuple[BaselineDiagnostic, ...] = ()
        estimates: tuple[Any, ...] = ()
        reason: str | None = None
        if request.formal_state_result.status is not FormalStateValidationStatus.VALID:
            status = BaselineResultStatus.ABSTAINED
            estimates = ()
            reason = "M06-01 formal-state result is not valid"
            diagnostics = (
                BaselineDiagnostic(
                    diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}",
                    status=BaselineDiagnosticStatus.NOT_EVALUABLE,
                    message=reason,
                ),
            )
        else:
            output = self._kernel.estimate(request)
            estimates = output.estimates
            diagnostics = output.diagnostics
            reason = output.abstention_reason
            status = BaselineResultStatus.ABSTAINED if reason else BaselineResultStatus.ESTIMATED
        support_status = (
            SupportStatus.SUPPORTED
            if status is BaselineResultStatus.ESTIMATED
            else SupportStatus.REVIEW_REQUIRED
        )
        support = SupportDecision(
            status=support_status,
            reason_code=("m0603_estimate_completed" if reason is None else "m0603_safe_abstention"),
            rationale=(
                "Transparent mature-baseline reduction completed."
                if reason is None
                else reason
            ),
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M0603_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": request,
            "status": status,
            "estimates": estimates,
            "diagnostics": diagnostics,
            "abstention_reason": reason,
            "parent_target": M0603_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": _evidence(request),
            "limitations": (
                Limitation(
                    code="aggregate_baseline_only",
                    statement="The result is an aggregate baseline estimate only.",
                ),
                Limitation(
                    code="no_calibrated_probability",
                    statement="No calibrated probability or clinical interpretation is emitted.",
                ),
            ),
        }
        constructed = cast("Any", EstimateProteinAbundanceBaselineResult.model_construct)(
            **payload
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def estimate_protein_abundance_baseline(
    request: object,
) -> EstimateProteinAbundanceBaselineResult:
    return M0603MatureBaselineEngine().estimate(request)


__all__ = [
    "M0603MatureBaselineEngine",
    "PtmBaselineAuthorizationError",
    "_validate_json_request",
    "estimate_protein_abundance_baseline",
    "preflight_m0603_authorization",
]
