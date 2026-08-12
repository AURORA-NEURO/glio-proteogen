"""Pure deterministic quality-metric engine for M01-04."""

from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_04 import (
    Computation,
    ComputeQualityMetricsRequest,
    MetricDefinition,
    MetricState,
    MetricStatus,
    Observation,
    Provenance,
    QualityDisposition,
    QualityMetric,
    QualityProfile,
    canonical_request_digest,
    metric_definition_digest,
    observation_digest,
    policy_digest,
    profile_digest,
)
from glio_proteogen.contracts.m01_04.v1 import M0104_CONTRACT_VERSION, M0104_MODULE_ID
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.calculations import (
    ScalarObservation,
    ScalarResult,
    ScalarState,
    Thresholds,
    calculate_scalar,
    classify_scalar,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REQUEST_ADAPTER: Final[TypeAdapter[ComputeQualityMetricsRequest]] = TypeAdapter(
    ComputeQualityMetricsRequest
)
_LIMITATIONS: Final = (
    Limitation(
        code="quality_metrics_only",
        statement=(
            "This profile reports declared assay quality metrics only; it does not infer a "
            "proteotype, biological absence, kinase state, clinical meaning, or treatment."
        ),
    ),
    Limitation(
        code="external_controls_unverified",
        statement=(
            "Upstream controls, assay definitions, and observation artifacts are "
            "caller-declared references whose issuers M01-04 does not authenticate."
        ),
    ),
)


class M0104MetricEngine:
    """Compute one immutable quality profile without I/O, persistence, or learned models."""

    __slots__ = ()

    def compute(self, request: ComputeQualityMetricsRequest) -> QualityProfile:
        """Revalidate, calculate, and aggregate one authorized request."""

        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        observations = {item.observation_id: item for item in validated.observations}
        active_policy_digest = policy_digest(validated.policy)
        metrics = tuple(
            _evaluate_metric(definition, observations, active_policy_digest)
            for definition in sorted(validated.metric_definitions, key=lambda item: item.metric_id)
        )
        disposition = _disposition(validated, metrics)
        request_hash = canonical_request_digest(validated)
        assay_hash = profile_digest(validated.assay_profile)
        return QualityProfile(
            quality_profile_id=f"quality.m0104.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            assay_profile_digest=assay_hash,
            policy_digest=active_policy_digest,
            disposition=disposition,
            metrics=metrics,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                metrics,
                request_hash,
                assay_hash,
                active_policy_digest,
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is QualityDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def compute_quality_profile(request: ComputeQualityMetricsRequest) -> QualityProfile:
    """Convenience entry point for stateless callers and agent tools."""

    return M0104MetricEngine().compute(request)


def _evaluate_metric(
    definition: MetricDefinition,
    observations: dict[str, Observation],
    active_policy_digest: str,
) -> QualityMetric:
    inputs = tuple(observations[item] for item in definition.observation_ids)
    scalar = _calculate(definition, inputs)
    status = classify_scalar(
        scalar,
        _direction(definition),
        Thresholds(
            pass_min=definition.pass_minimum,
            pass_max=definition.pass_maximum,
            warning_min=definition.warning_minimum,
            warning_max=definition.warning_maximum,
        ),
    )
    evidence = _bounded_references(
        (item for value in inputs for item in value.evidence),
        limit=64,
    )
    return QualityMetric(
        metric_id=definition.metric_id,
        definition_version=definition.version,
        category=definition.category,
        computation=definition.computation,
        state=_metric_state(scalar.state),
        status=MetricStatus(status.value),
        value=scalar.value,
        unit=(
            definition.unit
            if definition.computation is Computation.DIRECT
            else "1"
        ),
        provenance=Provenance(
            definition_digest=metric_definition_digest(definition),
            observation_ids=definition.observation_ids,
            observation_digests=tuple(observation_digest(item) for item in inputs),
            computation=definition.computation,
            policy_digest=active_policy_digest,
        ),
        evidence=evidence,
    )


def _calculate(
    definition: MetricDefinition,
    observations: tuple[Observation, ...],
) -> ScalarResult:
    nonobserved = next(
        (item for item in observations if item.state is not MetricState.OBSERVED),
        None,
    )
    if nonobserved is not None:
        state = {
            MetricState.MISSING: ScalarState.MISSING,
            MetricState.BELOW_DETECTION: ScalarState.BELOW_DETECTION_LIMIT,
            MetricState.NOT_APPLICABLE: ScalarState.NOT_APPLICABLE,
        }[nonobserved.state]
        return ScalarResult(state, None)
    if any(item.unit != definition.unit for item in observations):
        return ScalarResult(ScalarState.UNSUPPORTED, None)
    values = tuple(item.value for item in observations)
    if definition.computation is Computation.RATIO:
        return calculate_scalar(
            definition.computation.value,
            ScalarObservation(
                state="observed",
                numerator=_numeric(values[0]),
                denominator=_numeric(values[1]),
            ),
        )
    value = values[0]
    if definition.computation is Computation.BOOLEAN_MATCH:
        return calculate_scalar(
            definition.computation.value,
            ScalarObservation(
                state="observed",
                matches_expected=(
                    value == definition.reference_value if isinstance(value, bool) else None
                ),
            ),
        )
    numeric_value = _numeric(value)
    reference = _numeric(definition.reference_value)
    return calculate_scalar(
        definition.computation.value,
        ScalarObservation(
            state="observed",
            value=numeric_value,
            detection_limit=reference,
            expected_value=reference,
        ),
    )


def _numeric(value: object) -> float | None:
    return value if isinstance(value, float) else None


def _direction(definition: MetricDefinition) -> str:
    if definition.pass_minimum is not None and definition.pass_maximum is not None:
        return "within_range"
    if definition.pass_minimum is not None:
        return "higher_is_better"
    return "lower_is_better"


def _metric_state(state: ScalarState) -> MetricState:
    return {
        ScalarState.OBSERVED: MetricState.OBSERVED,
        ScalarState.MISSING: MetricState.MISSING,
        ScalarState.BELOW_DETECTION_LIMIT: MetricState.BELOW_DETECTION,
        ScalarState.NOT_APPLICABLE: MetricState.NOT_APPLICABLE,
        ScalarState.UNSUPPORTED: MetricState.NOT_APPLICABLE,
    }[state]


def _disposition(
    request: ComputeQualityMetricsRequest,
    metrics: tuple[QualityMetric, ...],
) -> QualityDisposition:
    required = set(request.assay_profile.required_metric_ids)
    if any(
        metric.status is MetricStatus.FAIL
        or (
            request.policy.require_complete_profile
            and metric.status is MetricStatus.NOT_EVALUABLE
        )
        or (metric.metric_id in required and metric.status is MetricStatus.NOT_EVALUABLE)
        or (
            request.policy.quarantine_on_warning
            and metric.status is MetricStatus.WARNING
        )
        for metric in metrics
    ):
        return QualityDisposition.QUARANTINED
    return QualityDisposition.ACCEPTED


def _support(disposition: QualityDisposition) -> SupportDecision:
    if disposition is QualityDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="quality_profile_quarantined",
            rationale="At least one quality metric failed or could not support the profile.",
        )
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="quality_profile_accepted",
        rationale="Declared deterministic quality metrics support bounded assay use only.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("No calibrated measurement-error distribution was supplied."),
        sampling=_not_estimable("The request supplies no sampling distribution."),
        parameter=_not_estimable("Reviewed thresholds are fixed; no parameters are fitted."),
        model_form=_not_estimable("The deterministic engine uses no predictive model."),
        identification=_not_estimable("Residual observation attribution error is not scored."),
        support=_not_estimable("Support is a deterministic policy state, not a probability."),
        transport=_not_estimable("Transport beyond the declared assay profile is not estimated."),
        sensitivity_notes=(
            "Changing a definition, observation, assay profile, or policy requires replay.",
            "Missing and below-detection observations are never converted to measured zero.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
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


def _provenance(
    request: ComputeQualityMetricsRequest,
    metrics: tuple[QualityMetric, ...],
    request_hash: str,
    assay_hash: str,
    active_policy_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _control_records(request.context)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_hash,
                assay_hash,
                active_policy_digest,
                *(metric.provenance.definition_digest for metric in metrics),
                *(digest for metric in metrics for digest in metric.provenance.observation_digests),
                *(item.evidence_digest for item in controls),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0104.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0104_MODULE_ID,
        module_version=M0104_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=active_policy_digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: ComputeQualityMetricsRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    control_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                f"Caller-declared {role.value.replace('_', '-')} control reference; issuer and "
                "content are not authenticated by M01-04."
            ),
        )
        for role, reference in controls
    )
    observation_references = _bounded_references(
        chain(
            (request.assay_profile.evidence,),
            (
                evidence
                for observation in request.observations
                for evidence in observation.evidence
            ),
        ),
        limit=505,
    )
    observation_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                "Caller-declared scalar observation evidence; M01-04 does not retain or "
                "reinterpret its source payload."
            ),
        )
        for reference in observation_references
    )
    return (*control_evidence, *observation_evidence)


def _bounded_references(
    references: Iterable[ArtifactReference],
    *,
    limit: int,
) -> tuple[ArtifactReference, ...]:
    unique = set(references)
    return tuple(sorted(unique, key=canonical_json_bytes)[:limit])


__all__ = ["M0104MetricEngine", "compute_quality_profile"]
