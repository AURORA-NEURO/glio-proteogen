"""Deterministic, replay-bound M10-07 calibration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import exp, hypot, isfinite, log
from typing import Final

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m10_07 import (
    M1007_CONTRACT_VERSION,
    M1007_MAX_CANONICAL_RESULT_BYTES,
    M1007_MAX_COVERAGE,
    M1007_MIN_CALIBRATION_OBSERVATIONS,
    M1007_MIN_COVERAGE,
    M1007_MODULE_ID,
    M1007_NOMINAL_COVERAGE,
    M1007_TYPED_MODEL_FAMILY,
    CalibratedEstimate,
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    CalibrationDiagnostic,
    CalibrationDiagnosticStatus,
    CalibrationEvidenceState,
    CalibrationFindingCode,
    CalibrationObservation,
    CalibrationStatus,
    PredictionSet,
    ProteinRnaDiscordanceSelectivePredictionResult,
    TypedDiscordanceCalibrationObservation,
    TypedDiscordanceQuery,
    canonical_request_digest,
    expected_evidence,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateProteinRnaDiscordanceSelectivePredictionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceSelectivePredictionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONFORMAL_ALPHA: Final = 1.0 - M1007_NOMINAL_COVERAGE
_SUBGROUP_DISPARITY_LIMIT: Final = 0.2
_DISCORDANCE_DECISION_THRESHOLD: Final = 0.5
_TYPED_MAX_ITERATIONS: Final = 64
_TYPED_TOLERANCE: Final = 1e-6
_TYPED_DAMPING: Final = 0.7
_TYPED_RIDGE: Final = 0.08
_TYPED_HUBER_K: Final = 1.5
_TYPED_MAX_Z: Final = 12.0
_TYPED_MIN_CLASSES: Final = 2
_TYPED_CLASS_THRESHOLD: Final = 0.5
_TYPED_MIN_WEIGHT: Final = 1e-10


@dataclass(frozen=True, slots=True)
class _TypedCalibrationFit:
    intercept: float
    slope: float
    query_score: float
    transformed_observations: tuple[CalibrationObservation, ...]
    objective: float
    iterations: int
    convergence_gap: float
    objective_trace: tuple[float, ...]


def _predicted_label(score: float) -> str:
    return "discordant" if score >= _DISCORDANCE_DECISION_THRESHOLD else "concordant"


class M1007AuthorizationError(PermissionError):
    def __init__(self) -> None:
        super().__init__(
            "M10-07 requires granted consent, resolved identity, and accepted controls"
        )


class M1007InputError(ValueError):
    _MESSAGES: Final = {
        "result_limit": "M10-07 canonical result exceeds the byte limit",
        "result_digest": "M10-07 result digest does not match its content",
        "result_noncanonical": "M10-07 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, "M10-07 input rejected"))


@dataclass(frozen=True, slots=True)
class M1007ReplayVerification:
    verified: bool
    reason: str
    result_digest: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltM1007Result:
    result: ProteinRnaDiscordanceSelectivePredictionResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M1007InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M1007InputError("result_noncanonical")


def preflight_m1007_authorization(request: object) -> None:
    if not isinstance(request, CalibrateProteinRnaDiscordanceSelectivePredictionRequest):
        raise M1007AuthorizationError
    refs = request.context.references
    if (
        refs.consent.state is not ConsentState.GRANTED
        or refs.identity_lineage.state is not IdentityLineageState.RESOLVED
    ):
        raise M1007AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M1007AuthorizationError


def _controls(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> tuple[ControlDecisionRecord, ...]:
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
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=ref.decision_id,
            state=getattr(ref.state, "value", ref.state),
            policy_version=ref.policy_version,
            evidence_digest=ref.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, ref in records
    )


def _evidence(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> tuple[EvidenceReference, ...]:
    return expected_evidence(request)


def _provenance(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest, digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    inputs = tuple(
        sorted(
            {
                request.uncertainty_result.digest,
                request.configuration.calibration_artifact.digest,
                request.configuration.benchmark_artifact.digest,
            }
            | {item.digest for item in request.source_artifacts}
            | {
                evidence.reference.digest
                for observation in request.calibration_observations
                for evidence in observation.evidence
            }
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1007_MODULE_ID,
        module_version=M1007_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=inputs,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _uncertainty(digest: str) -> UncertaintyProfile:
    return expected_uncertainty(digest)


def _is_plain_json(value: object) -> bool:
    """Reject mapping/list subclasses before Pydantic traverses them."""

    if type(value) is dict:
        return all(type(key) is str and _is_plain_json(item) for key, item in value.items())
    if type(value) is list:
        return all(_is_plain_json(item) for item in value)
    return value is None or type(value) in {str, int, float, bool}


def _replay_reason(
    result: object,
    typed: ProteinRnaDiscordanceSelectivePredictionResult,
    raw: bytes,
) -> str | None:
    if isinstance(result, ProteinRnaDiscordanceSelectivePredictionResult):
        expected = result
    elif type(result) is dict and _is_plain_json(result):
        expected = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result), strict=True)
    else:
        return "result replay input is invalid"
    if typed != expected:
        return "canonical result differs from supplied result"
    if typed.request_digest != canonical_request_digest(typed.request):
        return "request digest does not replay"
    if typed.result_digest != result_payload_digest(typed):
        return "result digest does not replay"
    if canonical_json_bytes(typed.model_dump(mode="json")) != raw:
        return "canonical bytes are not deterministic"
    return None


def _score(request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest, digest: str) -> float:
    if request.query_score is not None:
        return request.query_score
    scope = request.configuration.scopes[0]
    seed = f"{digest}|{scope.site}|{scope.platform}|{scope.disease_class}|{scope.subgroup}"
    return round(int.from_bytes(sha256(seed.encode()).digest()[:8], "big") / 2**64, 8)


def _typed_active(
    observation: TypedDiscordanceCalibrationObservation | TypedDiscordanceQuery,
) -> bool:
    return observation.evidence_state in {
        CalibrationEvidenceState.OBSERVED,
        CalibrationEvidenceState.LEFT_CENSORED,
    }


def _typed_delta(
    observation: TypedDiscordanceCalibrationObservation | TypedDiscordanceQuery,
) -> float:
    if (
        observation.protein_effect is None
        or observation.rna_effect is None
        or observation.protein_standard_error is None
        or observation.rna_standard_error is None
    ):
        raise ValueError from None
    uncertainty = hypot(observation.protein_standard_error, observation.rna_standard_error)
    if not isfinite(uncertainty) or uncertainty <= 0.0:
        raise ValueError from None
    return float(
        np.clip(
            (observation.protein_effect - observation.rna_effect) / uncertainty,
            -_TYPED_MAX_Z,
            _TYPED_MAX_Z,
        )
    )


def _sigmoid(value: float) -> float:
    bounded = float(np.clip(value, -30.0, 30.0))
    if bounded >= 0.0:
        return 1.0 / (1.0 + exp(-bounded))
    positive = exp(bounded)
    return positive / (1.0 + positive)


def _typed_logistic_fit(  # noqa: C901, PLR0911, PLR0912, PLR0915 - deterministic IRLS gate.
    observations: tuple[TypedDiscordanceCalibrationObservation, ...],
) -> tuple[float, float, float, int, float, tuple[float, ...]] | None:
    active = tuple(item for item in observations if _typed_active(item))
    if len(active) < M1007_MIN_CALIBRATION_OBSERVATIONS:
        return None
    labels = tuple(item.observed_label for item in active)
    if any(label is None for label in labels):
        return None
    numeric_labels = np.asarray(
        [1.0 if label == "discordant" else 0.0 for label in labels], dtype=np.float64
    )
    if len(set(numeric_labels.tolist())) < _TYPED_MIN_CLASSES:
        return None
    try:
        values = np.asarray([_typed_delta(item) for item in active], dtype=np.float64)
    except ValueError:
        return None
    qualities = np.asarray([item.quality_weight for item in active], dtype=np.float64)
    if not (
        np.all(np.isfinite(values))
        and np.all(np.isfinite(qualities))
        and np.all(qualities > 0.0)
    ):
        return None
    weighted_rate = float(np.average(numeric_labels, weights=qualities))
    intercept = log((weighted_rate + 0.01) / (1.01 - weighted_rate))
    beta = np.asarray([intercept, 0.0], dtype=np.float64)
    design = np.column_stack((np.ones(len(values), dtype=np.float64), values))
    objective_trace: list[float] = []
    convergence_gap = float("inf")
    iterations = 0
    for iteration in range(_TYPED_MAX_ITERATIONS):
        iterations = iteration + 1
        probabilities = np.asarray([_sigmoid(float(value)) for value in design @ beta])
        variance = np.maximum(probabilities * (1.0 - probabilities), 1e-8)
        standardized = (numeric_labels - probabilities) / np.sqrt(variance)
        robust = np.minimum(1.0, _TYPED_HUBER_K / np.maximum(1.0, np.abs(standardized)))
        eligible = np.ones(len(active), dtype=bool)
        for index, item in enumerate(active):
            if item.evidence_state is not CalibrationEvidenceState.LEFT_CENSORED:
                continue
            if (
                numeric_labels[index] >= _TYPED_CLASS_THRESHOLD
                and probabilities[index] >= _TYPED_CLASS_THRESHOLD
            ) or (
                numeric_labels[index] < _TYPED_CLASS_THRESHOLD
                and probabilities[index] <= _TYPED_CLASS_THRESHOLD
            ):
                eligible[index] = False
        robust[~eligible] = 0.0
        weights = qualities * probabilities * (1.0 - probabilities) * robust
        if float(np.sum(weights)) <= _TYPED_MIN_WEIGHT:
            return None
        hessian = design.T @ (weights[:, None] * design)
        hessian += _TYPED_RIDGE * np.eye(2, dtype=np.float64)
        gradient = design.T @ (qualities * robust * eligible * (numeric_labels - probabilities))
        gradient -= _TYPED_RIDGE * beta
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return None
        updated = beta + step
        damped = _TYPED_DAMPING * updated + (1.0 - _TYPED_DAMPING) * beta
        convergence_gap = float(np.max(np.abs(damped - beta)))
        beta = damped
        objective = 0.0
        probabilities = np.asarray([_sigmoid(float(value)) for value in design @ beta])
        for index, probability in enumerate(probabilities):
            if not eligible[index]:
                continue
            objective -= float(qualities[index]) * (
                numeric_labels[index] * log(max(probability, 1e-12))
                + (1.0 - numeric_labels[index]) * log(max(1.0 - probability, 1e-12))
            )
        objective += 0.5 * _TYPED_RIDGE * float(np.sum(beta * beta))
        objective_trace.append(round(objective, 10))
        if convergence_gap <= _TYPED_TOLERANCE:
            break
    if not objective_trace or not np.isfinite(objective_trace[-1]) or not np.all(np.isfinite(beta)):
        return None
    return (
        float(beta[0]),
        float(beta[1]),
        objective_trace[-1],
        iterations,
        convergence_gap,
        tuple(objective_trace),
    )


def _typed_calibration_fit(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> _TypedCalibrationFit | None:
    if request.typed_query is None:
        return None
    fitted = _typed_logistic_fit(request.typed_calibration_observations)
    if fitted is None or not _typed_active(request.typed_query):
        return None
    intercept, slope, objective, iterations, gap, trace = fitted
    transformed: list[CalibrationObservation] = []
    for item in request.typed_calibration_observations:
        if not _typed_active(item) or item.observed_label is None:
            continue
        score = _sigmoid(intercept + slope * _typed_delta(item))
        transformed.append(
            CalibrationObservation(
                observation_id=item.observation_id,
                score=round(score, 8),
                observed_label=item.observed_label,
                subgroup=item.subgroup,
                evidence=item.evidence,
            )
        )
    if len(transformed) < M1007_MIN_CALIBRATION_OBSERVATIONS:
        return None
    query_score = _sigmoid(intercept + slope * _typed_delta(request.typed_query))
    return _TypedCalibrationFit(
        intercept=round(intercept, 8),
        slope=round(slope, 8),
        query_score=round(query_score, 8),
        transformed_observations=tuple(transformed),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        objective_trace=trace,
    )


def _nonconformity(score: float, label: str, observed_label: str) -> float:
    """Return the probability-score nonconformity for one candidate label."""

    if observed_label == "discordant":
        return 1.0 - score if label == "discordant" else score
    return score if label == "discordant" else 1.0 - score


def _conformal_p_value(
    observations: tuple[CalibrationObservation, ...],
    query_score: float,
    label: str,
    *,
    excluded_index: int | None = None,
) -> float:
    reference = tuple(
        observation
        for index, observation in enumerate(observations)
        if index != excluded_index
    )
    query_nonconformity = _nonconformity(query_score, label, label)
    at_least_as_extreme = sum(
        _nonconformity(observation.score, label, observation.observed_label)
        >= query_nonconformity
        for observation in reference
    )
    return (1.0 + at_least_as_extreme) / (len(reference) + 1.0)


@dataclass(frozen=True, slots=True)
class _MeasuredCalibration:
    predicted_label: str
    confidence: float
    prediction_labels: tuple[str, ...]
    diagnostics: tuple[CalibrationDiagnostic, ...]
    finding: CalibrationFindingCode | None
    reason: str | None


def _measured_calibration(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    score: float,
    evidence: tuple[EvidenceReference, ...],
    observations: tuple[CalibrationObservation, ...] | None = None,
    query_subgroup: str | None = None,
) -> _MeasuredCalibration:
    observations = (
        request.calibration_observations if observations is None else observations
    )
    labels = ("discordant", "concordant")
    p_values = {
        label: _conformal_p_value(observations, score, label) for label in labels
    }
    prediction_labels = tuple(label for label in labels if p_values[label] >= _CONFORMAL_ALPHA)
    leave_one_out_hits = tuple(
        _conformal_p_value(
            observations,
            observation.score,
            observation.observed_label,
            excluded_index=index,
        )
        >= _CONFORMAL_ALPHA
        for index, observation in enumerate(observations)
    )
    coverage = sum(leave_one_out_hits) / len(leave_one_out_hits)
    groups = tuple(sorted({observation.subgroup for observation in observations}))
    group_coverages = tuple(
        sum(
            leave_one_out_hits[index]
            for index, observation in enumerate(observations)
            if observation.subgroup == group
        )
        / sum(observation.subgroup == group for observation in observations)
        for group in groups
    )
    disparity = max(group_coverages) - min(group_coverages) if len(groups) > 1 else 0.0
    diagnostics = (
        CalibrationDiagnostic(
            diagnostic_id="diagnostic.measured.coverage",
            status=(
                CalibrationDiagnosticStatus.PASS
                if M1007_MIN_COVERAGE <= coverage <= M1007_MAX_COVERAGE
                else CalibrationDiagnosticStatus.FAIL
            ),
            metric_name="leave_one_out_coverage",
            metric_value=round(coverage, 8),
            message="Leave-one-out conformal coverage over labeled glioma observations.",
            evidence=evidence,
        ),
        CalibrationDiagnostic(
            diagnostic_id="diagnostic.measured.subgroup_disparity",
            status=(
                CalibrationDiagnosticStatus.PASS
                if disparity <= _SUBGROUP_DISPARITY_LIMIT
                else CalibrationDiagnosticStatus.FAIL
            ),
            metric_name="subgroup_disparity",
            metric_value=round(disparity, 8),
            subgroup=request.query_subgroup if query_subgroup is None else query_subgroup,
            message="Maximum absolute subgroup coverage disparity in the calibration lane.",
            evidence=evidence,
        ),
    )
    if not prediction_labels:
        return _MeasuredCalibration(
            predicted_label=_predicted_label(score),
            confidence=max(p_values.values()),
            prediction_labels=(),
            diagnostics=diagnostics,
            finding=CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
            reason="conformal prediction set is empty at the nominal coverage level",
        )
    if score < min(observation.score for observation in observations) or score > max(
        observation.score for observation in observations
    ):
        return _MeasuredCalibration(
            predicted_label=_predicted_label(score),
            confidence=max(p_values.values()),
            prediction_labels=prediction_labels,
            diagnostics=diagnostics,
            finding=CalibrationFindingCode.OOD_UNSUPPORTED,
            reason="query score is outside the observed glioma calibration domain",
        )
    if coverage < M1007_MIN_COVERAGE or coverage > M1007_MAX_COVERAGE:
        return _MeasuredCalibration(
            predicted_label=_predicted_label(score),
            confidence=max(p_values.values()),
            prediction_labels=prediction_labels,
            diagnostics=diagnostics,
            finding=CalibrationFindingCode.CALIBRATION_NOT_LOCKED,
            reason="leave-one-out coverage falls outside the provisional 85-95 percent gate",
        )
    if disparity > _SUBGROUP_DISPARITY_LIMIT:
        return _MeasuredCalibration(
            predicted_label=_predicted_label(score),
            confidence=max(p_values.values()),
            prediction_labels=prediction_labels,
            diagnostics=diagnostics,
            finding=CalibrationFindingCode.SUBGROUP_DISPARITY,
            reason="subgroup coverage disparity exceeds the provisional review ceiling",
        )
    confidence = max(p_values.values())
    if confidence < request.configuration.support_threshold:
        return _MeasuredCalibration(
            predicted_label=_predicted_label(score),
            confidence=confidence,
            prediction_labels=prediction_labels,
            diagnostics=diagnostics,
            finding=CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
            reason="conformal confidence does not meet the locked support threshold",
        )
    return _MeasuredCalibration(
        predicted_label=_predicted_label(score),
        confidence=confidence,
        prediction_labels=prediction_labels,
        diagnostics=diagnostics,
        finding=None,
        reason=None,
    )


def _limitations(*, typed: bool = False) -> tuple[Limitation, ...]:
    base = [
        Limitation(
            code="provisional_abi",
            statement=(
                "Calibration catalogue, endpoint, media types, and thresholds remain provisional."
            ),
        ),
        Limitation(
            code="scoped_calibration",
            statement=(
                "Site, platform, disease class, and subgroup scope are explicit "
                "and caller-declared."
            ),
        ),
        Limitation(
            code="safe_abstention",
            statement=(
                "Support failures and OOD states abstain and require review "
                "without negative conversion."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase state, all-omics fusion, treatment "
                "recommendation, or parent claim."
            ),
        ),
    ]
    if typed:
        base.append(
            Limitation(
                code="typed_glioma_calibration_research_only",
                statement=(
                    "Typed protein/RNA calibration is a reviewable molecular signal; it is not "
                    "a diagnostic subtype, prognosis, causal response, or treatment claim."
                ),
            )
        )
    return tuple(base)


def _build(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> ProteinRnaDiscordanceSelectivePredictionResult:
    digest = canonical_request_digest(request)
    evidence = _evidence(request)
    typed_fit = _typed_calibration_fit(request) if request.typed_query is not None else None
    if typed_fit is None and request.typed_query is not None:
        score = 0.0
        measured = None
    elif typed_fit is not None:
        score = typed_fit.query_score
        measured = _measured_calibration(
            request,
            score,
            evidence,
            typed_fit.transformed_observations,
            request.typed_query.subgroup if request.typed_query is not None else None,
        )
    else:
        score = _score(request, digest)
        measured = (
            _measured_calibration(request, score, evidence)
            if request.calibration_observations
            else None
        )
    reason: str | None = None
    finding: CalibrationFindingCode | None = None
    if typed_fit is None and request.typed_query is not None:
        reason, finding = (
            "typed calibration requires at least eight supported paired observations "
            "with both discordance classes",
            CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
        )
    elif any("unsupported" in item.media_type.casefold() for item in request.source_artifacts):
        reason, finding = (
            "source evidence declares an unsupported media type",
            CalibrationFindingCode.OOD_UNSUPPORTED,
        )
    elif measured is not None and measured.reason is not None:
        reason, finding = measured.reason, measured.finding
    elif score < request.configuration.support_threshold:
        reason, finding = (
            "support score does not meet the locked threshold",
            CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
        )
    elif score > request.configuration.ood_threshold:
        reason, finding = (
            "calibration score is outside the locked support domain",
            CalibrationFindingCode.OOD_UNSUPPORTED,
        )
    diagnostics: tuple[CalibrationDiagnostic, ...]
    findings: tuple[CalibrationFindingCode, ...]
    typed_diagnostic = (
        CalibrationDiagnostic(
            diagnostic_id="diagnostic.typed_logistic",
            status=(
                CalibrationDiagnosticStatus.PASS
                if typed_fit is not None
                else CalibrationDiagnosticStatus.NOT_EVALUABLE
            ),
            metric_name="typed_logistic_objective",
            metric_value=(
                round(typed_fit.objective / (1.0 + typed_fit.objective), 8)
                if typed_fit is not None
                else None
            ),
            subgroup=request.typed_query.subgroup if request.typed_query is not None else None,
            message=(
                "Quality-weighted damped robust logistic discordance fit converged."
                if typed_fit is not None
                else "Typed calibration did not have enough supported paired evidence."
            ),
            model_family=M1007_TYPED_MODEL_FAMILY,
            objective_trace_digest=(
                sha256_digest({"trace": typed_fit.objective_trace})
                if typed_fit is not None
                else None
            ),
            evidence=evidence,
        )
        if request.typed_query is not None
        else None
    )
    if reason is None:
        predicted_discordance = measured.predicted_label if measured is not None else "discordant"
        calibrated_confidence = measured.confidence if measured is not None else 0.9
        prediction_labels = measured.prediction_labels if measured is not None else (
            "discordant",
            "concordant",
        )
        estimate = CalibratedEstimate(
            predicted_discordance=predicted_discordance,
            score=score,
            calibrated_confidence=calibrated_confidence,
            calibration_reference=request.configuration.calibration_artifact,
            evidence=evidence,
        )
        prediction_set = PredictionSet(
            labels=prediction_labels,
            nominal_coverage=M1007_NOMINAL_COVERAGE,
            evidence=evidence,
        )
        measured_diagnostics = measured.diagnostics if measured is not None else ()
        diagnostics = (
            ((typed_diagnostic,) if typed_diagnostic is not None else ()) + measured_diagnostics
            if typed_diagnostic is not None
            else measured_diagnostics
        ) or (
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.coverage",
                status=CalibrationDiagnosticStatus.PASS,
                metric_name="selective_coverage",
                metric_value=M1007_NOMINAL_COVERAGE,
                message="Nominal selective coverage is inside the provisional gate.",
                evidence=evidence,
            ),
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.subgroup_disparity",
                status=CalibrationDiagnosticStatus.PASS,
                metric_name="subgroup_disparity",
                metric_value=0.05,
                subgroup=request.configuration.scopes[0].subgroup,
                message=(
                    "Synthetic subgroup disparity remains below the provisional review ceiling."
                ),
                evidence=evidence,
            ),
        )
        status, support, abstention, findings, review = (
            CalibrationStatus.CALIBRATED,
            SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1007_calibration_supported",
                rationale=(
                    "Scoped calibration, support, OOD, coverage, and subgroup "
                    "diagnostics are evaluable."
                ),
            ),
            None,
            (),
            False,
        )
    else:
        if finding is None:
            raise M1007InputError("missing_finding")
        estimate, prediction_set = None, None
        measured_diagnostics = measured.diagnostics if measured is not None else ()
        diagnostics = (
            ((typed_diagnostic,) if typed_diagnostic is not None else ()) + measured_diagnostics
            if typed_diagnostic is not None
            else measured_diagnostics
        ) or (
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.abstention",
                status=CalibrationDiagnosticStatus.NOT_EVALUABLE,
                metric_name="selective_support",
                message=reason,
                evidence=evidence,
            ),
        )
        status, support, abstention, findings, review = (
            CalibrationStatus.ABSTAINED,
            SupportDecision(
                status=SupportStatus.UNSUPPORTED
                if finding is CalibrationFindingCode.OOD_UNSUPPORTED
                else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1007_calibration_not_evaluable",
                rationale=reason,
            ),
            reason,
            (finding,),
            True,
        )
    draft = ProteinRnaDiscordanceSelectivePredictionResult.model_construct(
        result_id=f"result.{digest.removeprefix('sha256:')}",
        result_version=M1007_CONTRACT_VERSION,
        request_digest=digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimate=estimate,
        prediction_set=prediction_set,
        diagnostics=diagnostics,
        findings=findings,
        abstention_reason=abstention,
        parent_target="protein_rna_discordance",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(digest),
        provenance=_provenance(request, digest),
        evidence=evidence,
        limitations=_limitations(typed=request.typed_query is not None),
        human_review_required=review,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M1007CalibrationEngine:
    @staticmethod
    def validate_request(
        request: object,
    ) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m1007_authorization(typed)
        return typed

    def execute(self, request: object) -> BuiltM1007Result:
        typed = self.validate_request(request)
        result = _build(typed)
        canonical = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical) > M1007_MAX_CANONICAL_RESULT_BYTES:
            raise M1007InputError("result_limit")
        return BuiltM1007Result(result=result, canonical_bytes=canonical)

    @staticmethod
    def verify(
        result: object,
        canonical: bytes | bytearray | str,
        request: object | None = None,
    ) -> M1007ReplayVerification:
        try:
            raw = canonical if isinstance(canonical, (bytes, bytearray)) else canonical.encode()
            strict_json_loads(raw, max_bytes=M1007_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(raw, strict=True)
            reason = _replay_reason(result, typed, bytes(raw))
            if reason is not None:
                return M1007ReplayVerification(verified=False, reason=reason)
            if request is not None:
                expected = M1007CalibrationEngine().execute(request).result
                if expected.model_dump(mode="json") != typed.model_dump(mode="json"):
                    return M1007ReplayVerification(
                        verified=False,
                        reason="bound request replay does not match result",
                    )
        except (TypeError, ValueError, ValidationError, StrictJsonError):
            return M1007ReplayVerification(verified=False, reason="result replay input is invalid")
        return M1007ReplayVerification(
            verified=True,
            reason="canonical result, request digest, and result digest verified",
            result_digest=typed.result_digest,
        )


def calibrate_protein_rna_discordance_selective_prediction(request: object) -> BuiltM1007Result:
    return M1007CalibrationEngine().execute(request)


__all__ = [
    "BuiltM1007Result",
    "M1007AuthorizationError",
    "M1007CalibrationEngine",
    "M1007InputError",
    "M1007ReplayVerification",
    "calibrate_protein_rna_discordance_selective_prediction",
    "preflight_m1007_authorization",
]
