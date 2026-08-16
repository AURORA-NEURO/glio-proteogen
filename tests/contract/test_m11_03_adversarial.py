"""Adversarial contract and adapter matrix for M11-03 safety gates."""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1103 import app, m1103_app
from glio_proteogen.contracts.m11_03 import (
    MechanisticFeature,
    MechanisticFeatureKind,
    MechanisticFeatureObject,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    VariantPeptideMechanisticFeatureResult,
    normalized_request,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_03_mechanistic_feature_constructor as m1103,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor.engine import (  # noqa: E501
    _validate_request,
)
from tests.contract.test_m11_03_runtime import _artifact, _request


def _feature(  # noqa: PLR0913
    request,
    *,
    value_kind,
    scalar=None,
    lower=None,
    upper=None,
    category=None,
    feature_id="pathway.activity",
):
    return MechanisticFeature(
        feature_id=feature_id,
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=value_kind,
        unit="activity",
        scalar_value=scalar,
        lower_bound=lower,
        upper_bound=upper,
        category=category,
        lineage=request.declared_features[0].lineage.model_copy(update={"feature_id": feature_id}),
    )


def test_value_shapes_relations_and_object_topology_are_closed() -> None:
    request = _request()
    assert _feature(request, value_kind=MechanisticValueKind.INTERVAL, lower=0.1, upper=0.9)
    assert _feature(request, value_kind=MechanisticValueKind.CATEGORICAL, category="active")
    with pytest.raises(ValueError, match="interval feature"):
        _feature(request, value_kind=MechanisticValueKind.INTERVAL, lower=0.9, upper=0.1)
    with pytest.raises(ValueError, match="categorical feature"):
        _feature(request, value_kind=MechanisticValueKind.CATEGORICAL, scalar=0.5)
    wrong_lineage = request.declared_features[0].lineage.model_copy(
        update={"feature_id": "different"}
    )
    with pytest.raises(ValueError, match="lineage id"):
        MechanisticFeature(
            feature_id="pathway.activity",
            version="1.0.0",
            kind=MechanisticFeatureKind.PATHWAY,
            value_kind=MechanisticValueKind.SCALAR,
            unit="activity",
            scalar_value=0.5,
            lineage=wrong_lineage,
        )
    with pytest.raises(ValueError, match="self-loop"):
        MechanisticRelation(
            relation_id="relation.self",
            source_feature_id="pathway.activity",
            target_feature_id="pathway.activity",
            kind=MechanisticRelationKind.REGULATES,
        )
    with pytest.raises(ValueError, match="weight"):
        MechanisticRelation(
            relation_id="relation.weight",
            source_feature_id="pathway.activity",
            target_feature_id="other",
            kind=MechanisticRelationKind.REGULATES,
            weight=2.0,
        )
    config = request.configuration
    with pytest.raises(ValueError, match="unique"):
        MechanisticFeatureObject(
            object_id="object.duplicate",
            version="1.0.0",
            features=(request.declared_features[0], request.declared_features[0]),
            configuration=config,
        )
    relation = MechanisticRelation(
        relation_id="relation.unknown",
        source_feature_id="pathway.activity",
        target_feature_id="other",
        kind=MechanisticRelationKind.REGULATES,
    )
    with pytest.raises(ValueError, match="unknown feature"):
        MechanisticFeatureObject(
            object_id="object.unknown",
            version="1.0.0",
            features=request.declared_features,
            relations=(relation,),
            configuration=config,
        )
    duplicate_relation = relation.model_copy(update={"relation_id": "relation.duplicate"})
    with pytest.raises(ValueError, match="relation ids"):
        MechanisticFeatureObject(
            object_id="object.relations",
            version="1.0.0",
            features=request.declared_features,
            relations=(duplicate_relation, duplicate_relation),
            configuration=config,
        )
    with pytest.raises(ValueError, match="transformation ids"):
        MechanisticFeatureObject(
            object_id="object.transform",
            version="1.0.0",
            features=request.declared_features,
            configuration=config.model_copy(
                update={"transformation_ids": ("transform.scale", "transform.scale")}
            ),
        )
    with pytest.raises(ValueError, match="negative-control"):
        MechanisticFeatureObject(
            object_id="object.negative",
            version="1.0.0",
            features=request.declared_features,
            configuration=config.model_copy(
                update={
                    "negative_control_artifacts": (
                        config.negative_control_artifacts[0],
                        config.negative_control_artifacts[0],
                    )
                }
            ),
        )
    unknown_lineage = request.declared_features[0].lineage.model_copy(
        update={"transformation_ids": ("transform.unknown",)}
    )
    with pytest.raises(ValueError, match="unknown transformation"):
        MechanisticFeatureObject(
            object_id="object.unknown-transform",
            version="1.0.0",
            features=(
                request.declared_features[0].model_copy(update={"lineage": unknown_lineage}),
            ),
            configuration=config,
        )


def test_contract_request_and_result_replay_closure_rejects_tampering() -> None:
    request = _request()
    with pytest.raises(ValueError, match="request identifier"):
        request.model_validate(
            {**request.model_dump(mode="python"), "request_id": "other"}, strict=False
        )
    with pytest.raises(ValueError, match="upstream"):
        request.model_validate(
            {
                **request.model_dump(mode="python"),
                "upstream_result": _artifact("wrong").model_dump(mode="python"),
            },
            strict=False,
        )
    duplicate_source = request.model_dump(mode="python")
    duplicate_source["source_artifacts"] = [
        request.source_artifacts[0].model_dump(mode="python"),
        request.source_artifacts[0].model_dump(mode="python"),
    ]
    with pytest.raises(ValueError, match="source artifact"):
        type(request).model_validate(duplicate_source, strict=False)
    duplicate_feature = request.model_dump(mode="python")
    duplicate_feature["declared_features"] = [
        request.declared_features[0].model_dump(mode="python"),
        request.declared_features[0].model_dump(mode="python"),
    ]
    with pytest.raises(ValueError, match="declared feature"):
        type(request).model_validate(duplicate_feature, strict=False)
    config_values = request.configuration.model_dump()
    config_values["locked"] = False
    config_unlocked = request.configuration.model_construct(**config_values)
    with pytest.raises(ValueError, match="locked"):
        type(request).model_validate(
            {**request.model_dump(mode="python"), "configuration": config_unlocked},
            strict=False,
        )
    result = m1103.construct_variant_peptide_mechanistic_features(request)
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="request digest"):
        VariantPeptideMechanisticFeatureResult.model_validate(payload, strict=False)
    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="result digest"):
        VariantPeptideMechanisticFeatureResult.model_validate(payload, strict=False)
    invalid_constructed = result.model_dump(mode="python")
    invalid_constructed["feature_object"] = None
    with pytest.raises(ValueError, match="constructed result"):
        VariantPeptideMechanisticFeatureResult.model_validate(invalid_constructed, strict=False)
    invalid_abstained = result.model_dump(mode="python")
    invalid_abstained["status"] = "abstained"
    invalid_abstained["abstention_reason"] = "review"
    with pytest.raises(ValueError, match="abstained result"):
        VariantPeptideMechanisticFeatureResult.model_validate(invalid_abstained, strict=False)


