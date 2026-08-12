"""Focused public-engine qualification for M01-04."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m01_04 import (
    AnalyteLevel,
    AssayProfile,
    AssayType,
    Computation,
    ComputeQualityMetricsRequest,
    MetricCategory,
    MetricDefinition,
    MetricState,
    MetricStatus,
    Observation,
    QualityComputationPolicy,
    QualityDisposition,
    policy_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics import (
    M0104MetricEngine,
    compute_quality_profile,
)


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/json",
    )


def _context(policy: QualityComputationPolicy) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.quality",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", policy_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    definitions: tuple[MetricDefinition, ...],
    observations: tuple[Observation, ...],
    *,
    required: tuple[str, ...] | None = None,
    require_complete_profile: bool = True,
    quarantine_on_warning: bool = False,
) -> ComputeQualityMetricsRequest:
    policy = QualityComputationPolicy(
        policy_id="policy.quality",
        version="1.0.0",
        enabled_categories=tuple(MetricCategory),
        require_complete_profile=require_complete_profile,
        quarantine_on_warning=quarantine_on_warning,
    )
    return ComputeQualityMetricsRequest(
        context=_context(policy),
        assay_profile=AssayProfile(
            profile_id="assay.synthetic",
            version="1.0.0",
            assay_type=AssayType.DIA,
            analyte_level=AnalyteLevel.PROTEIN,
            required_metric_ids=required or tuple(item.metric_id for item in definitions),
            evidence=_artifact("assay-profile"),
        ),
        policy=policy,
        metric_definitions=definitions,
        observations=observations,
    )


def _observation(
    identifier: str,
    value: object,
    *,
    state: MetricState = MetricState.OBSERVED,
    unit: str | None = "%",
    detection_limit: float | None = None,
) -> Observation:
    typed_value = value if isinstance(value, float | bool) else None
    return Observation(
        observation_id=identifier,
        state=state,
        value=typed_value,
        unit=unit,
        detection_limit=detection_limit,
        evidence=(_artifact(identifier),),
    )


def _definition(  # noqa: PLR0913 - fixture builder mirrors the public definition.
    identifier: str,
    computation: Computation,
    observation_ids: tuple[str, ...],
    *,
    category: MetricCategory = MetricCategory.COVERAGE,
    reference: float | bool | None = None,
    pass_minimum: float | None = 0.8,
    pass_maximum: float | None = None,
    warning_minimum: float | None = 0.6,
    warning_maximum: float | None = None,
    unit: str | None = "%",
) -> MetricDefinition:
    return MetricDefinition(
        metric_id=identifier,
        version="1.0.0",
        category=category,
        computation=computation,
        unit=unit,
        observation_ids=observation_ids,
        reference_value=reference,
        pass_minimum=pass_minimum,
        pass_maximum=pass_maximum,
        warning_minimum=warning_minimum,
        warning_maximum=warning_maximum,
    )


def test_engine_computes_sorted_metrics_and_deterministic_provenance() -> None:
    definitions = (
        _definition("metric.ratio", Computation.RATIO, ("observed", "eligible")),
        _definition("metric.direct", Computation.DIRECT, ("quality",)),
    )
    observations = (
        _observation("eligible", 10.0),
        _observation("quality", 0.9),
        _observation("observed", 9.0),
    )
    request = _request(definitions, observations)

    result = M0104MetricEngine().compute(request)
    replay = compute_quality_profile(request)

    assert replay == result
    assert result.disposition is QualityDisposition.ACCEPTED
    assert tuple(item.metric_id for item in result.metrics) == (
        "metric.direct",
        "metric.ratio",
    )
    assert tuple(item.value for item in result.metrics) == (0.9, 0.9)
    assert tuple(item.unit for item in result.metrics) == ("%", "1")
    assert all(item.status is MetricStatus.PASS for item in result.metrics)
    assert result.result_digest != "sha256:" + ("0" * 64)


@pytest.mark.parametrize(
    ("definition", "observation", "expected"),
    [
        (
            _definition(
                "metric.margin",
                Computation.DETECTION_MARGIN,
                ("signal",),
                category=MetricCategory.DETECTION_LIMIT,
                reference=2.0,
                pass_minimum=3.0,
                warning_minimum=2.0,
            ),
            _observation("signal", 8.0),
            4.0,
        ),
        (
            _definition(
                "metric.control",
                Computation.RELATIVE_ERROR,
                ("control",),
                category=MetricCategory.CONTROL_MATERIAL,
                reference=10.0,
                pass_minimum=None,
                pass_maximum=0.1,
                warning_minimum=None,
                warning_maximum=0.2,
            ),
            _observation("control", 9.0),
            0.1,
        ),
        (
            _definition(
                "metric.context",
                Computation.BOOLEAN_MATCH,
                ("context",),
                category=MetricCategory.SAMPLE_CONTEXT,
                reference=True,
                pass_minimum=1.0,
                warning_minimum=1.0,
                unit=None,
            ),
            _observation("context", value=True, unit=None),
            1.0,
        ),
    ],
)
def test_specialized_calculations(
    definition: MetricDefinition,
    observation: Observation,
    expected: float,
) -> None:
    result = compute_quality_profile(_request((definition,), (observation,)))

    assert result.metrics[0].value == pytest.approx(expected)
    assert result.metrics[0].status is MetricStatus.PASS


def test_required_missing_and_failed_control_quarantine() -> None:
    definition = _definition("metric.required", Computation.DIRECT, ("missing",))
    missing = _observation("missing", None, state=MetricState.MISSING)
    result = compute_quality_profile(_request((definition,), (missing,)))

    assert result.disposition is QualityDisposition.QUARANTINED
    assert result.metrics[0].state is MetricState.MISSING
    assert result.metrics[0].status is MetricStatus.NOT_EVALUABLE
    assert result.human_review_required is True


def test_optional_missing_is_accepted_without_becoming_zero() -> None:
    required = _definition("metric.required", Computation.DIRECT, ("value",))
    optional = _definition("metric.optional", Computation.DIRECT, ("missing",))
    observations = (
        _observation("value", 0.9),
        _observation("missing", None, state=MetricState.MISSING),
    )
    result = compute_quality_profile(
        _request(
            (required, optional),
            observations,
            required=(required.metric_id,),
            require_complete_profile=False,
        )
    )

    assert result.disposition is QualityDisposition.ACCEPTED
    metrics = {item.metric_id: item for item in result.metrics}
    assert metrics[optional.metric_id].status is MetricStatus.NOT_EVALUABLE
    assert metrics[optional.metric_id].value is None


def test_complete_profile_policy_quarantines_optional_missing() -> None:
    required = _definition("metric.required", Computation.DIRECT, ("value",))
    optional = _definition("metric.optional", Computation.DIRECT, ("missing",))
    result = compute_quality_profile(
        _request(
            (required, optional),
            (
                _observation("value", 0.9),
                _observation("missing", None, state=MetricState.MISSING),
            ),
            required=(required.metric_id,),
        )
    )

    assert result.disposition is QualityDisposition.QUARANTINED


def test_warning_is_accepted_as_limited_support() -> None:
    definition = _definition("metric.warning", Computation.DIRECT, ("value",))
    observation = _observation("value", 0.7)

    accepted = compute_quality_profile(_request((definition,), (observation,)))

    assert accepted.metrics[0].status is MetricStatus.WARNING
    assert accepted.disposition is QualityDisposition.ACCEPTED

    escalated = compute_quality_profile(
        _request(
            (definition,),
            (observation,),
            quarantine_on_warning=True,
        )
    )
    assert escalated.disposition is QualityDisposition.QUARANTINED


def test_unit_mismatch_abstains_without_coercion() -> None:
    definition = _definition("metric.units", Computation.DIRECT, ("value",))
    observation = _observation("value", 0.9, unit="ratio")
    result = compute_quality_profile(_request((definition,), (observation,)))

    assert result.metrics[0].state is MetricState.NOT_APPLICABLE
    assert result.metrics[0].value is None
    assert result.disposition is QualityDisposition.QUARANTINED


def test_two_sided_pass_range_is_inclusive() -> None:
    definition = _definition(
        "metric.range",
        Computation.DIRECT,
        ("value",),
        pass_minimum=0.8,
        pass_maximum=1.2,
        warning_minimum=0.7,
        warning_maximum=1.3,
    )
    result = compute_quality_profile(
        _request((definition,), (_observation("value", 1.0),))
    )

    assert result.metrics[0].status is MetricStatus.PASS
    assert result.disposition is QualityDisposition.ACCEPTED


def test_top_level_evidence_includes_assay_profile_reference() -> None:
    definition = _definition("metric.evidence", Computation.DIRECT, ("value",))
    request = _request((definition,), (_observation("value", 0.9),))
    result = compute_quality_profile(request)

    references = {item.reference for item in result.evidence}
    assert request.assay_profile.evidence in references
