"""Lifecycle and safe-selection fixtures for M06-07."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_05 import (
    ConstraintAwareEstimate,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsRequest,
    IntegrateProteinAbundanceConstraintsResult,
    MechanismConstraint,
    MechanismConstraintHardness,
    MechanismConstraintKind,
    MechanismConstraintSet,
)
from glio_proteogen.contracts.m06_05.canonical import (
    canonical_request_digest as constraint_request_digest,
)
from glio_proteogen.contracts.m06_05.canonical import (
    result_payload_digest as constraint_result_digest,
)
from glio_proteogen.contracts.m06_06 import (
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m06_06.canonical import (
    canonical_request_digest as uncertainty_request_digest,
)
from glio_proteogen.contracts.m06_06.canonical import (
    result_payload_digest as uncertainty_result_digest,
)
from glio_proteogen.contracts.m06_07 import (
    M0607_NOMINAL_COVERAGE,
    CalibratedEstimate,
    CalibrateSelectiveProteinAbundanceRequest,
    CalibrateSelectiveProteinAbundanceResult,
    CalibrationMethod,
    CalibrationPolicy,
    CalibrationStratum,
    CalibrationStratumDimension,
    OutOfDistributionStatus,
    SelectivePredictionStatus,
    SelectiveSupportThreshold,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    BuiltCalibration,
    CalibrationAuthorizationError,
    CalibrationInputError,
    M0607CalibrationEngine,
    M0607Service,
    calibrate_selective_protein_abundance,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    engine as m0607_engine,
)

_COVERAGE = 0.90
_CALIBRATION_ERROR = 0.02


def _artifact(
    label: str,
    char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0607.{label}",
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0607.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(label),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0607.smoke",
        actor_id="actor.m0607.smoke",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0607.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0607.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _provenance(context: ExecutionContext, module: str) -> ProvenanceRecord:
    refs = context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    records = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in decisions
    )
    return ProvenanceRecord(
        activity_id=f"activity.{module.lower()}",
        actor_id=context.actor_id,
        module_id=module,
        module_version="0.1.0-provisional",
        generated_at=context.occurred_at,
        input_digests=("sha256:" + "e" * 64,),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=records,
    )


def _constraint_request() -> IntegrateProteinAbundanceConstraintsRequest:
    context = _context()
    feature = FormalStateFeatureDefinition(
        feature_id="protein.abundance",
        version="1.0.0",
        value_kind=FormalStateFeatureValueKind.SCALAR,
        unit="normalized-abundance",
        allowed_missingness=(FormalStateMissingness.OBSERVED,),
    )
    schema = FormalProteinStateSchema(
        schema_id="schema.formal-state",
        version="1.0.0",
        features=(feature,),
    )
    value = FormalStateFeatureValue(
        feature_id=feature.feature_id,
        state=FormalStateMissingness.OBSERVED,
        unit=feature.unit,
        scalar_value=1.5,
    )
    constraint = MechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="1.0.0",
        kind=MechanismConstraintKind.CHEMISTRY,
        hardness=MechanismConstraintHardness.HARD,
        expression="abundance >= 0",
        feature_ids=(feature.feature_id,),
    )
    return IntegrateProteinAbundanceConstraintsRequest(
        request_id="request.m0605.upstream",
        context=context,
        state_schema=schema,
        feature_values=(value,),
        constraint_set=MechanismConstraintSet(
            constraint_set_id="constraint-set.reviewed",
            version="1.0.0",
            constraints=(constraint,),
            reviewed_by="reviewer.constraints",
        ),
        advanced_estimator_result=_artifact(
            "advanced", "d", "application/vnd.glio-proteogen.m06-04+json"
        ),
        source_artifacts=(_artifact("proteome", "e"),),
    )


def _constraint_result() -> IntegrateProteinAbundanceConstraintsResult:
    request = _constraint_request()
    estimate = ConstraintAwareEstimate(
        feature_id="protein.abundance",
        unit="normalized-abundance",
        estimate_value=1.5,
    )
    evaluation = ConstraintEvaluation(
        constraint_id="constraint.nonnegative",
        outcome=ConstraintEvaluationOutcome.SATISFIED,
        residual=1.5,
        effect_size=1.0,
        message="constraint satisfied",
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="constraint_support_state",
        rationale="upstream support is present",
    )
    uncertainty = expected_uncertainty()
    draft = IntegrateProteinAbundanceConstraintsResult.model_construct(
        result_id="result.m0605.upstream",
        request_digest=constraint_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=ConstraintIntegrationStatus.INTEGRATED,
        estimates=(estimate,),
        evaluations=(evaluation,),
        ablations=(),
        support_decision=support,
        uncertainty=uncertainty,
        provenance=_provenance(request.context, "GLIO-PROTEOGEN-M06-05"),
        evidence=(),
        limitations=(Limitation(code="provisional", statement="test upstream"),),
    )
    return IntegrateProteinAbundanceConstraintsResult.model_validate(
        draft.model_copy(update={"result_digest": constraint_result_digest(draft)}),
        strict=True,
    )


def _uncertainty_request() -> DecomposeProteinAbundanceUncertaintyRequest:
    context = _context()
    policy = UncertaintyDecompositionPolicy(
        policy_id="policy.m0606.test",
        version="1.0.0",
        method="synthetic-test-policy",
        calibration_reference=_artifact("uncertainty-policy", "f"),
    )
    return DecomposeProteinAbundanceUncertaintyRequest(
        request_id="request.m0606.test",
        context=context,
        constraint_result=_constraint_result(),
        policy=policy,
        source_artifacts=(_artifact("uncertainty", "1"),),
    )


def _uncertainty_result(
    *, decomposed: bool = True
) -> ProteinAbundanceUncertaintyDecompositionResult:
    request = _uncertainty_request()
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.1,
        rationale="synthetic uncertainty estimate",
    )
    decomposition = UncertaintyDecomposition(
        decomposition_id="decomposition.m0606.test",
        components=tuple(
            UncertaintyComponent(
                dimension=dimension,
                estimate=estimate,
                rationale="synthetic component",
            )
            for dimension in UncertaintyDimension
        ),
        method="synthetic-decomposition",
        model_reference=_artifact("uncertainty-model", "2"),
    )
    sensitivity = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        nominal_coverage=_COVERAGE,
        lower_bound=0.85,
        upper_bound=0.95,
        observed_coverage=_COVERAGE,
        rationale="synthetic envelope",
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="uncertainty_support",
        rationale="synthetic support",
    )
    draft = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
        result_id="result.m0606.test",
        request_digest=uncertainty_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=UncertaintyDecompositionStatus.DECOMPOSED
        if decomposed
        else UncertaintyDecompositionStatus.ABSTAINED,
        decomposition=decomposition if decomposed else None,
        sensitivity_envelope=sensitivity
        if decomposed
        else SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            nominal_coverage=_COVERAGE,
            rationale="upstream abstained",
        ),
        findings=(),
        abstention_reason=None if decomposed else "upstream not supported",
        support_decision=support
        if decomposed
        else support.model_copy(update={"status": SupportStatus.UNSUPPORTED}),
        uncertainty=expected_uncertainty(),
        provenance=expected_provenance(
            request,
            uncertainty_request_digest(request),
            sha256_digest(request.policy),
        ),
        evidence=(),
        limitations=(Limitation(code="provisional", statement="test upstream"),),
        human_review_required=not decomposed,
    )
    return ProteinAbundanceUncertaintyDecompositionResult.model_validate(
        draft.model_copy(update={"result_digest": uncertainty_result_digest(draft)}),
        strict=True,
    )


def _request(
    *,
    upstream_decomposed: bool = True,
    calibration_error: float = _CALIBRATION_ERROR,
) -> CalibrateSelectiveProteinAbundanceRequest:
    policy = CalibrationPolicy(
        policy_id="policy.m0607.test",
        version="1.0.0",
        method=CalibrationMethod.CONFORMAL,
        target_coverage=M0607_NOMINAL_COVERAGE,
        calibration_reference=_artifact("calibration-policy", "3"),
        strata=(
            CalibrationStratum(
                stratum_id="stratum.site-a",
                dimension=CalibrationStratumDimension.SITE,
                label="site-a",
                sample_count=20,
                observed_coverage=_COVERAGE,
                calibration_error=calibration_error,
            ),
        ),
        support_threshold=SelectiveSupportThreshold(
            threshold_id="threshold.m0607.test",
            version="1.0.0",
            minimum_support_score=0.8,
            maximum_ood_score=0.2,
            maximum_calibration_error=0.1,
            target_coverage=M0607_NOMINAL_COVERAGE,
        ),
    )
    return CalibrateSelectiveProteinAbundanceRequest(
        request_id="request.m0607.smoke",
        context=_context(),
        uncertainty_result=_uncertainty_result(decomposed=upstream_decomposed),
        policy=policy,
        source_artifacts=(_artifact("calibration-source", "4"),),
    )


def test_calibration_is_deterministic_and_selects_supported_estimates() -> None:
    engine = M0607CalibrationEngine()
    first = engine.calibrate(_request())
    second = engine.calibrate(_request())
    assert first.result.status.value == "calibrated"
    assert first.result.estimates[0].selection_status.value == "selected"
    assert first.result.prediction_sets[0].labels == ("in_domain",)
    assert first.canonical_bytes == second.canonical_bytes


def test_provenance_binds_policy_evidence() -> None:
    base = _request()
    policy_evidence = EvidenceReference(
        reference=_artifact("policy-evidence", "9"),
        role="evidence",
        claim="calibration policy evidence",
    )
    request = base.model_copy(
        update={"policy": base.policy.model_copy(update={"evidence": (policy_evidence,)})}
    )
    engine = M0607CalibrationEngine()
    result = engine.calibrate(request).result
    assert policy_evidence.reference.digest in result.provenance.input_digests

    mutated_evidence = policy_evidence.model_copy(
        update={"reference": _artifact("policy-evidence-mutated", "8")}
    )
    mutated = request.model_copy(
        update={
            "policy": request.policy.model_copy(update={"evidence": (mutated_evidence,)})
        }
    )
    mutated_result = engine.calibrate(mutated).result
    assert mutated_result.provenance.input_digests != result.provenance.input_digests


def test_calibration_replay_accepts_canonical_and_rejects_tamper() -> None:
    engine = M0607CalibrationEngine()
    built = engine.calibrate(_request())
    assert engine.verify(built.result, built.canonical_bytes).verified
    tampered = built.canonical_bytes[:-1] + bytes([built.canonical_bytes[-1] ^ 1])
    rejected = engine.verify(built.result, tampered)
    assert rejected.verified is False
    assert rejected.result_digest is None


def test_calibration_replay_rejects_self_rehashed_diagnostic_mutation() -> None:
    engine = M0607CalibrationEngine()
    built = engine.calibrate(_request())
    diagnostic = built.result.diagnostics[0]
    forged_diagnostic = diagnostic.model_copy(update={"message": diagnostic.message + " forged"})
    forged = built.result.model_copy(
        update={"diagnostics": (forged_diagnostic, *built.result.diagnostics[1:])}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    verdict = engine.verify(forged, canonical_json_bytes(forged.model_dump(mode="json")))

    assert verdict.content_verified is True
    assert verdict.deterministic_verified is False
    assert verdict.verified is False
    assert verdict.result_digest is None


def test_upstream_abstention_and_bad_coverage_abstain_safely() -> None:
    engine = M0607CalibrationEngine()
    upstream = engine.calibrate(_request(upstream_decomposed=False))
    bad_coverage = engine.calibrate(_request(calibration_error=0.5))
    for built in (upstream, bad_coverage):
        assert built.result.status.value == "abstained"
        assert not built.result.estimates
        assert built.result.human_review_required is True


def test_service_wrapper_and_strict_boundary() -> None:
    request = _request()
    service = M0607Service()
    built = service.execute(request)
    wrapper = calibrate_selective_protein_abundance(request)
    assert built.canonical_bytes == wrapper.canonical_bytes
    assert service.verify(built.result, built.canonical_bytes).verified
    with pytest.raises((TypeError, ValueError)):
        service.calibrate(object())


def test_authorization_and_built_result_fail_closed() -> None:
    request = _request()
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(CalibrationAuthorizationError):
        M0607CalibrationEngine().calibrate(denied)
    built = M0607CalibrationEngine().calibrate(request)
    with pytest.raises(CalibrationInputError, match="digest"):
        BuiltCalibration(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
    with pytest.raises(CalibrationInputError, match="canonical"):
        BuiltCalibration(built.result, built.canonical_bytes + b" ")


def test_authorization_checks_identity_and_all_upstream_controls() -> None:
    request = _request()
    refs = request.context.references
    unresolved = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "identity_lineage": refs.identity_lineage.model_copy(
                                update={"state": IdentityLineageState.UNRESOLVED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(CalibrationAuthorizationError):
        M0607CalibrationEngine().calibrate(unresolved)
    rejected_quality = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "quality": refs.quality.model_copy(
                                update={"state": UpstreamDecisionState.REJECTED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(CalibrationAuthorizationError):
        M0607CalibrationEngine().calibrate(rejected_quality)


def test_quality_gate_abstains_for_missing_metrics_and_outside_coverage() -> None:
    request = _request()
    no_metrics_policy = CalibrationPolicy(
        **request.policy.model_dump(mode="python")
        | {
            "strata": (
                CalibrationStratum(
                    stratum_id="stratum.site-a",
                    dimension=CalibrationStratumDimension.SITE,
                    label="site-a",
                    sample_count=20,
                ),
            )
        }
    )
    no_metrics = request.model_copy(update={"policy": no_metrics_policy})
    outside_policy = CalibrationPolicy(
        **request.policy.model_dump(mode="python")
        | {
            "strata": (
                CalibrationStratum(
                    stratum_id="stratum.site-a",
                    dimension=CalibrationStratumDimension.SITE,
                    label="site-a",
                    sample_count=20,
                    observed_coverage=0.80,
                    calibration_error=0.02,
                ),
            )
        }
    )
    outside = request.model_copy(update={"policy": outside_policy})
    engine = M0607CalibrationEngine()
    assert engine.calibrate(no_metrics).result.status.value == "abstained"
    assert engine.calibrate(outside).result.status.value == "abstained"


def test_quality_gate_target_branch_and_result_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    high_target_policy = request.policy.model_copy(update={"target_coverage": 1.0})
    high_target = request.model_copy(update={"policy": high_target_policy})
    assert m0607_engine._quality_gate(high_target)[0] is False
    monkeypatch.setattr(m0607_engine, "M0607_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(CalibrationInputError, match="byte limit"):
        M0607CalibrationEngine().calibrate(request)


def test_invalid_and_non_bytes_replay_fail_closed() -> None:
    engine = M0607CalibrationEngine()
    assert engine.verify(object()).reason.value == "invalid_result"
    built = engine.calibrate(_request())
    rejected = engine.verify(built.result, cast("bytes", "not-canonical-bytes"))
    assert rejected.verified is False
    assert rejected.content_verified is False


def _validated_result_variant(
    built: BuiltCalibration,
    **updates: object,
) -> CalibrateSelectiveProteinAbundanceResult:
    candidate = built.result.model_copy(update=updates)
    return CalibrateSelectiveProteinAbundanceResult.model_validate(
        candidate.model_copy(update={"result_digest": result_payload_digest(candidate)}),
        strict=True,
    )


def test_result_closure_rejects_digest_support_selection_and_bindings() -> None:
    engine = M0607CalibrationEngine()
    built = engine.calibrate(_request())
    with pytest.raises(ValueError, match="request digest"):
        CalibrateSelectiveProteinAbundanceResult.model_validate(
            built.result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
            strict=True,
        )
    with pytest.raises(ValueError, match="selected estimates"):
        _validated_result_variant(built, estimates=())
    with pytest.raises(ValueError, match="supported status"):
        _validated_result_variant(
            built,
            support_decision=built.result.support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            ),
        )
    abstained = built.result.estimates[0].model_copy(
        update={
            "estimate_value": None,
            "calibration_error": None,
            "ood_status": OutOfDistributionStatus.OOD,
            "selection_status": SelectivePredictionStatus.ABSTAINED,
            "prediction_set_id": None,
            "support_score": 0.0,
        }
    )
    with pytest.raises(ValueError, match="abstained estimates"):
        _validated_result_variant(built, estimates=(abstained,))
    with pytest.raises(ValueError, match="bind a prediction set"):
        _validated_result_variant(
            built,
            estimates=(
                built.result.estimates[0].model_copy(update={"prediction_set_id": "missing"}),
            ),
        )
    with pytest.raises(ValueError, match="canonical result content"):
        CalibrateSelectiveProteinAbundanceResult.model_validate(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            strict=True,
        )


def test_result_closure_rejects_abstention_status_and_duplicate_diagnostics() -> None:
    engine = M0607CalibrationEngine()
    built = engine.calibrate(_request(upstream_decomposed=False))
    with pytest.raises(ValueError, match="no predictions"):
        _validated_result_variant(
            built,
            support_decision=built.result.support_decision.model_copy(
                update={"status": SupportStatus.SUPPORTED}
            ),
        )
    diagnostic = built.result.diagnostics[0]
    with pytest.raises(ValueError, match="diagnostic ids"):
        _validated_result_variant(built, diagnostics=(diagnostic, diagnostic))


def test_request_binding_checks_upstream_output_version_and_nominal_target() -> None:
    request = _request()
    bad_output_data = request.uncertainty_result.model_dump(mode="python")
    bad_output_data["output_type"] = "wrong-output"
    bad_output_upstream = request.uncertainty_result.model_construct(**bad_output_data)
    with pytest.raises(ValueError, match="complete M06-06"):
        request.model_copy(update={"uncertainty_result": bad_output_upstream}).request_is_bound()  # type: ignore[operator]
    bad_version_data = request.uncertainty_result.model_dump(mode="python")
    bad_version_data["result_version"] = "9.9.9"
    bad_version_upstream = request.uncertainty_result.model_construct(**bad_version_data)
    with pytest.raises(ValueError, match="provisional M06-06"):
        request.model_copy(update={"uncertainty_result": bad_version_upstream}).request_is_bound()  # type: ignore[operator]
    bad_target = request.policy.model_copy(update={"target_coverage": 0.8})
    with pytest.raises(ValueError, match="nominal 90"):
        request.model_copy(update={"policy": bad_target}).request_is_bound()  # type: ignore[operator]


def test_abstained_estimate_without_value_is_closed() -> None:
    estimate = CalibratedEstimate(
        feature_id="feature.abstained",
        support_score=0.0,
        ood_status=OutOfDistributionStatus.NOT_EVALUABLE,
        selection_status=SelectivePredictionStatus.ABSTAINED,
    )
    assert estimate.estimate_value is None
