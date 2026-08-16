"""Adversarial contract and runtime tests for M09-01."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m09_01 import (
    ComplexActivityFeatureDefinition,
    ComplexActivityFeatureValue,
    ComplexActivityFeatureValueKind,
    ComplexActivityInvariant,
    ComplexActivityInvariantSeverity,
    ComplexActivityMissingness,
    FormalComplexActivityStateSchema,
    ValidateComplexActivityStateRequest,
)
from glio_proteogen.contracts.m09_01.canonical import canonical_request_digest
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
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    M0901AuthorizationError,
    M0901FormalStateEngine,
    M0901Plugin,
    M0901Service,
)

_DIGEST: Final = "sha256:" + ("a" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type="application/vnd.aurora.synthetic+json",
    )


def _upstream(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=name,
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"{name}.evidence"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="context.m0901",
        actor_id="actor.m0901",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_upstream("configuration.m0901"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity.m0901",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity.m0901.evidence"),
            ),
            provenance=_upstream("provenance.m0901"),
            consent=ConsentReference(
                decision_id="consent.m0901",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent.m0901.evidence"),
            ),
            quality=_upstream("quality.m0901"),
            support=_upstream("support.m0901"),
            intended_use=_upstream("intended-use.m0901"),
        ),
    )


def _request(
    *,
    value: float | None = 0.75,
    state: ComplexActivityMissingness = ComplexActivityMissingness.OBSERVED,
    expression: str = "feature:complex.activity.scalar >= 0.5",
) -> ValidateComplexActivityStateRequest:
    definition = ComplexActivityFeatureDefinition(
        feature_id="complex.activity.scalar",
        version="0.1.0",
        value_kind=ComplexActivityFeatureValueKind.SCALAR,
        unit="activity",
        allowed_missingness=(
            ComplexActivityMissingness.OBSERVED,
            ComplexActivityMissingness.MISSING,
            ComplexActivityMissingness.UNSUPPORTED,
        ),
        domain_lower=0.0,
        domain_upper=1.0,
    )
    invariant = ComplexActivityInvariant(
        invariant_id="invariant.activity.scalar",
        expression=expression,
        severity=ComplexActivityInvariantSeverity.ERROR,
        feature_ids=(definition.feature_id,),
    )
    schema = FormalComplexActivityStateSchema(
        schema_id="schema.complex.activity",
        version="0.1.0",
        features=(definition,),
        invariants=(invariant,),
    )
    feature = ComplexActivityFeatureValue(
        feature_id=definition.feature_id,
        state=state,
        unit=definition.unit,
        scalar_value=value,
    )
    return ValidateComplexActivityStateRequest(
        request_id="request.m0901",
        context=_context(),
        state_schema=schema,
        values=(feature,),
        source_artifacts=(_artifact("source.m0901"),),
    )


def test_valid_state_has_explicit_provenance_and_replays() -> None:
    built = M0901Service().execute(_request())

    assert built.result.status.value == "valid"
    assert built.result.support_decision.status.value == "supported"
    assert built.result.request_digest == canonical_request_digest(built.result.request)
    assert built.result.provenance.module_id == "GLIO-PROTEOGEN-M09-01"
    assert M0901FormalStateEngine.verify(built.result, built.canonical_bytes).verified


def test_violated_state_is_invalid_but_not_unsupported() -> None:
    built = M0901Service().execute(_request(value=0.25))

    assert built.result.status.value == "invalid"
    assert built.result.support_decision.status.value == "limited"
    assert built.result.invariant_results[0].status.value == "violated"


def test_missing_state_abstains_without_negative_conversion() -> None:
    built = M0901Service().execute(_request(value=None, state=ComplexActivityMissingness.MISSING))

    assert built.result.status.value == "abstained"
    assert built.result.support_decision.status.value == "unsupported"
    assert built.result.invariant_results[0].status.value == "not_evaluable"


def test_unknown_expression_abstains_for_review() -> None:
    built = M0901Service().execute(_request(expression="python:activity > 0"))

    assert built.result.status.value == "abstained"
    assert built.result.support_decision.status.value == "review_required"


def test_authorization_fails_before_execution() -> None:
    request = _request()
    rejected = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"quality": rejected}
                    )
                }
            )
        }
    )

    with pytest.raises(M0901AuthorizationError):
        M0901Service().execute(denied)


def test_plugin_requires_issued_unmodified_token() -> None:
    service = M0901Service()
    plugin = M0901Plugin(service)
    token = plugin.validate(_request())
    result = plugin.run(token)

    assert result.result.status.value == "valid"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_strict_json_rejects_duplicate_keys() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id":"one","request_id":"two"}')


def test_tampered_canonical_result_is_rejected() -> None:
    built = M0901Service().execute(_request())
    tampered = built.canonical_bytes.replace(b"valid", b"invalid", 1)

    outcome = M0901FormalStateEngine.verify(built.result, tampered)
    assert not outcome.verified


def test_schema_rejects_representation_kind_mismatch() -> None:
    request = _request().model_dump(mode="python")
    request["values"] = (
        ComplexActivityFeatureValue(
            feature_id="complex.activity.scalar",
            state=ComplexActivityMissingness.OBSERVED,
            unit="activity",
            category="high",
        ),
    )
    with pytest.raises(ValidationError, match=r"category|representation"):
        ValidateComplexActivityStateRequest.model_validate(request)


def test_schema_rejects_nonfinite_numeric_values() -> None:
    with pytest.raises(ValidationError):
        _request(value=float("inf"))
