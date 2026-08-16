"""Deep contract, runtime, replay, and adapter tests for provisional M07-01."""

# The test fixture intentionally exposes a broad matrix and literal HTTP status
# assertions so that safety behavior remains readable at the call site.
# ruff: noqa: E501, INP001, PLR0913, PLR2004, TC003

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m07_01 import (
    CopyNumberFeatureDefinition,
    CopyNumberFeatureValue,
    CopyNumberFeatureValueKind,
    CopyNumberInvariant,
    CopyNumberInvariantSeverity,
    CopyNumberInvariantStatus,
    CopyNumberMigrationRule,
    CopyNumberMissingness,
    CopyNumberValidationStatus,
    FormalCopyNumberStateSchema,
    ValidateCopyNumberStateRequest,
    ValidateCopyNumberStateResult,
    contract_json_schemas,
    result_payload_digest,
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
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema import (
    FormalStateAuthorizationError,
    FormalStateInputError,
    FormalStateSubmission,
    M0701FormalStateEngine,
    M0701Plugin,
    M0701Service,
)
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema import (
    engine as engine_module,
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


def _categorical_request(*, expression: str = "all_present") -> ValidateCopyNumberStateRequest:
    definition = CopyNumberFeatureDefinition(
        feature_id="copy-number.state",
        version="1.0.0",
        value_kind=CopyNumberFeatureValueKind.CATEGORICAL,
        unit="state",
        allowed_missingness=(CopyNumberMissingness.OBSERVED, CopyNumberMissingness.MISSING),
        allowed_categories=("neutral", "amplified"),
    )
    invariant = CopyNumberInvariant(
        invariant_id="invariant.state",
        expression=expression,
        severity=CopyNumberInvariantSeverity.ERROR,
        feature_ids=(definition.feature_id,),
    )
    return ValidateCopyNumberStateRequest(
        request_id="request.m0701",
        context=_context(),
        state_schema=FormalCopyNumberStateSchema(
            schema_id="schema.copy-number",
            version="1.0.0",
            features=(definition,),
            invariants=(invariant,),
        ),
        values=(
            CopyNumberFeatureValue(
                feature_id=definition.feature_id,
                state=CopyNumberMissingness.OBSERVED,
                unit=definition.unit,
                category="neutral",
            ),
        ),
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
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])[
            "provisionalAbi"
        ]
        for item in schemas.values()
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_missingness": (CopyNumberMissingness.OBSERVED,) * 2},
        {"domain_lower": 4.0, "domain_upper": 2.0},
        {"value_kind": CopyNumberFeatureValueKind.CATEGORICAL},
        {"value_kind": CopyNumberFeatureValueKind.CATEGORICAL, "domain_lower": 0.0},
        {"allowed_categories": ("a", "a")},
        {"allowed_categories": ("a",)},
    ],
)
def test_feature_definition_rejects_closed_domain_errors(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "feature_id": "feature",
        "version": "1.0.0",
        "value_kind": CopyNumberFeatureValueKind.SCALAR,
        "unit": "copy-number",
        "allowed_missingness": (CopyNumberMissingness.OBSERVED,),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=r"unique|feature|domain|categorical|category"):
        CopyNumberFeatureDefinition(**base)  # type: ignore[arg-type]


def test_feature_value_rejects_multiple_and_malformed_representations() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        CopyNumberFeatureValue(
            feature_id="feature",
            state=CopyNumberMissingness.OBSERVED,
            unit="copy-number",
        )
    with pytest.raises(ValueError, match="exactly one"):
        CopyNumberFeatureValue(
            feature_id="feature",
            state=CopyNumberMissingness.OBSERVED,
            unit="copy-number",
            scalar_value=1.0,
            category="x",
        )
    with pytest.raises(ValueError, match="ordered"):
        CopyNumberFeatureValue(
            feature_id="feature",
            state=CopyNumberMissingness.OBSERVED,
            unit="copy-number",
            interval_lower=3.0,
            interval_upper=1.0,
        )
    with pytest.raises(ValueError, match="ordered"):
        CopyNumberFeatureValue(
            feature_id="feature",
            state=CopyNumberMissingness.OBSERVED,
            unit="copy-number",
            interval_lower=1.0,
        )
    with pytest.raises(ValueError, match="non-observed"):
        CopyNumberFeatureValue(
            feature_id="feature",
            state=CopyNumberMissingness.MISSING,
            unit="copy-number",
            vector=(1.0,),
        )


