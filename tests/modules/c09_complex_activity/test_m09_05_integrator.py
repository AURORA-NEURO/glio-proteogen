"""Adversarial deterministic runtime tests for provisional M09-05."""

# Boundary tests intentionally use local imports and exact numeric invariants.
# ruff: noqa: E501, PLC0415, PLR2004

import json
from datetime import UTC, datetime
from typing import cast

import pytest

from glio_proteogen.contracts.m09_05 import (
    M0905_BASELINE_MEDIA_TYPE,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintIntegratorPolicy,
    ConstraintIntegratorStatus,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateComplexActivityConstraintsRequest,
    IntegrateComplexActivityConstraintsResult,
    IntegrateComplexActivityConstraintsVerification,
    MechanismConstraint,
    MechanismConstraintKind,
)
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
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905AuthorizationError,
    M0905ConstraintIntegrator,
    integrate_complex_activity_constraints,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.engine import (
    BuiltM0905Result,
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
        request_id="request.m09-05",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(*expressions: str) -> IntegrateComplexActivityConstraintsRequest:
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
    return IntegrateComplexActivityConstraintsRequest(
        request_id="request.m09-05",
        context=_context(),
        baseline_result=_artifact("baseline", M0905_BASELINE_MEDIA_TYPE),
        policy=ConstraintIntegratorPolicy(
            policy_id="policy.m09-05",
            version="1.0.0",
            estimator_family="deterministic_constraint_bounded_integrator",
            constraints=constraints,
            conflict_tolerance=0.1,
        ),
        source_artifacts=(_artifact("feature.1"), _artifact("feature.2")),
    )


def test_supported_integration_is_deterministic_and_replayable() -> None:
    engine = M0905ConstraintIntegrator()
    first = engine.integrate(_request("conservation_hold"))
    second = engine.integrate(_request("conservation_hold"))
    assert first.result.status is ConstraintIntegratorStatus.ESTIMATED
    assert first.result.satisfaction_report[0].status is ConstraintEvaluationStatus.SATISFIED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_hard_violation_and_unsupported_input_abstain_safely() -> None:
    engine = M0905ConstraintIntegrator()
    hard = engine.integrate(_request("force_violation"))
    unsupported = engine.integrate(_request("unsupported ontology"))
    assert hard.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert unsupported.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert not hard.result.estimates
    assert (
        unsupported.result.satisfaction_report[0].status is ConstraintEvaluationStatus.NOT_EVALUABLE
    )


def test_soft_conflict_is_visible_and_ablated() -> None:
    report = (
        M0905ConstraintIntegrator()
        .integrate(_request("soft force_violation"))
        .result.satisfaction_report[0]
    )
    assert report.severity is ConstraintSeverity.SOFT
    assert report.status is ConstraintEvaluationStatus.VIOLATED
    assert report.violation_score is not None
    assert report.ablation_effect is not None


def test_preflight_rejects_withheld_consent_and_unknown_input() -> None:
    request = _request("hold")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    blocked_refs = refs.model_copy(update={"consent": withheld})
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": blocked_refs})}
    )
    with pytest.raises(M0905AuthorizationError):
        M0905ConstraintIntegrator().integrate(blocked)
    rejected_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected = request.model_copy(
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
    with pytest.raises(M0905AuthorizationError):
        M0905ConstraintIntegrator().integrate(rejected)
    with pytest.raises(ValueError, match="valid dictionary"):
        M0905ConstraintIntegrator().integrate(object())


def test_tampering_and_public_json_operation_are_closed() -> None:
    request = _request("hold")
    engine = M0905ConstraintIntegrator()
    built = integrate_complex_activity_constraints(request)
    tampered = built.canonical_bytes.replace(b'"hold"', b'"force_violation"')
    assert not engine.verify(built.result, tampered).verified
    payload = json.dumps(request.model_dump(mode="json")).encode()
    assert payload.startswith(b"{")


def test_replay_failure_reasons_and_result_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = M0905ConstraintIntegrator()
    built = engine.integrate(_request("hold"))
    assert engine.verify(object()).reason is ConstraintReplayReason.INVALID_RESULT
    assert (
        engine.verify(built.result, cast("bytes", "not-bytes")).reason
        is ConstraintReplayReason.NON_CANONICAL
    )
    monkeypatch.setattr(
        "glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.engine.M0905_MAX_CANONICAL_RESULT_BYTES",
        1,
    )
    assert (
        engine.verify(built.result, built.canonical_bytes).reason
        is ConstraintReplayReason.OVERSIZED
    )
    with pytest.raises(ValueError, match="canonical byte"):
        engine.integrate(_request("hold"))
    with pytest.raises(ValueError, match="canonical"):
        BuiltM0905Result(built.result, b"")
    with pytest.raises(ValueError, match="digest"):
        BuiltM0905Result(
            built.result.model_copy(update={"result_digest": _DIGEST}),
            built.canonical_bytes,
        )


def test_plugin_accepts_bytes_and_rejects_forged_tokens() -> None:
    from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
        M0905Plugin,
        M0905Service,
        ValidatedM0905Request,
    )

    request = _request("hold")
    plugin = M0905Plugin(M0905Service())
    encoded = json.dumps(request.model_dump(mode="json")).encode()
    assert (
        plugin.run(plugin.validate(encoded)).result.status is ConstraintIntegratorStatus.ESTIMATED
    )
    assert (
        plugin.run(plugin.validate(bytearray(encoded))).result.status
        is ConstraintIntegratorStatus.ESTIMATED
    )
    forged = ValidatedM0905Request(request=request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_control_rejections_and_result_rederivation_are_fail_closed() -> None:
    request = _request("hold")
    identity = request.context.references.identity_lineage.model_copy(
        update={"state": IdentityLineageState.UNRESOLVED}
    )
    blocked = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"identity_lineage": identity}
                    )
                }
            )
        }
    )
    with pytest.raises(M0905AuthorizationError):
        M0905ConstraintIntegrator().integrate(blocked)
    result = M0905ConstraintIntegrator().integrate(request).result
    candidates = (
        (result.model_copy(update={"request_digest": _DIGEST}), "request digest"),
        (result.model_copy(update={"satisfaction_report": ()}), "satisfaction report"),
        (
            result.model_copy(update={"estimates": (), "abstention_reason": "missing"}),
            "estimated result",
        ),
        (result.model_copy(update={"result_digest": _DIGEST}), "result digest"),
    )
    for candidate, message in candidates:
        with pytest.raises(ValueError, match=message):
            IntegrateComplexActivityConstraintsResult.model_validate(candidate)


