"""Negative and boundary paths used to close M10-01 branch coverage."""

# This matrix intentionally uses compact parametrized literals and HTTP codes.
# ruff: noqa: E501, PLR2004

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

import glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.engine as engine_module
from glio_proteogen.contracts.m10_01 import (
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValue,
    ProteinRnaFeatureValueKind,
    ProteinRnaInvariant,
    ProteinRnaInvariantSeverity,
    ProteinRnaInvariantStatus,
    ProteinRnaMigrationRule,
    ProteinRnaMissingness,
    ProteinRnaReplayReason,
    ProteinRnaValidationStatus,
    ValidateProteinRnaDiscordanceStateVerification,
)
from glio_proteogen.contracts.m10_01.canonical import canonical_request_digest
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    M1001InputError,
    M1001Plugin,
    M1001Service,
    validate_protein_rna_discordance_state,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.api import (
    create_app,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.cli import (
    app as cli_app,
)
from tests.modules.c10_pathway_proteotype.test_m10_01_formal_state import (
    _artifact,
    _context,
    _request,
)


def _feature(**updates: object) -> ProteinRnaFeatureDefinition:
    payload: dict[str, object] = {
        "feature_id": "feature.value",
        "version": "1.0.0",
        "value_kind": ProteinRnaFeatureValueKind.SCALAR,
        "unit": "ratio",
        "allowed_missingness": (ProteinRnaMissingness.OBSERVED,),
    }
    payload.update(updates)
    return ProteinRnaFeatureDefinition(**payload)


def _request_for_feature(
    feature: ProteinRnaFeatureDefinition,
    value: ProteinRnaFeatureValue,
    invariant: ProteinRnaInvariant | None = None,
) -> object:
    schema = FormalProteinRnaDiscordanceStateSchema(
        schema_id="schema.edge",
        version="1.0.0",
        features=(feature,),
        invariants=() if invariant is None else (invariant,),
    )
    base = _request()
    return type(base).model_validate(
        {
            **base.model_dump(mode="python"),
            "state_schema": schema,
            "values": (value,),
            "source_artifacts": (_artifact("source.edge"),),
        }
    )


def _rebuild(request: object, **updates: object) -> object:
    return type(request).model_validate(
        {**request.model_dump(mode="python"), **updates}
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"allowed_missingness": (ProteinRnaMissingness.OBSERVED,) * 2}, "missingness"),
        ({"allowed_categories": ("a", "a")}, "categories"),
        ({"domain_lower": 1.0, "domain_upper": 0.0}, "lower bound"),
        ({"value_kind": ProteinRnaFeatureValueKind.CATEGORICAL}, "categorical feature"),
        (
            {
                "value_kind": ProteinRnaFeatureValueKind.CATEGORICAL,
                "allowed_categories": ("a",),
                "domain_lower": 0.0,
            },
            "categorical feature",
        ),
        ({"allowed_categories": ("a",)}, "non-categorical"),
        (
            {"value_kind": ProteinRnaFeatureValueKind.VECTOR, "domain_lower": 0.0},
            "vector feature",
        ),
    ],
)
def test_feature_definition_closure(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _feature(**payload)


def test_feature_value_shapes_and_invariants_reject_illegal_states() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        ProteinRnaFeatureValue(
            feature_id="feature.value",
            state=ProteinRnaMissingness.OBSERVED,
            unit="ratio",
            scalar_value=0.5,
            category="a",
        )
    with pytest.raises(ValidationError, match="ordered bounds"):
        ProteinRnaFeatureValue(
            feature_id="feature.value",
            state=ProteinRnaMissingness.OBSERVED,
            unit="ratio",
            interval_lower=0.8,
            interval_upper=0.2,
        )
    with pytest.raises(ValidationError, match="non-observed"):
        ProteinRnaFeatureValue(
            feature_id="feature.value",
            state=ProteinRnaMissingness.MISSING,
            unit="ratio",
            scalar_value=0.5,
        )
    with pytest.raises(ValidationError, match="feature ids"):
        ProteinRnaInvariant(
            invariant_id="invariant.duplicate",
            expression="feature.value >= 0",
            severity=ProteinRnaInvariantSeverity.ERROR,
            feature_ids=("feature.value", "feature.value"),
        )
    with pytest.raises(ValidationError, match="expression"):
        ProteinRnaInvariant(
            invariant_id="invariant.long",
            expression="feature.value >= " + ("1" * 600),
            severity=ProteinRnaInvariantSeverity.ERROR,
            feature_ids=("feature.value",),
        )


def test_migration_and_schema_references_are_closed() -> None:
    with pytest.raises(ValidationError, match="versions"):
        ProteinRnaMigrationRule(
            source_version="1.0.0",
            target_version="1.0.0",
            mapped_feature_ids=("feature.value",),
            lossy=False,
        )
    feature = _feature()
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.same",
        expression="feature.value >= 0",
        severity=ProteinRnaInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    with pytest.raises(ValidationError, match="feature ids"):
        FormalProteinRnaDiscordanceStateSchema(
            schema_id="schema.duplicate",
            version="1.0.0",
            features=(feature, feature),
        )
    with pytest.raises(ValidationError, match="invariant ids"):
        FormalProteinRnaDiscordanceStateSchema(
            schema_id="schema.duplicate-invariant",
            version="1.0.0",
            features=(feature,),
            invariants=(invariant, invariant),
        )
    migration = ProteinRnaMigrationRule(
        source_version="1.0.0",
        target_version="2.0.0",
        mapped_feature_ids=("unknown",),
        lossy=False,
    )
    with pytest.raises(ValidationError, match="migration"):
        FormalProteinRnaDiscordanceStateSchema(
            schema_id="schema.unknown-migration",
            version="1.0.0",
            features=(feature,),
            migrations=(migration,),
        )


def test_request_domain_and_shape_closure() -> None:
    request = _request()
    feature = request.state_schema.features[0]
    with pytest.raises(ValidationError, match="unique"):
        _rebuild(request, values=request.values + request.values)
    with pytest.raises(ValidationError, match="at least 1"):
        _rebuild(request, values=())
    wrong_state = ProteinRnaFeatureValue(
        feature_id=feature.feature_id,
        state=ProteinRnaMissingness.UNSUPPORTED,
        unit=feature.unit,
    )
    with pytest.raises(ValidationError, match="disallowed"):
        _rebuild(request, values=(wrong_state,))
    wrong_unit = ProteinRnaFeatureValue(
        feature_id=feature.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit="wrong",
        scalar_value=0.5,
    )
    with pytest.raises(ValidationError, match="unit"):
        _rebuild(request, values=(wrong_unit,))
    out_of_range = ProteinRnaFeatureValue(
        feature_id=feature.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=feature.unit,
        scalar_value=2.0,
    )
    with pytest.raises(ValidationError, match="outside"):
        _rebuild(request, values=(out_of_range,))


def test_kind_and_category_and_interval_domains_are_checked() -> None:
    categorical = _feature(
        feature_id="feature.category",
        value_kind=ProteinRnaFeatureValueKind.CATEGORICAL,
        allowed_categories=("a", "b"),
    )
    bad_category = ProteinRnaFeatureValue(
        feature_id="feature.category",
        state=ProteinRnaMissingness.OBSERVED,
        unit="ratio",
        category="c",
    )
    with pytest.raises(ValidationError, match="category"):
        _request_for_feature(categorical, bad_category)
    scalar = _feature()
    wrong_shape = ProteinRnaFeatureValue(
        feature_id=scalar.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=scalar.unit,
        interval_lower=0.1,
        interval_upper=0.2,
    )
    with pytest.raises(ValidationError, match="representation"):
        _request_for_feature(scalar, wrong_shape)
    interval = _feature(
        feature_id="feature.interval",
        value_kind=ProteinRnaFeatureValueKind.INTERVAL,
        domain_lower=0.0,
        domain_upper=1.0,
    )
    bad_interval = ProteinRnaFeatureValue(
        feature_id=interval.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=interval.unit,
        interval_lower=-0.1,
        interval_upper=0.2,
    )
    with pytest.raises(ValidationError, match="interval"):
        _request_for_feature(interval, bad_interval)


@pytest.mark.parametrize(
    "expression",
    [
        "feature.value == 0.5",
        "feature.value <= 0.75",
        "feature.value > 0.5",
        "feature.value < 1.0",
        "feature.value between 0.5 and 1.0",
    ],
)
def test_all_declarative_comparison_operators_are_evaluated(expression: str) -> None:
    feature = _feature()
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.operator",
        expression=expression,
        severity=ProteinRnaInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    value = ProteinRnaFeatureValue(
        feature_id=feature.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=feature.unit,
        scalar_value=0.75,
    )
    built = M1001Service().execute(_request_for_feature(feature, value, invariant))
    assert built.result.invariant_results[0].status in {
        ProteinRnaInvariantStatus.SATISFIED,
        ProteinRnaInvariantStatus.VIOLATED,
    }


def test_presence_missing_and_interval_evaluation() -> None:
    for expression, state, expected in (
        (
            "present(protein.ratio)",
            ProteinRnaMissingness.OBSERVED,
            ProteinRnaInvariantStatus.SATISFIED,
        ),
        (
            "present(protein.ratio)",
            ProteinRnaMissingness.MISSING,
            ProteinRnaInvariantStatus.NOT_EVALUABLE,
        ),
        (
            "missing(protein.ratio)",
            ProteinRnaMissingness.MISSING,
            ProteinRnaInvariantStatus.SATISFIED,
        ),
        (
            "missing(protein.ratio)",
            ProteinRnaMissingness.OBSERVED,
            ProteinRnaInvariantStatus.VIOLATED,
        ),
    ):
        request = _request(expression, state)
        assert M1001Service().execute(request).result.invariant_results[0].status is expected
    interval = _feature(
        feature_id="feature.interval",
        value_kind=ProteinRnaFeatureValueKind.INTERVAL,
    )
    value = ProteinRnaFeatureValue(
        feature_id=interval.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=interval.unit,
        interval_lower=0.5,
        interval_upper=0.7,
    )
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.interval",
        expression="feature.interval between 0.4 and 0.8",
        severity=ProteinRnaInvariantSeverity.ERROR,
        feature_ids=(interval.feature_id,),
    )
    assert (
        M1001Service().execute(_request_for_feature(interval, value, invariant)).result.status
        is ProteinRnaValidationStatus.VALID
    )


