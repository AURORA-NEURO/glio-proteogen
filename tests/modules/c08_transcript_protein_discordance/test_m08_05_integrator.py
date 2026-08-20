"""Adversarial and deterministic runtime tests for provisional M08-05."""

# ruff: noqa: E501

import json
from datetime import UTC, datetime

import pytest

import glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator.engine as engine_module
from glio_proteogen.contracts.m08_05 import (
    M0805_BASELINE_MEDIA_TYPE,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintIntegratorPolicy,
    ConstraintIntegratorStatus,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateTranscriptProteinConstraintsRequest,
    IntegrateTranscriptProteinConstraintsResult,
    IntegrateTranscriptProteinConstraintsVerification,
    MechanismConstraint,
    MechanismConstraintKind,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805AuthorizationError,
    M0805ConstraintIntegrator,
    M0805Plugin,
    M0805Service,
    ValidatedM0805Request,
    integrate_transcript_protein_constraints,
)

_DIGEST = "sha256:" + ("1" * 64)
_DIGEST_2 = "sha256:" + ("2" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST if name.endswith("1") else _DIGEST_2,
        media_type=media_type,
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    identity = IdentityLineageReference(
        decision_id="decision.identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=_DIGEST,
        evidence=_artifact("evidence.identity"),
    )
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=identity,
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended_use"),
    )
    return ExecutionContext(
        request_id="request.m08-05",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(*expressions: str) -> IntegrateTranscriptProteinConstraintsRequest:
    references = (_artifact("feature.1"), _artifact("feature.2"))
    constraints = tuple(
        MechanismConstraint(
            constraint_id=f"constraint.{index}",
            version="1.0.0",
            kind=MechanismConstraintKind.CONSERVATION,
            expression=expression,
            severity=(ConstraintSeverity.SOFT if "soft" in expression else ConstraintSeverity.HARD),
            reference=_artifact(f"constraint-ref.{index}"),
        )
        for index, expression in enumerate(expressions, start=1)
    )
    return IntegrateTranscriptProteinConstraintsRequest(
        request_id="request.m08-05",
        context=_context(),
        baseline_result=_artifact("baseline", M0805_BASELINE_MEDIA_TYPE),
        policy=ConstraintIntegratorPolicy(
            policy_id="policy.m08-05",
            version="1.0.0",
            estimator_family="deterministic_constraint_bounded_integrator",
            constraints=constraints,
            conflict_tolerance=0.1,
        ),
        source_artifacts=references,
    )


def test_supported_integration_is_deterministic_and_replayable() -> None:
    engine = M0805ConstraintIntegrator()
    first = engine.integrate(_request("conservation_hold"))
    second = engine.integrate(_request("conservation_hold"))

    assert first.result.status is ConstraintIntegratorStatus.ESTIMATED
    assert first.result.satisfaction_report[0].status is ConstraintEvaluationStatus.SATISFIED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_replay_rejects_self_rehashed_report_mutation() -> None:
    engine = M0805ConstraintIntegrator()
    built = engine.integrate(_request("conservation_hold"))
    report = built.result.satisfaction_report[0]
    forged_report = report.model_copy(update={"message": report.message + " forged"})
    forged = built.result.model_copy(
        update={"satisfaction_report": (forged_report, *built.result.satisfaction_report[1:])}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    verdict = engine.verify(forged, canonical_json_bytes(forged.model_dump(mode="json")))

    assert verdict.content_verified is True
    assert verdict.deterministic_verified is False
    assert verdict.verified is False
    assert verdict.result_digest is None


def test_hard_violation_abstains_without_estimates() -> None:
    built = M0805Service().integrate(_request("force_violation"))

    assert built.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert not built.result.estimates
    assert built.result.support_decision.status.value == "review_required"
    assert built.result.abstention_reason is not None


def test_soft_conflict_is_visible_without_hidden_prior_dominance() -> None:
    built = M0805ConstraintIntegrator().integrate(_request("soft force_violation"))

    assert built.result.status is ConstraintIntegratorStatus.ESTIMATED
    report = built.result.satisfaction_report[0]
    assert report.severity is ConstraintSeverity.SOFT
    assert report.status is ConstraintEvaluationStatus.VIOLATED
    assert report.violation_score is not None


def test_unevaluable_constraint_abstains_safely() -> None:
    built = M0805ConstraintIntegrator().integrate(_request("unsupported ontology"))

    assert built.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert built.result.satisfaction_report[0].status is ConstraintEvaluationStatus.NOT_EVALUABLE
    assert not built.result.estimates


def test_preflight_rejects_withheld_consent() -> None:
    request = _request("conservation_hold")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": refs.model_copy(update={"consent": withheld})}
            )
        }
    )
    with pytest.raises(M0805AuthorizationError):
        M0805ConstraintIntegrator().integrate(request)


def test_replay_rejects_tampered_bytes_and_invalid_token() -> None:
    service = M0805Service()
    plugin = M0805Plugin(service)
    request = _request("conservation_hold")
    built = service.integrate(request)
    tampered = built.canonical_bytes.replace(b"conservation_hold", b"force_violation")
    verification = service.verify(built.result, tampered)

    assert not verification.verified
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0805Request(request=request, _seal=object()))


