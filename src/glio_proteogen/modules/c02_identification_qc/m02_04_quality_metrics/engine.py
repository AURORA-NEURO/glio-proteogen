"""Stateless deterministic engine for M02-04 identification quality."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_04 import (
    M0204_AUTHORITY_LIMITATION_CODE,
    M0204_CONTRACT_VERSION,
    M0204_MODULE_ID,
    M0204_QUALITY_LIMITATION_CODE,
    ComputeIdentificationQualityRequest,
    IdentificationMetricProvenance,
    IdentificationMetricResult,
    IdentificationMetricStatus,
    IdentificationQualityDisposition,
    IdentificationQualityMetricCode,
    IdentificationQualityProfile,
    MetricObservation,
    MetricObservationState,
    MetricThreshold,
    assay_profile_digest,
    canonical_request_digest,
    configuration_digest,
    observation_digest,
    policy_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.calculations import Thresholds
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.kernel import (
    IdentificationMetricInput,
    compute_identification_metric,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeIdentificationQualityRequest)
_LIMITATIONS: Final = (
    Limitation(
        code=M0204_QUALITY_LIMITATION_CODE,
        statement=(
            "This profile reports identification quality controls only; it does not infer "
            "protein subtype, proteotype, biology, kinase activity, or treatment."
        ),
    ),
    Limitation(
        code=M0204_AUTHORITY_LIMITATION_CODE,
        statement=(
            "Upstream controls, assay profiles, and observations are caller-declared "
            "references whose issuers M02-04 does not authenticate."
        ),
    ),
)


class IdentificationQualityAuthorizationError(ValueError):
    """Denied upstream controls detected before typed observation validation."""

    def __init__(self) -> None:
        super().__init__(
            "upstream controls do not authorize identification quality computation"
        )


class M0204IdentificationQualityEngine:
    """Compute one immutable identification quality profile without I/O or models."""

    __slots__ = ()

    def compute(self, request: object) -> IdentificationQualityProfile:
        preflight_identification_quality_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        active_policy_digest = policy_digest(validated.policy)
        assay_digest = assay_profile_digest(validated.assay_profile)
        observations = {item.metric_code: item for item in validated.observations}
        thresholds = {item.metric_code: item for item in validated.policy.thresholds}
        metrics = tuple(
            _evaluate_metric(
                code,
                observations[code],
                thresholds[code],
                assay_digest,
                active_policy_digest,
            )
            for code in IdentificationQualityMetricCode
        )
        disposition = _disposition(validated, metrics)
        request_hash = canonical_request_digest(validated)
        config_digest = configuration_digest(validated.policy)
        return IdentificationQualityProfile(
            quality_profile_id=f"quality.m0204.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            assay_profile_digest=assay_digest,
            assay_profile_evidence_digest=validated.assay_profile.evidence.digest,
            policy_id=validated.policy.policy_id,
            policy_version=validated.policy.version,
            policy_digest=active_policy_digest,
            configuration_digest=config_digest,
            disposition=disposition,
            metrics=metrics,
            quarantine_on_warning=validated.policy.quarantine_on_warning,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                metrics,
                request_hash,
                assay_digest,
                active_policy_digest,
                config_digest,
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is IdentificationQualityDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def compute_identification_quality(request: object) -> IdentificationQualityProfile:
    return M0204IdentificationQualityEngine().compute(request)


def preflight_identification_quality_authorization(candidate: object) -> None:
    """Reject raw denial before typed validation traverses metric observations."""

    context = _value(candidate, "context")
    references = _value(context, "references")
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
        _state(_value(_value(references, role), "state")) != state
        for role, state in expected.items()
    ):
        raise IdentificationQualityAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _evaluate_metric(
    code: IdentificationQualityMetricCode,
    observation: MetricObservation,
    threshold: MetricThreshold,
    assay_digest: str,
    active_policy_digest: str,
) -> IdentificationMetricResult:
    canonical_observation = observation.model_copy(
        update={"evidence": tuple(sorted(observation.evidence, key=canonical_json_bytes))}
    )
    outcome = compute_identification_metric(
        code.value,
        IdentificationMetricInput(
            state=canonical_observation.state.value,
            numerator=canonical_observation.numerator,
            denominator=canonical_observation.denominator,
            value=(
                canonical_observation.value
                if isinstance(canonical_observation.value, float)
                else None
            ),
            matches_expected=(
                canonical_observation.value
                if isinstance(canonical_observation.value, bool)
                else None
            ),
        ),
        threshold.direction.value,
        Thresholds(
            pass_min=threshold.pass_minimum,
            pass_max=threshold.pass_maximum,
            warning_min=threshold.warning_minimum,
            warning_max=threshold.warning_maximum,
        ),
    )
    return IdentificationMetricResult(
        metric_code=code,
        state=_result_state(outcome.state.value),
        status=IdentificationMetricStatus(outcome.status.value),
        required=threshold.required,
        value=outcome.value,
        unit=(
            "ppm"
            if code is IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY
            else "1"
        ),
        observation=canonical_observation,
        threshold=threshold,
        provenance=IdentificationMetricProvenance(
            observation_digest=observation_digest(canonical_observation),
            threshold_digest=sha256_digest(threshold),
            assay_profile_digest=assay_digest,
            policy_digest=active_policy_digest,
        ),
        evidence=canonical_observation.evidence,
    )


def _result_state(state: str) -> MetricObservationState:
    return {
        "observed": MetricObservationState.OBSERVED,
        "missing": MetricObservationState.MISSING,
        "below_detection_limit": MetricObservationState.CENSORED,
        "not_applicable": MetricObservationState.NOT_APPLICABLE,
        "unsupported": MetricObservationState.UNSUPPORTED,
    }[state]


def _disposition(
    request: ComputeIdentificationQualityRequest,
    metrics: tuple[IdentificationMetricResult, ...],
) -> IdentificationQualityDisposition:
    thresholds = {item.metric_code: item for item in request.policy.thresholds}
    if any(
        item.status is IdentificationMetricStatus.FAIL
        or (
            item.status is IdentificationMetricStatus.NOT_EVALUABLE
            and thresholds[item.metric_code].required
        )
        or (
            item.status is IdentificationMetricStatus.WARNING
            and request.policy.quarantine_on_warning
        )
        for item in metrics
    ):
        return IdentificationQualityDisposition.QUARANTINED
    return IdentificationQualityDisposition.ACCEPTED


def _support(disposition: IdentificationQualityDisposition) -> SupportDecision:
    if disposition is IdentificationQualityDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="identification_quality_quarantined",
            rationale="At least one required identification quality metric failed or abstained.",
        )
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="identification_quality_accepted",
        rationale="Deterministic identification quality controls support bounded workflow use.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("No calibrated measurement-error distribution was supplied."),
        sampling=_not_estimable("No sampling distribution was supplied."),
        parameter=_not_estimable("Reviewed thresholds are fixed; no parameters are fitted."),
        model_form=_not_estimable("The deterministic engine uses no predictive model."),
        identification=_not_estimable(
            "Residual identification error is not probabilistically modeled."
        ),
        support=_not_estimable("Support is a deterministic policy state."),
        transport=_not_estimable("Transport beyond the pinned assay profile is not estimated."),
        sensitivity_notes=(
            "Changing an observation, threshold, assay profile, or policy requires replay.",
            "Missing, censored, and unsupported evidence never becomes measured zero.",
        ),
    )


def _controls(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(  # noqa: PLR0913, PLR0917 - explicit digest bindings are safety-relevant.
    request: ComputeIdentificationQualityRequest,
    metrics: tuple[IdentificationMetricResult, ...],
    request_hash: str,
    assay_digest: str,
    active_policy_digest: str,
    config_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _controls(request.context)
    return ProvenanceRecord(
        activity_id=f"activity.m0204.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0204_MODULE_ID,
        module_version=M0204_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    assay_digest,
                    request.assay_profile.evidence.digest,
                    active_policy_digest,
                    config_digest,
                    *(item.provenance.observation_digest for item in metrics),
                    *(item.provenance.threshold_digest for item in metrics),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=config_digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: ComputeIdentificationQualityRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls: tuple[tuple[ControlRole, ArtifactReference], ...] = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    result = [
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=f"Caller-declared {role.value} control; issuer is not authenticated.",
        )
        for role, reference in controls
    ]
    result.append(
        EvidenceReference(
            reference=request.assay_profile.evidence,
            role="evidence",
            claim="Caller-declared assay profile evidence; issuer is not authenticated.",
        )
    )
    return tuple(sorted(result, key=canonical_json_bytes))


__all__ = [
    "IdentificationQualityAuthorizationError",
    "M0204IdentificationQualityEngine",
    "compute_identification_quality",
    "preflight_identification_quality_authorization",
]
