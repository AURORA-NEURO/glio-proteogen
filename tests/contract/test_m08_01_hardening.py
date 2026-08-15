"""Adversarial contract and replay-boundary coverage for M08-01."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from evals.m08_01.fixtures import artifact, request

from glio_proteogen.contracts.m08_01 import (
    FormalTranscriptProteinStateSchema,
    TranscriptProteinFeatureDefinition,
    TranscriptProteinFeatureValue,
    TranscriptProteinFeatureValueKind,
    TranscriptProteinInvariant,
    TranscriptProteinInvariantSeverity,
    TranscriptProteinMissingness,
    canonical_request_digest,
    normalized_request,
)
from glio_proteogen.kernel.models import (
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.engine import (
    M0801FormalStateEngine,
    _validate_json_request,
    preflight_formal_state_authorization,
    validate_transcript_protein_formal_state,
    verify_m0801_result,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.kernel import (
    M0801FormalStateKernel,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.plugin import (
    M0801Plugin,
    ValidatedM0801Request,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.service import M0801Service


def test_canonical_projection_is_stable_and_does_not_alias() -> None:
    candidate = request()
    projection = normalized_request(candidate)
    projection["request_id"] = "changed-only-copy"
    assert candidate.request_id != projection["request_id"]
    assert canonical_request_digest(candidate).startswith("sha256:")


def test_schema_rejects_duplicate_invariant_and_migration_ids() -> None:
    feature = TranscriptProteinFeatureDefinition(
        feature_id="feature.scalar",
        version="1.0.0",
        value_kind=TranscriptProteinFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(TranscriptProteinMissingness.OBSERVED,),
    )
    invariant = TranscriptProteinInvariant(
        invariant_id="invariant.same",
        expression="all_values_observed",
        severity=TranscriptProteinInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    with pytest.raises(ValueError, match="invariant ids"):
        FormalTranscriptProteinStateSchema(
            schema_id="schema.same",
            version="1.0.0",
            features=(feature,),
            invariants=(invariant, invariant),
        )


def test_feature_definition_closes_categories_and_bounds() -> None:
    with pytest.raises(ValueError, match="categorical feature requires"):
        TranscriptProteinFeatureDefinition(
            feature_id="feature.category",
            version="1.0.0",
            value_kind=TranscriptProteinFeatureValueKind.CATEGORICAL,
            unit="class",
            allowed_missingness=(TranscriptProteinMissingness.OBSERVED,),
        )
    with pytest.raises(ValueError, match="lower bound"):
        TranscriptProteinFeatureDefinition(
            feature_id="feature.scalar",
            version="1.0.0",
            value_kind=TranscriptProteinFeatureValueKind.SCALAR,
            unit="ratio",
            allowed_missingness=(TranscriptProteinMissingness.OBSERVED,),
            domain_lower=2.0,
            domain_upper=1.0,
        )


def test_kernel_observation_and_category_paths() -> None:
    kernel = M0801FormalStateKernel()
    feature = TranscriptProteinFeatureDefinition(
        feature_id="feature.category",
        version="1.0.0",
        value_kind=TranscriptProteinFeatureValueKind.CATEGORICAL,
        unit="class",
        allowed_missingness=(TranscriptProteinMissingness.OBSERVED,),
        allowed_categories=("high", "low"),
    )
    value = TranscriptProteinFeatureValue(
        feature_id=feature.feature_id,
        state=TranscriptProteinMissingness.OBSERVED,
        unit="class",
        category="high",
    )
    invariant = TranscriptProteinInvariant(
        invariant_id="invariant.category",
        expression='feature:feature.category category == "high"',
        severity=TranscriptProteinInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    assert kernel.evaluate_invariant(invariant, {feature.feature_id: value})[0].value == "satisfied"
    assert (
        kernel.evaluate_invariant(
            invariant,
            {feature.feature_id: value.model_copy(update={"category": "low"})},
        )[0].value
        == "violated"
    )
    observed = invariant.model_copy(update={"expression": "all_values_observed"})
    assert kernel.evaluate_invariant(observed, {feature.feature_id: value})[0].value == "satisfied"
    missing = value.model_copy(
        update={"state": TranscriptProteinMissingness.MISSING, "category": None}
    )
    assert (
        kernel.evaluate_invariant(observed, {feature.feature_id: missing})[0].value
        == "not_evaluable"
    )
    unbound = invariant.model_copy(update={"feature_ids": ("other",)})
    assert (
        kernel.evaluate_invariant(unbound, {feature.feature_id: value})[0].value == "not_evaluable"
    )
    not_observed = invariant.model_copy(update={"feature_ids": (feature.feature_id,)})
    assert (
        kernel.evaluate_invariant(not_observed, {feature.feature_id: missing})[0].value
        == "not_evaluable"
    )
    numeric = invariant.model_copy(update={"expression": "feature:feature.category >= 1"})
    assert (
        kernel.evaluate_invariant(numeric, {feature.feature_id: value})[0].value == "not_evaluable"
    )


def test_authorization_handles_malformed_hostile_object() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(PermissionError):
        preflight_formal_state_authorization(Hostile())


def test_json_request_limit_and_valid_bytes() -> None:
    candidate = request()
    encoded = candidate.model_dump_json().encode()
    assert (
        _validate_json_request(candidate.model_dump(mode="json"), encoded).request_id
        == candidate.request_id
    )
    with pytest.raises(ValueError, match="byte limit"):
        _validate_json_request(candidate.model_dump(mode="json"), b"x" * (4 * 1024 * 1024 + 1))


def test_engine_requires_validated_request_and_result_tamper_fails() -> None:
    engine = M0801FormalStateEngine()
    with pytest.raises(TypeError, match="validated request"):
        engine.validate_validated(object())  # type: ignore[arg-type]
    result = engine.validate(request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="digest"):
        verify_m0801_result(tampered)
    tampered_result = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="digest"):
        verify_m0801_result(tampered_result)
    assert validate_transcript_protein_formal_state(request()).result_id == result.result_id


def test_plugin_descriptor_and_service_replay_failures() -> None:
    service = M0801Service()
    plugin = M0801Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M08-01"
    token = plugin.validate(request())
    forged = ValidatedM0801Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    result = service.execute(request())
    altered_request = request(scalar=3.0)
    with pytest.raises(ValueError, match="replay request"):
        service.replay(altered_request, result)
    altered_result = result.model_copy(update={"status": "invalid"})
    with pytest.raises(ValueError, match="digest"):
        service.replay(request(), altered_result)


def test_context_reference_models_remain_strict() -> None:
    evidence = artifact("context")
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    context = ExecutionContext(
        request_id="context.request",
        actor_id="context.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )
    assert context.references.consent.state is ConsentState.GRANTED
