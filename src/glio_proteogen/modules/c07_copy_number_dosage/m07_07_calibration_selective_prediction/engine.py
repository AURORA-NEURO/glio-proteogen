"""Deterministic calibration and selective-prediction runtime for M07-07.

The dossier does not freeze a model, a calibration artefact catalogue, or a
public endpoint.  This runtime therefore consumes only caller-declared,
content-addressed candidates and never invents an estimate from raw inputs or
an artifact identifier.  A candidate is selectable only when the complete
M07-06 upstream result is supported, its sensitivity envelope is evaluated,
all four required calibration strata pass the provisional gate, and the
candidate's support/OOD/calibration values pass the locked threshold.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_06 import (
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionStatus,
)
from glio_proteogen.contracts.m07_07 import (
    M0707_CONTRACT_VERSION,
    M0707_EVIDENCE_CLAIM,
    M0707_MAX_CALIBRATION_ERROR,
    M0707_MAX_COVERAGE,
    M0707_MIN_COVERAGE,
    M0707_MODULE_ID,
    M0707_NOMINAL_COVERAGE,
    M0707_PARENT,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
    CalibrationDiagnostic,
    CalibrationStatus,
    CalibrationStratumDimension,
    OutOfDistributionStatus,
    SelectiveCandidate,
    SelectivePredictionStatus,
)
from glio_proteogen.contracts.m07_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveCopyNumberDosageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(CalibrateSelectiveCopyNumberDosageResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_REQUIRED_DIMENSIONS: Final = frozenset(CalibrationStratumDimension)


class CalibrationAuthorizationError(PermissionError):
    """Raised before an unauthorized calibration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M07-07 calibration request is not authorized")


class CalibrationInputError(ValueError):
    """Raised for malformed request objects outside the strict request ABI."""


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_calibration_authorization(request: object) -> None:
    """Check consent, identity, and every operational control first."""

    try:
        context = _member(request, "context")
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
        raise CalibrationAuthorizationError from None
    if states != expected:
        raise CalibrationAuthorizationError


def _evidence(request: CalibrateSelectiveCopyNumberDosageRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0707_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_candidates",
            statement="Candidates are caller-declared and are not inferred from raw artifacts.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, treatment recommendation, or parent proteotype."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement="The M07-07 ABI, metric catalogue, and coverage ceiling remain provisional.",
        ),
    )


