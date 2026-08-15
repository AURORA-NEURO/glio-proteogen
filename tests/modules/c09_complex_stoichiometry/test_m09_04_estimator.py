"""Adversarial and deterministic runtime tests for provisional M09-04."""

from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.contracts.m09_04 import (
    M0904_BASELINE_MEDIA_TYPE,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    EstimatorConstraint,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    ProbabilisticReplayReason,
    ProbabilisticResultStatus,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    M0904AuthorizationError,
    M0904Plugin,
    M0904ProbabilisticEstimator,
    M0904Service,
    ValidatedM0904Request,
    create_app,
)

_DIGEST = "sha256:" + ("1" * 64)
_DIGEST_2 = "sha256:" + ("2" * 64)
_EXPECTED_ESTIMATES = 2
_EXPECTED_DIAGNOSTICS = 2


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
        request_id="request.m09-04",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(*expressions: str) -> EstimateComplexActivityProbabilisticRequest:
    constraints = tuple(
        EstimatorConstraint(
            constraint_id=f"constraint.{index}",
            expression=expression,
            hard="soft" not in expression,
            evidence=(
                EvidenceReference(
                    reference=_artifact(f"constraint-evidence.{index}"),
                    role="evidence",
                    claim="caller-declared constraint evidence",
                ),
            ),
        )
        for index, expression in enumerate(expressions, start=1)
    )
    return EstimateComplexActivityProbabilisticRequest(
        request_id="request.m09-04",
        context=_context(),
        baseline_result=_artifact("baseline", M0904_BASELINE_MEDIA_TYPE),
        configuration=ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.m09-04",
            version="1.0.0",
            estimator_family=ProbabilisticEstimatorFamily.LEARNED,
            objective="locked_complex_activity_objective",
            priors=(
                ProbabilisticPrior(
                    prior_id="prior.activity",
                    version="1.0.0",
                    kind=ProbabilisticPriorKind.NORMAL,
                    parameters=(0.5, 0.2),
                    evidence=(
                        EvidenceReference(
                            reference=_artifact("prior-evidence.1"),
                            role="evidence",
                            claim="caller-declared prior evidence",
                        ),
                    ),
                ),
            ),
            constraints=constraints,
            optimizer="deterministic_reference_optimizer",
            seed=17,
            max_iterations=12,
            reference=_artifact("model-reference.1"),
        ),
        source_artifacts=(_artifact("feature.1"), _artifact("feature.2")),
    )


def test_supported_estimate_is_deterministic_and_replayable() -> None:
    engine = M0904ProbabilisticEstimator()
    first = engine.build(_request("stable_support"))
    second = engine.build(_request("stable_support"))

    assert first.result.status is ProbabilisticResultStatus.ESTIMATED
    assert len(first.result.estimates) == _EXPECTED_ESTIMATES
    assert first.result.estimates[0].lower_bound <= first.result.estimates[0].estimate_value
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_unsupported_and_ood_markers_abstain_without_estimates() -> None:
    for expression in ("unsupported PTM", "OOD transport", "missing assay"):
        built = M0904Service().build(_request(expression))
        assert built.result.status is ProbabilisticResultStatus.ABSTAINED
        assert not built.result.estimates
        assert built.result.support_decision.status is SupportStatus.UNSUPPORTED
        assert built.result.abstention_reason is not None
        assert all(
            item.state.value == "not_estimable"
            for item in (
                built.result.uncertainty.measurement,
                built.result.uncertainty.sampling,
                built.result.uncertainty.parameter,
                built.result.uncertainty.model_form,
                built.result.uncertainty.identification,
                built.result.uncertainty.support,
                built.result.uncertainty.transport,
            )
        )


def test_nonconverged_declaration_is_review_abstention() -> None:
    built = M0904ProbabilisticEstimator().build(_request("non_converged objective"))
    assert built.result.status is ProbabilisticResultStatus.ABSTAINED
    assert built.result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert built.result.diagnostics[0].status is OptimizationDiagnosticStatus.FAILED