def test_preflight_rejects_hostile_and_malformed_inputs() -> None:
    with pytest.raises(m1103.M1103AuthorizationError):
        m1103.preflight_m1103_authorization(object())
    with pytest.raises(m1103.M1103AuthorizationError):
        m1103.preflight_m1103_authorization({})
    with pytest.raises(TypeError):
        _validate_request("not a request")
    with pytest.raises(m1103.M1103AuthorizationError):
        m1103.preflight_m1103_authorization({"context": {"references": {"consent": {"state": 1}}}})
    request = _request()
    assert _validate_request(request.model_dump(mode="json")).request_id == request.request_id
    assert normalized_request({"z": 1}) == {"z": 1}
    assert not m1103.verify_m1103_replay(object(), b"not-json")  # type: ignore[arg-type]
    with pytest.raises(StrictJsonError):
        m1103.M1103Plugin(m1103.M1103Service()).validate('{"a":1,"a":2}')
    plugin = m1103.M1103Plugin(m1103.M1103Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M11-03"
    assert plugin.validate(request).request.request_id == request.request_id
    result = m1103.construct_variant_peptide_mechanistic_features(request)
    altered = result.model_copy(update={"request": _request(source_id="source.other")})
    assert not m1103.verify_m1103_replay(altered, request)
    config = request.configuration.model_copy(
        update={"negative_control_artifacts": (_artifact("negative.fail"),)}
    )
    failed = request.model_copy(update={"configuration": config})
    failed_result = m1103.M1103Service().execute(failed)
    assert "negative_control_failed" in {item.value for item in failed_result.findings}


def test_api_error_matrix_and_alias() -> None:
    client = TestClient(app)
    request = _request()
    assert client.get("/v1/m11-03/schema/nope").status_code == HTTPStatus.NOT_FOUND
    assert (
        client.post("/v1/modules/M11-03/mechanistic-features", content="bad").status_code
        == HTTPStatus.BAD_REQUEST
    )
    assert (
        client.post("/v1/modules/M11-03/verify", json=[]).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post("/v1/modules/M11-03/verify", json={}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(
            "/v1/modules/M11-03/verify",
            json={"request": request.model_dump(mode="json"), "result": {}},
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    body = json.loads(request.model_dump_json())
    body["unknown"] = True
    invalid = client.post("/v1/modules/M11-03/mechanistic-features", json=body)
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    alias = client.post(
        "/v1/modules/GLIO-PROTEOGEN-M11-03/construct", content=request.model_dump_json()
    )
    assert alias.status_code == HTTPStatus.OK
    denied = _request(controls={"quality": UpstreamDecisionState.REJECTED})
    assert (
        client.post(
            "/v1/modules/M11-03/verify",
            json={"request": denied.model_dump(mode="json"), "result": {}},
        ).status_code
        == HTTPStatus.FORBIDDEN
    )


def test_cli_error_and_abstention_matrix(tmp_path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    denied_path = tmp_path / "denied.json"
    result_path = tmp_path / "result.json"
    request = _request()
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    denied = _request(upstream_id="result.m1102.unsupported")
    denied_path.write_text(denied.model_dump_json(), encoding="utf-8")
    assert runner.invoke(m1103_app, ["export-schema", "nope"]).exit_code != 0
    assert runner.invoke(m1103_app, ["export-schema", "request"]).exit_code == 0
    abstained = runner.invoke(
        m1103_app, ["construct", str(denied_path), "--output", str(result_path)]
    )
    assert abstained.exit_code == 1
    assert runner.invoke(m1103_app, ["construct", str(request_path)]).exit_code == 0
    denied_control = _request(controls={"quality": UpstreamDecisionState.REJECTED})
    denied_path.write_text(denied_control.model_dump_json(), encoding="utf-8")
    assert runner.invoke(m1103_app, ["construct", str(denied_path)]).exit_code == 2  # noqa: PLR2004
    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result_digest"] = "sha256:" + "f" * 64
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert runner.invoke(m1103_app, ["verify", str(request_path), str(result_path)]).exit_code != 0
    other = _request(source_id="source.other")
    other_path = tmp_path / "other.json"
    other_path.write_text(other.model_dump_json(), encoding="utf-8")
    assert runner.invoke(m1103_app, ["verify", str(other_path), str(result_path)]).exit_code != 0