def test_engine_replay_failure_modes_and_public_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = engine_module.M1001FormalStateEngine()
    built = engine.execute(_request())
    assert engine.verify(object()).reason is ProteinRnaReplayReason.INVALID_RESULT
    assert engine.verify(built.result, b"tampered").reason is ProteinRnaReplayReason.NON_CANONICAL
    assert (
        engine.verify(
            built.result, b"x" * (engine_module.M1001_MAX_CANONICAL_RESULT_BYTES + 1)
        ).reason
        is ProteinRnaReplayReason.OVERSIZED
    )
    assert engine.verify(built.result).verified
    assert M1001Service().verify(built.result, built.canonical_bytes).verified
    assert (
        validate_protein_rna_discordance_state(_request()).result.status
        is ProteinRnaValidationStatus.VALID
    )
    assert M1001Service().validate(_request()).request_id == "request.m10-01"
    assert M1001Service().integrate(_request()).result.status is ProteinRnaValidationStatus.VALID
    monkeypatch.setattr(engine_module, "M1001_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(M1001InputError, match="canonical byte"):
        engine.execute(_request())


def test_contract_tamper_and_verification_closures() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    result = M1001Service().execute(request).result
    with pytest.raises(ValidationError, match="request digest"):
        type(result).model_validate(
            {**result.model_dump(mode="python"), "request_digest": "sha256:" + ("2" * 64)}
        )
    hard = M1001Service().execute(_request("protein.ratio >= 0.9")).result
    with pytest.raises(ValidationError, match="violated hard"):
        type(hard).model_validate(
            {**hard.model_dump(mode="python"), "status": ProteinRnaValidationStatus.VALID}
        )
    with pytest.raises(ValidationError, match="valid result requires"):
        type(result).model_validate(
            {
                **result.model_dump(mode="python"),
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.LIMITED}
                ),
            }
        )
    with pytest.raises(ValidationError, match="abstained"):
        type(result).model_validate(
            {**result.model_dump(mode="python"), "status": ProteinRnaValidationStatus.ABSTAINED}
        )
    with pytest.raises(ValidationError, match="verification verdict"):
        ValidateProteinRnaDiscordanceStateVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=True,
            reason=ProteinRnaReplayReason.VERIFIED,
            result_digest=result.result_digest,
        )
    with pytest.raises(ValidationError, match="verified replay"):
        ValidateProteinRnaDiscordanceStateVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=ProteinRnaReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValidationError, match="failed replay"):
        ValidateProteinRnaDiscordanceStateVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            reason=ProteinRnaReplayReason.INVALID_RESULT,
            result_digest=result.result_digest,
        )