def test_invariant_migration_and_schema_closures() -> None:
    with pytest.raises(ValueError, match="unique"):
        CopyNumberInvariant(
            invariant_id="invariant",
            expression="all_present",
            severity=CopyNumberInvariantSeverity.ERROR,
            feature_ids=("feature", "feature"),
        )
    with pytest.raises(ValueError, match="differ"):
        CopyNumberMigrationRule(
            source_version="1.0.0",
            target_version="1.0.0",
            mapped_feature_ids=("feature",),
            lossy=False,
        )
    definition = CopyNumberFeatureDefinition(
        feature_id="feature",
        version="1.0.0",
        value_kind=CopyNumberFeatureValueKind.SCALAR,
        unit="copy-number",
        allowed_missingness=(CopyNumberMissingness.OBSERVED,),
    )
    invariant = CopyNumberInvariant(
        invariant_id="invariant",
        expression="all_present",
        severity=CopyNumberInvariantSeverity.ERROR,
        feature_ids=("other",),
    )
    with pytest.raises(ValueError, match="unknown"):
        FormalCopyNumberStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(definition,),
            invariants=(invariant,),
        )


def test_request_domain_and_value_closure_errors() -> None:
    valid = _request()
    duplicate = valid.model_copy(update={"values": (valid.values[0], valid.values[0])})
    with pytest.raises(ValueError, match="unique"):
        ValidateCopyNumberStateRequest.model_validate(duplicate, strict=True)
    wrong_unit = valid.model_copy(
        update={
            "values": (
                valid.values[0].model_copy(update={"unit": "wrong"}),
            )
        }
    )
    with pytest.raises(ValueError, match="unit"):
        ValidateCopyNumberStateRequest.model_validate(wrong_unit, strict=True)
    disallowed_value = CopyNumberFeatureValue(
        feature_id=valid.values[0].feature_id,
        state=CopyNumberMissingness.UNKNOWN,
        unit=valid.values[0].unit,
    )
    disallowed = valid.model_copy(update={"values": (disallowed_value,)})
    with pytest.raises(ValueError, match="disallowed"):
        ValidateCopyNumberStateRequest.model_validate(disallowed, strict=True)
    with pytest.raises(ValueError, match="at least"):
        ValidateCopyNumberStateRequest.model_validate(
            valid.model_copy(update={"values": ()}), strict=True
        )


def test_categorical_and_non_numeric_invariant_abstain() -> None:
    built = M0701FormalStateEngine().execute(_categorical_request(expression="copy-number.state >= 2"))
    assert built.result.status.value == "abstained"
    assert built.result.invariant_results[0].status is CopyNumberInvariantStatus.NOT_EVALUABLE


@pytest.mark.parametrize("expression", [
    "copy-number.total > 2",
    "copy-number.total <= 3",
    "copy-number.total < 4",
])
def test_comparison_operator_branches(expression: str) -> None:
    assert M0701FormalStateEngine().execute(_request(expression=expression)).result.status.value == "valid"


def test_expression_feature_must_be_declared() -> None:
    built = M0701FormalStateEngine().execute(_request(expression="other >= 2"))
    assert built.result.invariant_results[0].status.value == "not_evaluable"


def test_non_request_preflight_and_control_gate_variants() -> None:
    with pytest.raises(ValueError, match="Field required"):
        M0701FormalStateEngine.validate_request({})
    identity = _context().references.identity_lineage.model_copy(
        update={"state": IdentityLineageState.CONFLICTED}
    )
    context = _context().model_copy(
        update={"references": _context().references.model_copy(update={"identity_lineage": identity})}
    )
    with pytest.raises(FormalStateAuthorizationError):
        M0701FormalStateEngine().execute(_request().model_copy(update={"context": context}))
    rejected = _context().references.support.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    context = _context().model_copy(
        update={"references": _context().references.model_copy(update={"support": rejected})}
    )
    with pytest.raises(FormalStateAuthorizationError):
        M0701FormalStateEngine().execute(_request().model_copy(update={"context": context}))


def test_result_contract_closes_digest_and_status_paths() -> None:
    built = M0701FormalStateEngine().execute(_request())
    with pytest.raises(ValueError, match="request digest"):
        ValidateCopyNumberStateResult.model_validate(
            built.result.model_copy(update={"request_digest": DIGEST}), strict=True
        )
    violated_result = built.result.model_copy(
        update={
            "status": CopyNumberValidationStatus.VALID,
            "invariant_results": (
                built.result.invariant_results[0].model_copy(
                    update={"status": CopyNumberInvariantStatus.VIOLATED}
                ),
            ),
        }
    )
    violated_result = violated_result.model_copy(update={"result_digest": result_payload_digest(violated_result)})
    with pytest.raises(ValueError, match="valid result"):
        ValidateCopyNumberStateResult.model_validate(violated_result, strict=True)