def test_contract_closures_reject_malformed_shapes_and_duplicate_policy_ids() -> None:
    constraint = _request("conservation_hold").policy.constraints[0]
    with pytest.raises(ValueError, match="unique"):
        ConstraintIntegratorPolicy(
            policy_id="policy.duplicate",
            version="1.0.0",
            estimator_family="deterministic",
            constraints=(constraint, constraint),
            conflict_tolerance=0.1,
        )
    with pytest.raises(ValueError, match="scalar"):
        ConstraintAwareEstimate(
            feature_id="feature.bad",
            kind=ConstraintEstimateKind.SCALAR,
            unit="ratio",
            support_score=1.0,
            applied_constraint_ids=("constraint.1",),
        )
    with pytest.raises(ValueError, match="interval"):
        ConstraintAwareEstimate(
            feature_id="feature.bad",
            kind=ConstraintEstimateKind.INTERVAL,
            unit="ratio",
            estimate_value=0.5,
            lower_bound=0.8,
            upper_bound=0.9,
            support_score=1.0,
            applied_constraint_ids=("constraint.1",),
        )
    with pytest.raises(ValueError, match="categorical"):
        ConstraintAwareEstimate(
            feature_id="feature.bad",
            kind=ConstraintEstimateKind.CATEGORICAL,
            unit="class",
            estimate_value=0.5,
            support_score=1.0,
            applied_constraint_ids=("constraint.1",),
        )
    with pytest.raises(ValueError, match="violation score"):
        ConstraintSatisfactionReport(
            constraint_id="constraint.bad",
            severity=ConstraintSeverity.HARD,
            status=ConstraintEvaluationStatus.VIOLATED,
            message="missing score",
        )
    with pytest.raises(ValueError, match="violation score"):
        ConstraintSatisfactionReport(
            constraint_id="constraint.bad",
            severity=ConstraintSeverity.HARD,
            status=ConstraintEvaluationStatus.SATISFIED,
            violation_score=0.1,
            message="unexpected score",
        )


def test_contract_replay_flags_are_closed_and_request_media_is_bound() -> None:
    with pytest.raises(ValueError, match="verified"):
        IntegrateTranscriptProteinConstraintsVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=_DIGEST,
            reason=ConstraintReplayReason.VERIFIED,
        )
    with pytest.raises(ValueError, match="digest"):
        IntegrateTranscriptProteinConstraintsVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=_DIGEST,
            reason=ConstraintReplayReason.INVALID_RESULT,
        )
    with pytest.raises(ValueError, match="provisional M08-04"):
        _request("conservation_hold").model_copy(
            update={"baseline_result": _artifact("wrong", "application/wrong")}
        ).__class__.model_validate(
            _request("conservation_hold").model_copy(
                update={"baseline_result": _artifact("wrong", "application/wrong")}
            )
        )


def test_runtime_boundaries_cover_duplicate_inputs_and_replay_failures(monkeypatch) -> None:
    request = _request("conservation_hold")
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )
    duplicate_result = M0805ConstraintIntegrator().integrate(duplicate)
    assert duplicate_result.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert (
        M0805ConstraintIntegrator().verify(object()).reason is ConstraintReplayReason.INVALID_RESULT
    )
    engine_module.preflight_m0805_authorization(object())
    with pytest.raises(ValueError, match="valid dictionary"):
        M0805ConstraintIntegrator().integrate(object())
    with pytest.raises(M0805AuthorizationError):
        engine_module.preflight_m0805_authorization(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={
                                    "identity_lineage": request.context.references.identity_lineage.model_copy(
                                        update={"state": IdentityLineageState.UNRESOLVED}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        )
    rejected_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected_request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"quality": rejected_quality}
                    )
                }
            )
        }
    )
    with pytest.raises(M0805AuthorizationError):
        M0805ConstraintIntegrator().integrate(rejected_request)
    monkeypatch.setattr(engine_module, "M0805_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="canonical byte"):
        M0805ConstraintIntegrator().integrate(request)
    assert not M0805ConstraintIntegrator().verify(duplicate_result.result, b"xx").verified
    with pytest.raises(ValueError, match="canonical"):
        engine_module.BuiltM0805Result(duplicate_result.result, b"")
    with pytest.raises(ValueError, match="digest"):
        engine_module.BuiltM0805Result(
            duplicate_result.result.model_copy(update={"result_digest": _DIGEST}),
            duplicate_result.canonical_bytes,
        )


def test_public_function_and_mapping_canonical_projection() -> None:
    request = _request("conservation_hold")
    assert canonical_request_digest(request.model_dump(mode="json")).startswith("sha256:")
    assert (
        integrate_transcript_protein_constraints(request).result.status
        is ConstraintIntegratorStatus.ESTIMATED
    )


def test_plugin_descriptor_and_json_submission_path() -> None:
    request = _request("conservation_hold")
    plugin = M0805Plugin(M0805Service())
    token = plugin.validate(json.dumps(request.model_dump(mode="json")).encode("utf-8"))
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M08-05"
    assert plugin.run(token).result.status is ConstraintIntegratorStatus.ESTIMATED


def test_result_rederivation_rejects_digest_report_and_status_drift() -> None:
    engine = M0805ConstraintIntegrator()
    estimated = engine.integrate(_request("conservation_hold")).result
    abstained = engine.integrate(_request("force_violation")).result
    estimate = estimated.estimates[0]

    cases = (
        (estimated.model_copy(update={"request_digest": _DIGEST}), "request digest"),
        (estimated.model_copy(update={"satisfaction_report": ()}), "satisfaction report"),
        (
            estimated.model_copy(update={"estimates": (), "abstention_reason": "missing"}),
            "estimated result",
        ),
        (
            estimated.model_copy(
                update={
                    "support_decision": estimated.support_decision.model_copy(
                        update={"status": SupportStatus.REVIEW_REQUIRED}
                    )
                }
            ),
            "supported status",
        ),
        (abstained.model_copy(update={"estimates": (estimate,)}), "abstained result"),
        (estimated.model_copy(update={"result_digest": _DIGEST}), "result digest"),
    )
    for candidate, message in cases:
        with pytest.raises(ValueError, match=message):
            IntegrateTranscriptProteinConstraintsResult.model_validate(candidate)
