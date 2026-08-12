"""Focused behavior for the M02-04 identification quality framework."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationAssayProfile,
    IdentificationAssayType,
    IdentificationMetricStatus,
    IdentificationQualityDisposition,
    IdentificationQualityMetricCode,
    IdentificationQualityPolicy,
    MetricDirection,
    MetricObservation,
    MetricObservationState,
    MetricThreshold,
    configuration_digest,
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
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    IdentificationQualityAuthorizationError,
    M0204IdentificationQualityEngine,
    M0204Plugin,
    M0204Service,
)

TOP_LEVEL_EVIDENCE_COUNT = 8
MAX_METRIC_EVIDENCE_COUNT = 32
EXPECTED_RECOVERY = 1.1


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/json",
    )


def _thresholds() -> tuple[MetricThreshold, ...]:
    values = {
        IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE: (
            MetricDirection.HIGHER_IS_BETTER,
            0.70,
            None,
            0.60,
            None,
        ),
        IdentificationQualityMetricCode.TARGET_DECOY_FDR: (
            MetricDirection.LOWER_IS_BETTER,
            None,
            0.01,
            None,
            0.02,
        ),
        IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY: (
            MetricDirection.LOWER_IS_BETTER,
            None,
            5.0,
            None,
            10.0,
        ),
        IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS: (
            MetricDirection.HIGHER_IS_BETTER,
            0.80,
            None,
            0.70,
            None,
        ),
        IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY: (
            MetricDirection.WITHIN_RANGE,
            0.80,
            1.20,
            0.70,
            1.30,
        ),
        IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH: (
            MetricDirection.HIGHER_IS_BETTER,
            1.0,
            None,
            None,
            None,
        ),
    }
    return tuple(
        MetricThreshold(
            metric_code=code,
            direction=value[0],
            pass_minimum=value[1],
            pass_maximum=value[2],
            warning_minimum=value[3],
            warning_maximum=value[4],
        )
        for code, value in values.items()
    )


def _policy() -> IdentificationQualityPolicy:
    return IdentificationQualityPolicy(
        policy_id="policy.m0204.synthetic",
        version="1.0.0",
        thresholds=_thresholds(),
    )


def _context(
    policy: IdentificationQualityPolicy,
    *,
    consent: ConsentState = ConsentState.GRANTED,
) -> ExecutionContext:
    def decision(label: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(label, digest),
        )

    return ExecutionContext(
        request_id="request.m0204.synthetic",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration_digest(policy)),
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
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _observations() -> tuple[MetricObservation, ...]:
    ratios = {
        IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE: (80.0, 100.0),
        IdentificationQualityMetricCode.TARGET_DECOY_FDR: (1.0, 200.0),
        IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS: (90.0, 100.0),
        IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY: (95.0, 100.0),
    }
    values: list[MetricObservation] = []
    for code in IdentificationQualityMetricCode:
        common = {"metric_code": code, "state": MetricObservationState.OBSERVED}
        evidence = (_artifact(f"observation.{code.value}"),)
        if code in ratios:
            numerator, denominator = ratios[code]
            values.append(
                MetricObservation(
                    **common,
                    numerator=numerator,
                    denominator=denominator,
                    evidence=evidence,
                )
            )
        else:
            value: float | bool = (
                True
                if code is IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH
                else 3.5
            )
            values.append(MetricObservation(**common, value=value, evidence=evidence))
    return tuple(values)


def _request() -> ComputeIdentificationQualityRequest:
    policy = _policy()
    return ComputeIdentificationQualityRequest(
        context=_context(policy),
        assay_profile=IdentificationAssayProfile(
            profile_id="profile.m0204.dda",
            version="1.0.0",
            assay_type=IdentificationAssayType.DDA,
            target_decoy_strategy="concatenated_target_decoy",
            evidence=_artifact("assay-profile"),
        ),
        policy=policy,
        observations=_observations(),
    )


def test_all_six_metrics_pass_deterministically() -> None:
    request = _request()
    engine = M0204IdentificationQualityEngine()
    first = engine.compute(request)
    second = engine.compute(
        request.model_copy(
            update={
                "policy": request.policy.model_copy(
                    update={"thresholds": tuple(reversed(request.policy.thresholds))}
                ),
                "observations": tuple(reversed(request.observations)),
            }
        )
    )

    assert second == first
    assert first.disposition is IdentificationQualityDisposition.ACCEPTED
    assert {item.status for item in first.metrics} == {IdentificationMetricStatus.PASS}
    assert first.parent_target == "protein_subtype"
    assert first.provenance.module_id == "GLIO-PROTEOGEN-M02-04"


def test_embedded_observation_evidence_order_is_fully_canonical() -> None:
    request = _request()
    observations = tuple(
        item.model_copy(
            update={
                "evidence": (
                    _artifact(f"{item.metric_code.value}.z"),
                    _artifact(f"{item.metric_code.value}.a"),
                )
            }
        )
        for item in request.observations
    )
    ordered = request.model_copy(update={"observations": observations})
    reversed_evidence = request.model_copy(
        update={
            "observations": tuple(
                item.model_copy(update={"evidence": tuple(reversed(item.evidence))})
                for item in observations
            )
        }
    )

    first = M0204IdentificationQualityEngine().compute(ordered)
    second = M0204IdentificationQualityEngine().compute(reversed_evidence)

    assert second == first
    assert second.model_dump_json() == first.model_dump_json()
    assert second.result_digest == first.result_digest


def test_failed_fdr_quarantines() -> None:
    request = _request()
    observations = tuple(
        item.model_copy(update={"numerator": 10.0, "denominator": 100.0})
        if item.metric_code is IdentificationQualityMetricCode.TARGET_DECOY_FDR
        else item
        for item in request.observations
    )
    result = M0204IdentificationQualityEngine().compute(
        request.model_copy(update={"observations": observations})
    )

    assert result.disposition is IdentificationQualityDisposition.QUARANTINED
    fdr = next(
        item
        for item in result.metrics
        if item.metric_code is IdentificationQualityMetricCode.TARGET_DECOY_FDR
    )
    assert fdr.status is IdentificationMetricStatus.FAIL


def test_recovery_can_exceed_one() -> None:
    request = _request()
    observations = tuple(
        item.model_copy(update={"numerator": 110.0, "denominator": 100.0})
        if item.metric_code is IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY
        else item
        for item in request.observations
    )

    result = M0204IdentificationQualityEngine().compute(
        request.model_copy(update={"observations": observations})
    )
    metrics = {item.metric_code: item for item in result.metrics}

    assert (
        metrics[IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY].value
        == EXPECTED_RECOVERY
    )
    assert (
        metrics[IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY].status
        is IdentificationMetricStatus.PASS
    )


def test_contract_rejects_negative_mass_error_and_out_of_domain_ratio_threshold() -> None:
    with pytest.raises(ValueError, match="mass-error observation cannot be negative"):
        MetricObservation(
            metric_code=IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY,
            state=MetricObservationState.OBSERVED,
            value=-0.1,
            evidence=(_artifact("negative-mass-error"),),
        )
    with pytest.raises(ValueError, match="thresholds must be within zero and one"):
        MetricThreshold(
            metric_code=IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE,
            direction=MetricDirection.HIGHER_IS_BETTER,
            pass_minimum=1.1,
        )


def test_optional_censored_metric_abstains_without_becoming_zero() -> None:
    request = _request()
    code = IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY
    observations = tuple(
        MetricObservation(
            metric_code=code,
            state=MetricObservationState.CENSORED,
            upper_bound=2.0,
            evidence=item.evidence,
        )
        if item.metric_code is code
        else item
        for item in request.observations
    )
    thresholds = tuple(
        item.model_copy(update={"required": False}) if item.metric_code is code else item
        for item in request.policy.thresholds
    )
    policy = request.policy.model_copy(update={"thresholds": thresholds})
    result = M0204IdentificationQualityEngine().compute(
        ComputeIdentificationQualityRequest(
            context=_context(policy),
            assay_profile=request.assay_profile,
            policy=policy,
            observations=observations,
        )
    )

    metric = next(item for item in result.metrics if item.metric_code is code)
    assert result.disposition is IdentificationQualityDisposition.ACCEPTED
    assert metric.status is IdentificationMetricStatus.NOT_EVALUABLE
    assert metric.value is None


def test_required_missing_metric_quarantines() -> None:
    request = _request()
    code = IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS
    observations = tuple(
        MetricObservation(
            metric_code=code,
            state=MetricObservationState.MISSING,
            evidence=item.evidence,
        )
        if item.metric_code is code
        else item
        for item in request.observations
    )
    result = M0204IdentificationQualityEngine().compute(
        request.model_copy(update={"observations": observations})
    )

    assert result.disposition is IdentificationQualityDisposition.QUARANTINED


def test_denied_consent_precedes_observation_validation() -> None:
    request = _request().model_dump(mode="python")
    request["context"]["references"]["consent"]["state"] = "withheld"
    request["observations"] = {"must_not": "be traversed"}

    with pytest.raises(IdentificationQualityAuthorizationError):
        M0204IdentificationQualityEngine().compute(request)


def test_plugin_strict_json_round_trip() -> None:
    request = _request()
    plugin = M0204Plugin(M0204Service())
    token = plugin.validate(request.model_dump_json())

    assert plugin.run(token).disposition is IdentificationQualityDisposition.ACCEPTED
    assert plugin.descriptor().owner == "Quality engineering"


def test_maximum_metric_evidence_keeps_top_level_envelope_compact() -> None:
    request = _request()
    observations = tuple(
        item.model_copy(
            update={
                "evidence": tuple(
                    _artifact(f"{item.metric_code.value}.{index}")
                    for index in range(MAX_METRIC_EVIDENCE_COUNT)
                )
            }
        )
        for item in request.observations
    )

    result = M0204IdentificationQualityEngine().compute(
        request.model_copy(update={"observations": observations})
    )

    assert len(result.evidence) == TOP_LEVEL_EVIDENCE_COUNT
    assert all(len(item.evidence) == MAX_METRIC_EVIDENCE_COUNT for item in result.metrics)


def test_output_contract_rejects_forged_accepted_failure() -> None:
    result = M0204IdentificationQualityEngine().compute(_request())
    payload = result.metrics[0].model_dump(mode="python")
    payload["status"] = IdentificationMetricStatus.FAIL

    with pytest.raises(ValueError, match="status contradicts"):
        type(result.metrics[0]).model_validate(payload, strict=True)


def test_output_contract_rejects_forged_threshold_and_policy_binding() -> None:
    result = M0204IdentificationQualityEngine().compute(_request())
    metric_payload = result.metrics[0].model_dump(mode="python")
    threshold = result.metrics[0].threshold.model_copy(update={"pass_minimum": 0.75})
    metric_payload["threshold"] = threshold

    with pytest.raises(ValueError, match="threshold digest"):
        type(result.metrics[0]).model_validate(metric_payload, strict=True)

    metric_payload["provenance"] = result.metrics[0].provenance.model_copy(
        update={"threshold_digest": sha256_digest(threshold)}
    )
    metric = type(result.metrics[0]).model_validate(metric_payload, strict=True)
    profile_payload = result.model_dump(mode="python")
    profile_payload["metrics"] = (metric, *result.metrics[1:])
    profile_payload["result_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValueError, match="provenance inputs are incomplete"):
        type(result).model_validate(profile_payload, strict=True)


def test_output_contract_rejects_forged_value_and_observation() -> None:
    result = M0204IdentificationQualityEngine().compute(_request())
    metric = next(
        item
        for item in result.metrics
        if item.metric_code is IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE
    )
    payload = metric.model_dump(mode="python")
    payload["value"] = 0.85

    with pytest.raises(ValueError, match="value contradicts its observation"):
        type(metric).model_validate(payload, strict=True)

    payload = metric.model_dump(mode="python")
    observation = metric.observation.model_copy(update={"numerator": 85.0})
    payload["observation"] = observation
    payload["value"] = 0.85

    with pytest.raises(ValueError, match="observation digest"):
        type(metric).model_validate(payload, strict=True)


def test_output_contract_rejects_top_evidence_role_flip() -> None:
    result = M0204IdentificationQualityEngine().compute(_request())
    payload = result.model_dump(mode="python")
    evidence = list(result.evidence)
    evidence[0] = evidence[0].model_copy(update={"role": "counter_evidence"})
    payload["evidence"] = tuple(evidence)
    payload["result_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValueError, match="evidence claims are inconsistent"):
        type(result).model_validate(payload, strict=True)