def test_runtime_request_and_result_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "M0701_MAX_CANONICAL_REQUEST_BYTES", 1)
    with pytest.raises(FormalStateInputError, match="request"):
        M0701FormalStateEngine().execute(_request())
    monkeypatch.setattr(engine_module, "M0701_MAX_CANONICAL_REQUEST_BYTES", 4 * 1024 * 1024)
    monkeypatch.setattr(engine_module, "M0701_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(FormalStateInputError, match="result"):
        M0701FormalStateEngine().execute(_request())


def test_contract_remaining_negative_paths() -> None:
    categorical_base = {
        "feature_id": "category",
        "version": "1.0.0",
        "value_kind": CopyNumberFeatureValueKind.CATEGORICAL,
        "unit": "state",
        "allowed_missingness": (CopyNumberMissingness.OBSERVED,),
        "allowed_categories": ("neutral",),
    }
    with pytest.raises(ValueError, match="numeric bounds"):
        CopyNumberFeatureDefinition(**categorical_base, domain_lower=0.0)  # type: ignore[arg-type]
    migration = CopyNumberMigrationRule(
        source_version="1.0.0",
        target_version="2.0.0",
        mapped_feature_ids=("feature",),
        lossy=True,
    )
    assert migration.review_required is True
    definition = CopyNumberFeatureDefinition(
        feature_id="feature",
        version="1.0.0",
        value_kind=CopyNumberFeatureValueKind.VECTOR,
        unit="vector",
        allowed_missingness=(CopyNumberMissingness.OBSERVED,),
    )
    with pytest.raises(ValueError, match="unique"):
        FormalCopyNumberStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(definition, definition),
        )
    vector_value = CopyNumberFeatureValue(
        feature_id="feature",
        state=CopyNumberMissingness.OBSERVED,
        unit="vector",
        vector=(1.0, 2.0),
    )
    request = _request().model_copy(
        update={
            "state_schema": FormalCopyNumberStateSchema(
                schema_id="schema.vector",
                version="1.0.0",
                features=(definition,),
            ),
            "values": (vector_value,),
        }
    )
    assert ValidateCopyNumberStateRequest.model_validate(request, strict=True).values[0].vector == (
        1.0,
        2.0,
    )
    with pytest.raises(ValueError, match="at least"):
        ValidateCopyNumberStateRequest.model_validate(
            _request().model_copy(update={"values": ()}), strict=True
        )


def test_contract_result_status_and_digest_closure_paths() -> None:
    built = M0701FormalStateEngine().execute(_request())
    valid_wrong_support = built.result.model_copy(
        update={
            "support_decision": built.result.support_decision.model_copy(
                update={"status": SupportStatus.LIMITED}
            )
        }
    )
    with pytest.raises(ValueError, match="supported"):
        ValidateCopyNumberStateResult.model_validate(valid_wrong_support, strict=True)
    abstained = M0701FormalStateEngine().execute(
        _request(value=None, state=CopyNumberMissingness.MISSING, expression="all_present")
    )
    abstained_wrong_support = abstained.result.model_copy(
        update={
            "support_decision": abstained.result.support_decision.model_copy(
                update={"status": SupportStatus.LIMITED}
            )
        }
    )
    with pytest.raises(ValueError, match="abstained"):
        ValidateCopyNumberStateResult.model_validate(abstained_wrong_support, strict=True)
    invalid_wrong = built.result.model_copy(
        update={"status": CopyNumberValidationStatus.INVALID, "invariant_results": ()}
    )
    with pytest.raises(ValueError, match="invariant"):
        ValidateCopyNumberStateResult.model_validate(invalid_wrong, strict=True)
    missing_result = built.result.model_copy(update={"invariant_results": ()})
    with pytest.raises(ValueError, match="every"):
        ValidateCopyNumberStateResult.model_validate(missing_result, strict=True)
    bad_digest = built.result.model_copy(update={"result_digest": DIGEST})
    with pytest.raises(ValueError, match="digest"):
        ValidateCopyNumberStateResult.model_validate(bad_digest, strict=True)


def test_api_strict_errors_and_cli_bad_inputs(tmp_path: Path) -> None:
    client = TestClient(create_app())
    assert client.post("/v1/modules/M07-01/validate", content=b"{").status_code == 422
    assert client.post(
        "/v1/modules/M07-01/validate", content=b'{"x":1,"x":2}'
    ).status_code == 422
    assert client.post("/v1/modules/M07-01/verify", json={}).status_code == 422
    assert client.post(
        "/v1/modules/M07-01/verify", json={"result": {}, "canonical": 1}
    ).status_code == 422
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert runner.invoke(app, ["validate", str(bad)]).exit_code != 0
    assert runner.invoke(app, ["export-schema", "nope"]).exit_code != 0
    assert runner.invoke(app, ["execute", str(bad)]).exit_code != 0


def test_service_validate_verify_and_plugin_descriptor() -> None:
    service = M0701Service()
    built = service.validate(_request())
    assert service.verify(built.result, built.canonical_bytes).result_id == built.result.result_id
    plugin = M0701Plugin(service)
    assert plugin.descriptor["status"] == "provisional"
    assert plugin.validate_request(_request()).request_id == "request.m0701"