def test_engine_missing_bounds_and_control_failures() -> None:
    feature = _feature(
        feature_id="feature.vector",
        value_kind=ProteinRnaFeatureValueKind.VECTOR,
        allowed_missingness=(ProteinRnaMissingness.OBSERVED,),
    )
    value = ProteinRnaFeatureValue(
        feature_id=feature.feature_id,
        state=ProteinRnaMissingness.OBSERVED,
        unit=feature.unit,
        vector=(0.1, 0.2),
    )
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.vector",
        expression="feature.vector >= 0",
        severity=ProteinRnaInvariantSeverity.ERROR,
        feature_ids=(feature.feature_id,),
    )
    assert (
        M1001Service().execute(_request_for_feature(feature, value, invariant)).result.status
        is ProteinRnaValidationStatus.ABSTAINED
    )
    for update in (
        {
            "identity_lineage": _context().references.identity_lineage.model_copy(
                update={"state": "unresolved"}
            )
        },
        {"quality": _context().references.quality.model_copy(update={"state": "rejected"})},
    ):
        refs = _request().context.references.model_copy(update=update)
        denied = _request().model_copy(
            update={"context": _request().context.model_copy(update={"references": refs})}
        )
        with pytest.raises(PermissionError):
            M1001Service().execute(denied)