def _provenance(
    request: CalibrateSelectiveCopyNumberDosageRequest,
    request_digest: str,
    policy_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0707_MODULE_ID,
        module_version=M0707_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.uncertainty_result.result_digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=policy_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _upstream_ready(request: CalibrateSelectiveCopyNumberDosageRequest) -> bool:
    upstream = request.uncertainty_result
    envelope = upstream.sensitivity_envelope
    return bool(
        upstream.status is UncertaintyDecompositionStatus.DECOMPOSED
        and upstream.support_decision.status is SupportStatus.SUPPORTED
        and envelope.status is SensitivityEnvelopeStatus.EVALUATED
        and envelope.observed_coverage is not None
        and M0707_MIN_COVERAGE <= envelope.observed_coverage <= M0707_MAX_COVERAGE
    )


def _policy_ready(request: CalibrateSelectiveCopyNumberDosageRequest) -> bool:
    policy = request.policy
    if policy.target_coverage != M0707_NOMINAL_COVERAGE:
        return False
    if {stratum.dimension for stratum in policy.strata} != _REQUIRED_DIMENSIONS:
        return False
    for stratum in policy.strata:
        if stratum.sample_count <= 0 or stratum.observed_coverage is None:
            return False
        if not M0707_MIN_COVERAGE <= stratum.observed_coverage <= M0707_MAX_COVERAGE:
            return False
        if (
            stratum.calibration_error is None
            or stratum.calibration_error > M0707_MAX_CALIBRATION_ERROR
        ):
            return False
    threshold = policy.support_threshold
    return (
        threshold.target_coverage == policy.target_coverage
        and threshold.maximum_calibration_error <= M0707_MAX_CALIBRATION_ERROR
    )


def _candidate_diagnostic(
    candidate: SelectiveCandidate,
    status: CalibrationStatus,
    message: str,
    request_digest: str,
) -> CalibrationDiagnostic:
    diagnostic_id = "diagnostic." + sha256_digest(
        {"request": request_digest, "feature": candidate.feature_id, "message": message}
    ).removeprefix("sha256:")
    return CalibrationDiagnostic(
        diagnostic_id=diagnostic_id,
        status=status,
        metric_name="selective_support_gate",
        metric_value=candidate.support_score,
        message=message,
        evidence=candidate.evidence,
    )


def _stratum_calibration_fails(stratum: object, maximum_error: float) -> bool:
    metric = getattr(stratum, "calibration_error", None)
    return metric is None or metric > maximum_error


def _select_candidates(
    request: CalibrateSelectiveCopyNumberDosageRequest,
    request_digest: str,
) -> tuple[
    tuple[CalibratedEstimate, ...],
    tuple[CalibratedPredictionSet, ...],
    tuple[CalibrationDiagnostic, ...],
]:
    policy = request.policy
    strata = {stratum.stratum_id: stratum for stratum in policy.strata}
    threshold = policy.support_threshold
    estimates: list[CalibratedEstimate] = []
    prediction_sets: list[CalibratedPredictionSet] = []
    diagnostics: list[CalibrationDiagnostic] = []
    for candidate in sorted(request.candidates, key=lambda item: item.feature_id):
        reason: str | None = None
        if any(stratum_id not in strata for stratum_id in candidate.stratum_ids):
            reason = "candidate references an unknown calibration stratum"
        elif candidate.support_score < threshold.minimum_support_score:
            reason = "candidate support score is below the locked threshold"
        elif candidate.ood_score > threshold.maximum_ood_score:
            reason = "candidate OOD score exceeds the locked threshold"
        elif candidate.calibration_error > threshold.maximum_calibration_error:
            reason = "candidate calibration error exceeds the locked threshold"
        elif any(
            _stratum_calibration_fails(strata[stratum_id], threshold.maximum_calibration_error)
            for stratum_id in candidate.stratum_ids
        ):
            reason = "candidate is bound to an out-of-gate calibration stratum"
        if reason is not None:
            diagnostics.append(
                _candidate_diagnostic(
                    candidate, CalibrationStatus.ABSTAINED, reason, request_digest
                )
            )
            continue
        labels = candidate.labels or ((candidate.category,) if candidate.category else ())
        prediction_id = "prediction-set." + sha256_digest(
            {"request": request_digest, "feature": candidate.feature_id, "labels": labels}
        ).removeprefix("sha256:")
        observed_coverages = [strata[item].observed_coverage for item in candidate.stratum_ids]
        observed_coverage = min(item for item in observed_coverages if item is not None)
        prediction_set = CalibratedPredictionSet(
            prediction_set_id=prediction_id,
            feature_id=candidate.feature_id,
            labels=labels,
            target_coverage=policy.target_coverage,
            observed_coverage=observed_coverage,
            evidence=candidate.evidence,
        )
        estimates.append(
            CalibratedEstimate(
                feature_id=candidate.feature_id,
                estimate_value=candidate.estimate_value,
                category=candidate.category,
                prediction_set_id=prediction_id,
                support_score=candidate.support_score,
                ood_status=OutOfDistributionStatus.IN_DOMAIN,
                calibration_error=candidate.calibration_error,
                selection_status=SelectivePredictionStatus.SELECTED,
                evidence=candidate.evidence,
            )
        )
        prediction_sets.append(prediction_set)
        diagnostics.append(
            _candidate_diagnostic(
                candidate,
                CalibrationStatus.CALIBRATED,
                "candidate passed support, OOD, calibration, and stratum gates",
                request_digest,
            )
        )
    return tuple(estimates), tuple(prediction_sets), tuple(diagnostics)


class M0707CalibrationEngine:
    """Execute the provisional quality-gated selective calibration operation."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveCopyNumberDosageRequest:
        preflight_calibration_authorization(request)
        try:
            return _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as exc:
            raise CalibrationInputError from exc

    def calibrate(self, request: object) -> CalibrateSelectiveCopyNumberDosageResult:
        validated = self.validate_request(request)
        return self._result(validated)

    def _result(
        self,
        request: CalibrateSelectiveCopyNumberDosageRequest,
    ) -> CalibrateSelectiveCopyNumberDosageResult:
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        evidence = _evidence(request)
        estimates: tuple[CalibratedEstimate, ...] = ()
        prediction_sets: tuple[CalibratedPredictionSet, ...] = ()
        diagnostics: tuple[CalibrationDiagnostic, ...] = ()
        if not _upstream_ready(request):
            reason = "upstream M07-06 uncertainty result is unsupported or not evaluable"
            status = CalibrationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0707_upstream_not_ready",
                rationale=reason,
            )
        elif not _policy_ready(request):
            reason = "calibration strata or coverage do not satisfy the provisional gate"
            status = CalibrationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0707_calibration_gate_not_met",
                rationale=reason,
            )
        else:
            estimates, prediction_sets, diagnostics = _select_candidates(request, request_hash)
            if estimates:
                reason = None
                status = CalibrationStatus.CALIBRATED
                support = SupportDecision(
                    status=SupportStatus.SUPPORTED,
                    reason_code="m0707_selective_gate_passed",
                    rationale="At least one candidate passed every locked selective gate.",
                )
            else:
                reason = "no candidate passed the locked support, OOD, and calibration gates"
                status = CalibrationStatus.ABSTAINED
                support = SupportDecision(
                    status=SupportStatus.UNSUPPORTED,
                    reason_code="m0707_no_candidate_selected",
                    rationale=reason,
                )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0707_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimates": estimates,
            "prediction_sets": prediction_sets,
            "diagnostics": diagnostics,
            "abstention_reason": reason,
            "parent_target": M0707_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": request.uncertainty_result.uncertainty,
            "provenance": _provenance(request, request_hash, policy_hash),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": status is not CalibrationStatus.CALIBRATED,
        }
        constructed = CalibrateSelectiveCopyNumberDosageResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def calibrate_selective_copy_number_dosage(
    request: object,
) -> CalibrateSelectiveCopyNumberDosageResult:
    """Public provisional M07-07 calibration operation."""

    return M0707CalibrationEngine().calibrate(request)


__all__ = [
    "CalibrationAuthorizationError",
    "CalibrationInputError",
    "M0707CalibrationEngine",
    "calibrate_selective_copy_number_dosage",
    "preflight_calibration_authorization",
]