def test_contract_estimate_report_and_verification_shapes() -> None:
    assert (
        ConstraintAwareEstimate(
            feature_id="feature.scalar",
            kind=ConstraintEstimateKind.SCALAR,
            unit="ratio",
            estimate_value=0.4,
            support_score=1.0,
            applied_constraint_ids=("constraint.1",),
        ).estimate_value
        == 0.4
    )
    assert (
        ConstraintAwareEstimate(
            feature_id="feature.category",
            kind=ConstraintEstimateKind.CATEGORICAL,
            unit="class",
            category="active",
            support_score=1.0,
            applied_constraint_ids=("constraint.1",),
        ).category
        == "active"
    )
    with pytest.raises(ValueError, match="soft violation"):
        ConstraintSatisfactionReport(
            constraint_id="constraint.soft",
            severity=ConstraintSeverity.SOFT,
            status=ConstraintEvaluationStatus.VIOLATED,
            violation_score=0.2,
            message="missing ablation",
        )
    with pytest.raises(ValueError, match="ablation effect"):
        ConstraintSatisfactionReport(
            constraint_id="constraint.good",
            severity=ConstraintSeverity.HARD,
            status=ConstraintEvaluationStatus.SATISFIED,
            ablation_effect=0.2,
            message="unexpected ablation",
        )
    with pytest.raises(ValueError, match="verification outcome"):
        IntegrateComplexActivityConstraintsVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=_DIGEST,
            reason=ConstraintReplayReason.VERIFIED,
        )


def test_contract_negative_closures_cover_bindings_and_statuses() -> None:
    request = _request("hold")
    constraint = request.policy.constraints[0]
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
    wrong_media = request.model_copy(
        update={"baseline_result": _artifact("baseline", "application/wrong")}
    )
    with pytest.raises(ValueError, match="M09-04"):
        IntegrateComplexActivityConstraintsRequest.model_validate(wrong_media)
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )
    with pytest.raises(ValueError, match="unique"):
        IntegrateComplexActivityConstraintsRequest.model_validate(duplicate)
    with pytest.raises(ValueError, match="verified reason"):
        IntegrateComplexActivityConstraintsVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            result_digest=_DIGEST,
            reason=ConstraintReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValueError, match="trusted digest"):
        IntegrateComplexActivityConstraintsVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=_DIGEST,
            reason=ConstraintReplayReason.INVALID_RESULT,
        )
    result = M0905ConstraintIntegrator().integrate(request).result
    limited = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            )
        }
    )
    with pytest.raises(ValueError, match="supported status"):
        IntegrateComplexActivityConstraintsResult.model_validate(limited)
    abstained = M0905ConstraintIntegrator().integrate(_request("force_violation")).result
    invalid_abstained = abstained.model_copy(
        update={
            "support_decision": abstained.support_decision.model_copy(
                update={"status": SupportStatus.SUPPORTED}
            )
        }
    )
    with pytest.raises(ValueError, match="abstained result"):
        IntegrateComplexActivityConstraintsResult.model_validate(invalid_abstained)