def test_plugin_accepts_serialized_inputs_and_descriptor() -> None:
    plugin = M1001Plugin(M1001Service())
    request = _request()
    token = plugin.validate(request.model_dump_json())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-01"
    assert plugin.run(token).result.status is ProteinRnaValidationStatus.VALID
    token = plugin.validate(bytearray(request.model_dump_json().encode()))
    assert plugin.run(token).result.status is ProteinRnaValidationStatus.VALID


def test_api_and_cli_error_paths(tmp_path: Path) -> None:
    request = _request()
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with TestClient(create_app(M1001Service())) as client:
        assert client.post("/v1/modules/M10-01/validate", json={}).status_code == 422
        assert client.post("/v1/modules/M10-01/execute", json={}).status_code == 422
        assert client.post("/v1/modules/M10-01/validate", content=b"{bad").status_code == 422
        assert (
            client.post(
                "/v1/modules/M10-01/validate", json=denied.model_dump(mode="json")
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/v1/modules/M10-01/execute", json=denied.model_dump(mode="json")
            ).status_code
            == 403
        )
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(cli_app, ["validate", str(bad_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(tmp_path / "missing.json")]).exit_code != 0
    abstained_path = tmp_path / "abstained.json"
    abstained_path.write_text(
        _request(state=ProteinRnaMissingness.MISSING).model_dump_json(), encoding="utf-8"
    )
    output_path = tmp_path / "output.json"
    assert (
        runner.invoke(
            cli_app, ["execute", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app, ["execute", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(cli_app, ["execute", str(abstained_path)]).exit_code == 1
