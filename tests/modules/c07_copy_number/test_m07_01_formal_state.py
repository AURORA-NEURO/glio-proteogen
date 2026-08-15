"""Deep contract, runtime, replay, and adapter tests for provisional M07-01."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m07_01 import (
    CopyNumberFeatureDefinition,
    CopyNumberFeatureValue,
    CopyNumberFeatureValueKind,
    CopyNumberInvariant,
    CopyNumberInvariantSeverity,
    CopyNumberMissingness,
    FormalCopyNumberStateSchema,
    ValidateCopyNumberStateRequest,
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
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema import (
    FormalStateAuthorizationError,
    FormalStateInputError,
    FormalStateSubmission,
    M0701FormalStateEngine,
    M0701Plugin,
)
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema.api import (
    create_app,
)
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema.cli import app

DIGEST = "sha256:" + "1" * 64
runner = CliRunner()


def _artifact(identifier: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="1.0.0",
        digest=DIGEST,
        media_type="application/json",
    )


def _decision(identifier: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=identifier,
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact("evidence." + identifier),
    )


def _context(*, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0701",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=DIGEST,
                evidence=_artifact("evidence.identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _request(
    *,
    value: float | None = 3.0,
    state: CopyNumberMissingness = CopyNumberMissingness.OBSERVED,
    expression: str = "copy-number.total >= 2",
    value_kind: CopyNumberFeatureValueKind = CopyNumberFeatureValueKind.SCALAR,
    feature_value: CopyNumberFeatureValue | None = None,
    consent: ConsentState = ConsentState.GRANTED,
) -> ValidateCopyNumberStateRequest:
    definition = CopyNumberFeatureDefinition(
        feature_id="copy-number.total",
        version="1.0.0",
        value_kind=value_kind,
        unit="copy-number",
        allowed_missingness=(CopyNumberMissingness.OBSERVED, CopyNumberMissingness.MISSING),
        domain_lower=0.0,
        domain_upper=10.0,
    )
    invariant = CopyNumberInvariant(
        invariant_id="invariant.total",
        expression=expression,
        severity=CopyNumberInvariantSeverity.ERROR,
        feature_ids=(definition.feature_id,),
    )
    schema = FormalCopyNumberStateSchema(
        schema_id="schema.copy-number",
        version="1.0.0",
        features=(definition,),
        invariants=(invariant,),
    )
    selected_value = feature_value or CopyNumberFeatureValue(
        feature_id=definition.feature_id,
        state=state,
        unit=definition.unit,
        scalar_value=value,
    )
    return ValidateCopyNumberStateRequest(
        request_id="request.m0701",
        context=_context(consent=consent),
        state_schema=schema,
        values=(selected_value,),
        source_artifacts=(_artifact("source.measurements"),),
    )


def test_valid_state_is_deterministic_and_replay_closed() -> None:
    engine = M0701FormalStateEngine()
    first = engine.execute(_request())
    second = engine.execute(_request())
    assert first.result.status.value == "valid"
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).result_digest == first.result.result_digest


def test_hard_invariant_violation_is_invalid_not_negative_abstention() -> None:
    built = M0701FormalStateEngine().execute(_request(value=1.0))
    assert built.result.status.value == "invalid"
    assert built.result.support_decision.status.value == "limited"
    assert built.result.invariant_results[0].status.value == "violated"


def test_missingness_abstains_and_never_imputes() -> None:
    built = M0701FormalStateEngine().execute(_request(value=None, state=CopyNumberMissingness.MISSING, expression="all_present"))
    assert built.result.status.value == "abstained"
    assert built.result.invariant_results[0].status.value == "not_evaluable"
    assert "imput" in built.result.support_decision.rationale


@pytest.mark.parametrize("expression", ["copy-number.total between 2 and 4", "copy-number.total == 3"])
def test_safe_expression_vocabulary(expression: str) -> None:
    built = M0701FormalStateEngine().execute(_request(expression=expression))
    assert built.result.status.value == "valid"


def test_unknown_expression_abstains() -> None:
    built = M0701FormalStateEngine().execute(_request(expression="copy-number.total / 2 == 1.5"))
    assert built.result.status.value == "abstained"


def test_interval_value_uses_bounded_midpoint() -> None:
    interval = CopyNumberFeatureValue(
        feature_id="copy-number.total",
        state=CopyNumberMissingness.OBSERVED,
        unit="copy-number",
        interval_lower=2.0,
        interval_upper=4.0,
    )
    built = M0701FormalStateEngine().execute(
        _request(value_kind=CopyNumberFeatureValueKind.INTERVAL, feature_value=interval)
    )
    assert built.result.status.value == "valid"


def test_authorization_fails_before_execution() -> None:
    with pytest.raises(FormalStateAuthorizationError):
        M0701FormalStateEngine().execute(_request(consent=ConsentState.WITHHELD))


def test_contract_rejects_kind_and_domain_mismatch() -> None:
    with pytest.raises(ValueError, match="representation"):
        M0701FormalStateEngine().execute(
            _request(value_kind=CopyNumberFeatureValueKind.VECTOR)
        )
    with pytest.raises(ValueError, match="outside"):
        M0701FormalStateEngine().execute(_request(value=11.0))


def test_replay_rejects_tampered_result_and_bytes() -> None:
    engine = M0701FormalStateEngine()
    built = engine.execute(_request())
    tampered = built.result.model_copy(update={"status": "invalid"})
    with pytest.raises(FormalStateInputError):
        engine.verify(tampered)
    with pytest.raises(FormalStateInputError):
        engine.verify(built.result, built.canonical_bytes + b" ")


def test_plugin_requires_submission_and_validated_token() -> None:
    plugin = M0701Plugin()
    with pytest.raises(TypeError):
        plugin.validate(_request())
    validated = plugin.validate(FormalStateSubmission(_request()))
    assert plugin.run(validated).result.status.value == "valid"
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_parses_canonical_json_once() -> None:
    plugin = M0701Plugin()
    payload = _request().model_dump_json()
    validated = plugin.validate(FormalStateSubmission(payload))
    assert plugin.run(validated).result.status.value == "valid"


def test_api_schema_validate_execute_and_verify() -> None:
    client = TestClient(create_app())
    request = _request().model_dump(mode="json")
    schema_response = client.get("/v1/modules/M07-01/schemas/request")
    assert schema_response.status_code == 200
    assert schema_response.json()["x-glio-contract"]["provisionalAbi"] is True
    validated = client.post("/v1/modules/M07-01/validate", json=request)
    assert validated.status_code == 200
    executed = client.post("/v1/modules/M07-01/execute", json=request)
    assert executed.status_code == 200
    envelope = executed.json()
    verified = client.post("/v1/modules/M07-01/verify", json=envelope)
    assert verified.status_code == 200
    assert verified.json()["verified"] is True


def test_api_sanitizes_invalid_and_denies_unauthorized() -> None:
    client = TestClient(create_app())
    invalid = client.post("/v1/modules/M07-01/validate", json={"extra": "secret"})
    assert invalid.status_code == 422
    assert "secret" not in invalid.text
    denied = client.post(
        "/v1/modules/M07-01/execute",
        json=_request(consent=ConsentState.WITHHELD).model_dump(mode="json"),
    )
    assert denied.status_code == 403
    assert client.get("/v1/modules/M07-01/schemas/nope").status_code == 404


def test_cli_schema_and_validate(tmp_path: Path) -> None:
    source = tmp_path / "request.json"
    source.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    schema_result = runner.invoke(app, ["export-schema", "request"])
    assert schema_result.exit_code == 0
    assert "provisionalAbi" in schema_result.stdout
    validate_result = runner.invoke(app, ["validate", str(source)])
    assert validate_result.exit_code == 0
    assert "request.m0701" in validate_result.stdout


def test_cli_no_overwrite_and_abstention_exit(tmp_path: Path) -> None:
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    first = runner.invoke(app, ["execute", str(source), "--output", str(output)])
    assert first.exit_code == 0
    second = runner.invoke(app, ["execute", str(source), "--output", str(output)])
    assert second.exit_code != 0
    abstained = _request(value=None, state=CopyNumberMissingness.MISSING, expression="all_present")
    source.write_text(json.dumps(abstained.model_dump(mode="json")), encoding="utf-8")
    assert runner.invoke(app, ["execute", str(source)]).exit_code == 1


def test_schema_inventory_stays_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 8
    assert all(item["x-glio-contract"]["provisionalAbi"] for item in schemas.values())
