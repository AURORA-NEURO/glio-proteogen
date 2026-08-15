"""Contract, replay, and adversarial-boundary tests for M06-01."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m06_01 import (
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateInvariant,
    FormalStateInvariantSeverity,
    FormalStateMigrationRule,
    FormalStateMissingness,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
    contract_json_schemas,
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
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    FormalStateAuthorizationError,
    FormalStateInputError,
    M0601FormalStateEngine,
    M0601Plugin,
    M0601Service,
    M0601Submission,
    ValidatedM0601Request,
    validate_formal_protein_state,
)

_DIGEST = "sha256:" + "a" * 64
_SCHEMA_COUNT = 8


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m0601.{name}",
        version="1.0.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def _context(
    *, quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ExecutionContext:
    evidence = _artifact("control")

    def decision(name: str, state: UpstreamDecisionState) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.m0601.{name}",
            state=state,
            policy_version="1.0.0",
            evidence=evidence,
        )

    return ExecutionContext(
        request_id="request.m0601",
        actor_id="actor.m0601",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", UpstreamDecisionState.ACCEPTED),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0601.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=decision("provenance", UpstreamDecisionState.ACCEPTED),
            consent=ConsentReference(
                decision_id="decision.m0601.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=decision("quality", quality),
            support=decision("support", UpstreamDecisionState.ACCEPTED),
            intended_use=decision("intended-use", UpstreamDecisionState.ACCEPTED),
        ),
    )


def _schema(*, include_category: bool = True) -> FormalProteinStateSchema:
    features = [
        FormalStateFeatureDefinition(
            feature_id="protein.abundance",
            version="1.0.0",
            value_kind=FormalStateFeatureValueKind.SCALAR,
            unit="normalized",
            allowed_missingness=(
                FormalStateMissingness.OBSERVED,
                FormalStateMissingness.MISSING,
                FormalStateMissingness.UNKNOWN,
            ),
            domain_lower=0.0,
            domain_upper=1.0,
        )
    ]
    if include_category:
        features.append(
            FormalStateFeatureDefinition(
                feature_id="subtype",
                version="1.0.0",
                value_kind=FormalStateFeatureValueKind.CATEGORICAL,
                unit="label",
                allowed_missingness=(FormalStateMissingness.OBSERVED,),
                allowed_categories=("class_a", "class_b"),
            )
        )
    return FormalProteinStateSchema(
        schema_id="schema.m0601.formal-state",
        version="1.0.0",
        features=tuple(features),
        invariants=(
            FormalStateInvariant(
                invariant_id="invariant.abundance.nonnegative",
                expression="protein.abundance >= 0",
                severity=FormalStateInvariantSeverity.ERROR,
                feature_ids=("protein.abundance",),
            ),
            FormalStateInvariant(
                invariant_id="invariant.subtype.closed",
                expression='subtype == "class_a"',
                severity=FormalStateInvariantSeverity.WARNING,
                feature_ids=("subtype",),
            ),
        ),
    )


def _request(
    *,
    abundance: float | None = 0.5,
    subtype: str | None = "class_a",
    abundance_state: FormalStateMissingness = FormalStateMissingness.OBSERVED,
    expression: str | None = None,
    context: ExecutionContext | None = None,
) -> ValidateFormalProteinStateRequest:
    schema = _schema()
    if expression is not None:
        schema = schema.model_copy(
            update={
                "invariants": (
                    schema.invariants[0].model_copy(update={"expression": expression}),
                    schema.invariants[1],
                )
            }
        )
    values = (
        FormalStateFeatureValue(
            feature_id="protein.abundance",
            state=abundance_state,
            unit="normalized",
            scalar_value=abundance,
        ),
        FormalStateFeatureValue(
            feature_id="subtype",
            state=(
                FormalStateMissingness.OBSERVED
                if subtype is not None
                else FormalStateMissingness.UNKNOWN
            ),
            unit="label",
            category=subtype,
        ),
    )
    return ValidateFormalProteinStateRequest(
        request_id="request.m0601",
        context=context or _context(),
        state_schema=schema,
        values=values,
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
    )


def test_valid_state_is_deterministic_across_typed_and_json_replay() -> None:
    request = _request()
    first = validate_formal_protein_state(request)
    replay = validate_formal_protein_state(request.model_dump(mode="json"))

    assert first == replay
    assert first.status.value == "valid"
    assert first.request_digest == replay.request_digest
    assert first.result_digest == replay.result_digest
    assert all(item.status.value == "satisfied" for item in first.invariant_results)


def test_violated_invariant_is_invalid_and_unsupported() -> None:
    result = M0601FormalStateEngine().validate(
        _request(abundance=0.0, expression="protein.abundance > 0")
    )

    assert result.status.value == "invalid"
    assert result.support_decision.status.value == "unsupported"
    assert result.invariant_results[0].status.value == "violated"
    assert result.emits_parent is False


def test_missing_or_unknown_state_abstains_without_negative_inference() -> None:
    result = M0601Service().execute(
        _request(abundance=None, abundance_state=FormalStateMissingness.MISSING)
    )

    assert result.status.value == "abstained"
    assert result.support_decision.status.value == "review_required"
    assert result.invariant_results[0].status.value == "not_evaluable"
    assert "negative" not in result.model_dump(mode="json")


def test_unsupported_expression_and_type_mismatch_abstain() -> None:
    expression_result = M0601Service().execute(_request(expression="protein.abundance + 1"))
    category_result = M0601Service().execute(_request(expression='protein.abundance == "class_a"'))

    assert expression_result.status.value == "abstained"
    assert category_result.status.value == "abstained"


def test_authorization_preflight_rejects_denied_control_before_execution() -> None:
    with pytest.raises(FormalStateAuthorizationError):
        M0601FormalStateEngine().validate(
            _request(context=_context(quality=UpstreamDecisionState.REJECTED))
        )


def test_strict_json_and_unknown_fields_fail_closed() -> None:
    payload = _request().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(FormalStateInputError):
        M0601FormalStateEngine().validate(payload)
    with pytest.raises(FormalStateInputError):
        M0601FormalStateEngine().validate(b"not-json")


def test_byte_cap_and_non_mapping_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _request().model_dump(mode="json")
    payload["padding"] = "x" * (M0601_MAX_CANONICAL_REQUEST_BYTES + 1)
    with pytest.raises(FormalStateInputError):
        M0601FormalStateEngine().validate(payload)
    with pytest.raises(FormalStateInputError):
        M0601FormalStateEngine().validate(object())

    monkeypatch.setattr(
        "glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema.engine.M0601_MAX_CANONICAL_REQUEST_BYTES",
        0,
    )
    with pytest.raises(FormalStateInputError):
        M0601FormalStateEngine().validate(_request())


def test_plugin_service_and_cli_token_parity() -> None:
    plugin = M0601Plugin(M0601Service())
    request = _request()
    typed = plugin.run(plugin.validate(M0601Submission(request)))
    serialized = plugin.run(plugin.validate(request.model_dump_json()))

    assert typed == serialized
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M06-01"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(ValidatedM0601Request(request=request, _seal=object()))


def test_result_digest_tampering_is_rejected() -> None:
    result = validate_formal_protein_state(_request())
    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + "f" * 64

    with pytest.raises(ValidationError, match="result digest"):
        ValidateFormalProteinStateResult.model_validate(payload)


def test_schema_and_migration_invariants_are_closed() -> None:
    with pytest.raises(ValidationError, match="differ"):
        FormalStateMigrationRule(
            source_version="1.0.0",
            target_version="1.0.0",
            mapped_feature_ids=("protein.abundance",),
            lossy=False,
        )
    with pytest.raises(ValidationError, match="unknown feature"):
        FormalProteinStateSchema(
            schema_id="schema.invalid",
            version="1.0.0",
            features=_schema(include_category=False).features,
            invariants=(
                FormalStateInvariant(
                    invariant_id="invariant.unknown",
                    expression="unknown >= 0",
                    severity=FormalStateInvariantSeverity.ERROR,
                    feature_ids=("unknown",),
                ),
            ),
        )


def test_schema_registry_is_eight_strict_provisional_contracts() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"] is True for schema in schemas.values()
    )
