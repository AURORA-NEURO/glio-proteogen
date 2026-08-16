"""Adversarial contract and runtime checks for provisional M06-04."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_04 import (
    EstimatorConstraint,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
)
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
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604_PROXY_OPTIMIZER,
    M0604ProbabilisticEstimatorEngine,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorInputError,
)

_PROXY_VALUE = 4.0
_CONTROL_COUNT = 7
_INTERVAL_LOWER = 2.0
_INTERVAL_UPPER = 6.0


def _artifact(name: str, offset: int = 0) -> ArtifactReference:
    letter = chr(ord("a") + offset)
    return ArtifactReference(
        artifact_id=f"{name}.{letter}",
        version="1.0.0",
        digest="sha256:" + (letter * 64),
        media_type="application/json",
    )


def _upstream(name: str, evidence: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )


def _context() -> ExecutionContext:
    evidence = _artifact("control", 0)
    return ExecutionContext(
        request_id="request.m0604",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_upstream("configuration", evidence),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + ("1" * 64),
                evidence=evidence,
            ),
            provenance=_upstream("provenance", evidence),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=_upstream("quality", evidence),
            support=_upstream("support", evidence),
            intended_use=_upstream("intended-use", evidence),
        ),
    )


def _schema(*, category: bool = False) -> FormalProteinStateSchema:
    feature = FormalStateFeatureDefinition(
        feature_id="protein.abundance",
        version="1.0.0",
        value_kind=(
            FormalStateFeatureValueKind.CATEGORICAL
            if category
            else FormalStateFeatureValueKind.SCALAR
        ),
        unit="normalized-abundance" if not category else "class",
        allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING),
        domain_lower=None if category else 0.0,
        allowed_categories=("low", "high") if category else (),
    )
    return FormalProteinStateSchema(
        schema_id="schema.m0604",
        version="1.0.0",
        features=(feature,),
    )


def _configuration(
    schema: FormalProteinStateSchema,
    *,
    family: ProbabilisticEstimatorFamily = ProbabilisticEstimatorFamily.MECHANISM_GUIDED,
    optimizer: str = M0604_PROXY_OPTIMIZER,
) -> ProbabilisticEstimatorConfiguration:
    return ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m0604",
        version="1.0.0",
        estimator_family=family,
        state_schema_id=schema.schema_id,
        state_schema_version=schema.version,
        objective="estimate normalized abundance",
        priors=(
            ProbabilisticPrior(
                prior_id="prior.abundance",
                version="1.0.0",
                kind=ProbabilisticPriorKind.NORMAL,
                parameters=(0.0, 1.0),
            ),
        ),
        constraints=(
            EstimatorConstraint(
                constraint_id="constraint.nonnegative",
                expression="protein.abundance >= 0",
                hard=True,
            ),
        ),
        optimizer=optimizer,
        seed=7,
        max_iterations=100,
        reference=_artifact("configuration", 2),
    )


def _request(
    *,
    value: FormalStateFeatureValue | None = None,
    schema: FormalProteinStateSchema | None = None,
    family: ProbabilisticEstimatorFamily = ProbabilisticEstimatorFamily.MECHANISM_GUIDED,
    optimizer: str = M0604_PROXY_OPTIMIZER,
):
    selected_schema = schema or _schema()
    selected_value = value or FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="normalized-abundance",
        scalar_value=_PROXY_VALUE,
    )
    return {
        "request_id": "request.m0604",
        "context": _context(),
        "state_schema": selected_schema,
        "feature_values": (selected_value,),
        "representation_artifact": _artifact("representation", 3),
        "baseline_result_digest": None,
        "configuration": _configuration(selected_schema, family=family, optimizer=optimizer),
        "source_artifacts": (_artifact("source", 4),),
        "supersedes_result_digest": None,
    }


def test_mechanism_guided_proxy_emits_typed_result_and_provenance() -> None:
    result = M0604ProbabilisticEstimatorEngine().estimate(_request())

    assert result.status.value == "estimated"
    assert result.estimates[0].estimate_value == _PROXY_VALUE
    assert result.parent_target == "biomarker_panel"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.result_digest.startswith("sha256:")


def test_typed_and_json_replay_are_identical() -> None:
    request = _request()
    typed = M0604ProbabilisticEstimatorEngine().estimate(request)
    serialized = json.dumps(
        {
            key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            for key, value in request.items()
        },
        default=lambda value: value.model_dump(mode="json"),
    )
    replay = M0604ProbabilisticEstimatorEngine().estimate(serialized)

    assert replay == typed


def test_learned_family_abstains_without_model_artifact_execution() -> None:
    result = M0604ProbabilisticEstimatorEngine().estimate(
        _request(family=ProbabilisticEstimatorFamily.LEARNED)
    )

    assert result.status.value == "abstained"
    assert not result.estimates
    assert result.support_decision.status.value == "review_required"
    assert "not authorized" in (result.abstention_reason or "")


def test_unknown_optimizer_abstains() -> None:
    result = M0604ProbabilisticEstimatorEngine().estimate(_request(optimizer="unknown-v2"))

    assert result.status.value == "abstained"
    assert result.diagnostics[0].status.value == "not_evaluable"


def test_missing_feature_is_explicitly_abstained() -> None:
    value = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.MISSING,
        unit="normalized-abundance",
    )
    result = M0604ProbabilisticEstimatorEngine().estimate(_request(value=value))

    assert result.status.value == "abstained"
    assert result.abstention_reason is not None
    assert not result.estimates


def test_interval_feature_preserves_ordered_bounds() -> None:
    value = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="normalized-abundance",
        interval_lower=_INTERVAL_LOWER,
        interval_upper=_INTERVAL_UPPER,
    )
    result = M0604ProbabilisticEstimatorEngine().estimate(_request(value=value))

    assert result.status.value == "estimated"
    assert result.estimates[0].estimate_value == _PROXY_VALUE
    assert result.estimates[0].lower_bound == _INTERVAL_LOWER
    assert result.estimates[0].upper_bound == _INTERVAL_UPPER


def test_categorical_feature_abstains_without_numeric_proxy() -> None:
    schema = _schema(category=True)
    value = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="class",
        category="high",
    )
    result = M0604ProbabilisticEstimatorEngine().estimate(_request(schema=schema, value=value))

    assert result.status.value == "abstained"
    assert not result.estimates


def test_denied_consent_fails_before_estimation() -> None:
    request = _request()
    context = request["context"]
    references = context.references.model_copy(
        update={
            "consent": context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    denied = dict(request)
    denied["context"] = context.model_copy(update={"references": references})

    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0604ProbabilisticEstimatorEngine().estimate(denied)


def test_unresolved_identity_fails_before_estimation() -> None:
    request = _request()
    context = request["context"]
    references = context.references.model_copy(
        update={
            "identity_lineage": context.references.identity_lineage.model_copy(
                update={"state": IdentityLineageState.UNRESOLVED}
            )
        }
    )
    denied = dict(request)
    denied["context"] = context.model_copy(update={"references": references})

    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0604ProbabilisticEstimatorEngine().estimate(denied)


def test_missing_control_object_is_authorization_failure() -> None:
    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0604ProbabilisticEstimatorEngine().estimate({"request_id": "request.m0604"})


def test_non_mapping_input_is_rejected_without_reflection() -> None:
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0604ProbabilisticEstimatorEngine().estimate(42)


def test_duplicate_json_keys_are_rejected() -> None:
    request = _request()
    payload = {
        key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for key, value in request.items()
    }
    serialized = (
        json.dumps(payload, default=lambda value: value.model_dump(mode="json"))[:-1]
        + ',"request_id":"request.duplicate"}'
    )

    with pytest.raises(ProbabilisticEstimatorInputError):
        M0604ProbabilisticEstimatorEngine().estimate(serialized)


def test_unknown_request_field_is_rejected() -> None:
    payload = _request()
    payload["untrusted"] = "ignored"

    with pytest.raises(ProbabilisticEstimatorInputError):
        M0604ProbabilisticEstimatorEngine().estimate(payload)


def test_non_string_mapping_key_is_rejected() -> None:
    payload = _request()
    payload["context"] = {1: "not-a-context"}

    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0604ProbabilisticEstimatorEngine().estimate(payload)


def test_unit_and_domain_binding_are_strict() -> None:
    wrong_unit = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="wrong-unit",
        scalar_value=_PROXY_VALUE,
    )
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0604ProbabilisticEstimatorEngine.validate_request(_request(value=wrong_unit))

    out_of_domain = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="normalized-abundance",
        scalar_value=-1.0,
    )
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0604ProbabilisticEstimatorEngine.validate_request(_request(value=out_of_domain))


def test_duplicate_prior_and_constraint_ids_are_rejected() -> None:
    schema = _schema()
    prior = ProbabilisticPrior(
        prior_id="prior.same",
        version="1.0.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    with pytest.raises(ValidationError):
        ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.duplicate",
            version="1.0.0",
            estimator_family=ProbabilisticEstimatorFamily.MECHANISM_GUIDED,
            state_schema_id=schema.schema_id,
            state_schema_version=schema.version,
            objective="objective",
            priors=(prior, prior),
            optimizer=M0604_PROXY_OPTIMIZER,
            seed=1,
            max_iterations=1,
            reference=_artifact("configuration", 2),
        )


def test_result_replay_preserves_supersession_binding() -> None:
    original = M0604ProbabilisticEstimatorEngine().estimate(_request())
    payload = _request()
    payload["supersedes_result_digest"] = original.result_digest
    revised = M0604ProbabilisticEstimatorEngine().estimate(payload)

    assert revised.request.supersedes_result_digest == original.result_digest
    assert revised.result_digest != original.result_digest