def test_soft_constraint_is_visible_and_does_not_silently_change_output() -> None:
    built = M0904ProbabilisticEstimator().build(_request("soft stability"))
    assert built.result.status is ProbabilisticResultStatus.ESTIMATED
    assert len(built.result.diagnostics) == _EXPECTED_DIAGNOSTICS
    assert "Soft constraint" in built.result.diagnostics[1].message


def test_hard_unsupported_constraint_abstains() -> None:
    built = M0904ProbabilisticEstimator().build(_request("unsupported hard prior"))
    assert built.result.status is ProbabilisticResultStatus.ABSTAINED
    assert built.result.support_decision.status is SupportStatus.UNSUPPORTED


def test_preflight_rejects_withheld_consent() -> None:
    request = _request("stable_support")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": refs.model_copy(update={"consent": withheld})}
            )
        }
    )
    with pytest.raises(M0904AuthorizationError):
        M0904ProbabilisticEstimator().build(denied)


def test_replay_rejects_tampered_bytes_and_invalid_token() -> None:
    service = M0904Service()
    plugin = M0904Plugin(service)
    built = service.build(_request("stable_support"))
    tampered = built.canonical_bytes.replace(b"stable_support", b"stable_corrupt")
    verification = service.verify(built.result, tampered)

    assert not verification.verified
    assert verification.reason is ProbabilisticReplayReason.NON_CANONICAL
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0904Request(request=built.result.request, _seal=object()))


def test_contract_closes_nonfinite_values_and_diagnostic_requirements() -> None:
    with pytest.raises(ValueError, match="finite"):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.bad",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective="objective",
            iteration_count=1,
            objective_value=float("nan"),
            convergence_gap=0.1,
            message="bad",
        )
    with pytest.raises(ValueError, match="converged"):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.bad",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective="objective",
            iteration_count=1,
            message="missing convergence data",
        )


def test_invalid_result_and_oversized_replay_are_safe() -> None:
    engine = M0904ProbabilisticEstimator()
    invalid = engine.verify(object())
    oversized = engine.verify(object(), b"x" * (8 * 1024 * 1024 + 1))
    assert invalid.reason is ProbabilisticReplayReason.INVALID_RESULT
    assert oversized.reason is ProbabilisticReplayReason.INVALID_RESULT


def test_plugin_json_submission_and_descriptor_boundary() -> None:
    request = _request("stable_support")
    plugin = M0904Plugin(M0904Service())
    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-04"
    assert result.status is ProbabilisticResultStatus.ESTIMATED


def test_result_revalidation_rejects_status_and_digest_drift() -> None:
    result = M0904ProbabilisticEstimator().build(_request("stable_support")).result
    with pytest.raises(ValueError, match="request digest"):
        EstimateComplexActivityProbabilisticResult.model_validate(
            result.model_copy(update={"request_digest": _DIGEST})
        )
    with pytest.raises(ValueError, match="estimated result"):
        EstimateComplexActivityProbabilisticResult.model_validate(
            result.model_copy(update={"estimates": (), "abstention_reason": "missing"})
        )


def test_api_schema_validate_estimate_and_verify() -> None:
    request = _request("stable_support")
    with TestClient(create_app(M0904Service())) as client:
        schema = client.get("/v1/modules/M09-04/schemas/verification")
        validated = client.post("/v1/modules/M09-04/validate", json=request.model_dump(mode="json"))
        estimated = client.post("/v1/modules/M09-04/estimate", json=request.model_dump(mode="json"))
        verified = client.post(
            "/v1/modules/M09-04/verify",
            json=estimated.json()["result"],
        )
    assert schema.status_code == HTTPStatus.OK
    assert validated.status_code == HTTPStatus.OK
    assert estimated.status_code == HTTPStatus.OK
    assert estimated.json()["result"]["status"] == "estimated"
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True
