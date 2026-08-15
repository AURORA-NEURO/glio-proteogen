"""Deep runtime, replay, adapter, and safety gates for provisional M12-03."""

from __future__ import annotations

import json
from collections import UserDict
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1203 as m1203_adapter
from glio_proteogen.adapters.m1203 import app, m1203_app
from glio_proteogen.contracts.m12_03 import (
    M1203_M1202_INPUT_MEDIA_TYPE,
    M1203_OPERATION,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
    MechanisticDiagnosticStatus,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    NegativeControlStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c12_driver_protein_consequence import (
    M1203Plugin,
    M1203Service,
    MechanisticFeatureAuthorizationError,
    construct_mechanistic_features,
)
from glio_proteogen.modules.c12_driver_protein_consequence.m12_03_mechanistic_feature_constructor.engine import (  # noqa: E501
    MechanisticFeatureValidationError,
    _abstention_reason,
    _findings,
    _plain_value,
    _state_text,
    preflight_mechanistic_feature_authorization,
    validate_json_request,
)

HTTP_OK = 200
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_NOT_FOUND = 404
INTERVAL_UPPER = 0.9


def artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"artifact": label}),
        media_type=media_type,
    )


def context() -> ExecutionContext:
    accepted = {
        "approved_configuration": UpstreamDecisionReference(
            decision_id="approved.configuration",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("approved"),
        ),
        "provenance": UpstreamDecisionReference(
            decision_id="accepted.provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("provenance"),
        ),
        "quality": UpstreamDecisionReference(
            decision_id="accepted.quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("quality"),
        ),
        "support": UpstreamDecisionReference(
            decision_id="accepted.support",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("support"),
        ),
        "intended_use": UpstreamDecisionReference(
            decision_id="accepted.intended-use",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact("intended-use"),
        ),
    }
    return ExecutionContext(
        request_id="request.m1203.runtime",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted["approved_configuration"],
            identity_lineage=IdentityLineageReference(
                decision_id="resolved.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "test"}),
                evidence=artifact("identity"),
            ),
            provenance=accepted["provenance"],
            consent=ConsentReference(
                decision_id="granted.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact("consent"),
            ),
            quality=accepted["quality"],
            support=accepted["support"],
            intended_use=accepted["intended_use"],
        ),
    )


def request(
    *, negative: NegativeControlStatus = NegativeControlStatus.PASSED
) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
    source = artifact("feature-source")
    lineage = MechanisticFeatureLineage(
        feature_id="feature.pathway",
        source_artifacts=(source,),
        claim="Pathway evidence is bound to a caller-declared artifact.",
        transformation_ids=("transform.log1p",),
    )
    feature = MechanisticFeature(
        feature_id="feature.pathway",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit="score",
        scalar_value=0.75,
        lineage=lineage,
    )
    configuration = MechanisticFeatureConfiguration(
        configuration_id="config.m1203.reference",
        version="1.0.0",
        model_family="curated-mechanistic-baseline",
        transformation_ids=("transform.log1p",),
        topology_reference=artifact("topology"),
        negative_control_artifacts=(artifact("negative-control"),),
        evidence=(),
    )
    return ConstructBiomarkerPanelMechanisticFeaturesRequest(
        operation=M1203_OPERATION,
        request_id="request.m1203.runtime",
        context=context(),
        upstream_result=artifact("upstream", M1203_M1202_INPUT_MEDIA_TYPE),
        configuration=configuration,
        feature_inputs=(feature,),
        relations=(),
        negative_control_status=negative,
        source_artifacts=(source,),
    )


def test_supported_runtime_constructs_closed_object_and_replays() -> None:
    result = construct_mechanistic_features(request())

    assert result.status.value == "constructed"
    assert result.feature_object is not None
    assert result.feature_object.features[0].feature_id == "feature.pathway"
    assert result.result_digest.startswith("sha256:")
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M12-03"

    replayed = type(result).model_validate_json(result.model_dump_json())
    assert replayed.result_digest == result.result_digest


def test_failed_negative_control_abstains_without_object() -> None:
    result = construct_mechanistic_features(request(negative=NegativeControlStatus.FAILED))

    assert result.status.value == "abstained"
    assert result.feature_object is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_controls_fail_closed_before_input_traversal() -> None:
    candidate = request().model_dump(mode="python")
    candidate["context"]["references"]["consent"]["state"] = "withheld"

    with pytest.raises(MechanisticFeatureAuthorizationError):
        construct_mechanistic_features(candidate)


def test_plugin_rejects_forged_capability_and_accepts_json() -> None:
    service = M1203Service()
    plugin = M1203Plugin(service)
    payload = request().model_dump_json().encode()
    token = plugin.validate(payload)
    assert plugin.run(token).status.value == "constructed"
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(object())  # type: ignore[arg-type]


def test_fastapi_construct_verify_and_schema_are_sanitized() -> None:
    client = TestClient(app)
    response = client.post("/v1/modules/M12-03/construct", content=request().model_dump_json())
    assert response.status_code == HTTP_OK
    result = response.json()
    assert result["status"] == "constructed"
    verified = client.post("/v1/modules/M12-03/verify", json=result)
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/m12-03/schema/request")
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    bad = client.post("/v1/modules/M12-03/construct", content=b'{"request_id": 3}')
    assert bad.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "validation" in bad.json()["error"]["message"]
    assert "traceback" not in bad.text.lower()


def test_cli_schema_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "schema.json"
    runner = CliRunner()
    first = runner.invoke(m1203_app, ["export-schema", "request", "--output", str(output)])
    assert first.exit_code == 0
    second = runner.invoke(m1203_app, ["export-schema", "request", "--output", str(output)])
    assert second.exit_code != 0


def test_contract_interval_categorical_and_relation_invariants() -> None:
    source = artifact("contract-feature")
    lineage = MechanisticFeatureLineage(
        feature_id="feature.interval",
        source_artifacts=(source,),
        claim="Interval evidence.",
    )
    interval = MechanisticFeature(
        feature_id="feature.interval",
        version="1.0.0",
        kind=MechanisticFeatureKind.STATE,
        value_kind=MechanisticValueKind.INTERVAL,
        unit="fraction",
        lower_bound=0.1,
        upper_bound=0.9,
        lineage=lineage,
    )
    categorical = MechanisticFeature(
        feature_id="feature.category",
        version="1.0.0",
        kind=MechanisticFeatureKind.LINEAGE,
        value_kind=MechanisticValueKind.CATEGORICAL,
        unit="label",
        category="mesenchymal",
        lineage=MechanisticFeatureLineage(
            feature_id="feature.category",
            source_artifacts=(source,),
            claim="Category evidence.",
        ),
    )
    assert interval.upper_bound == INTERVAL_UPPER
    assert categorical.category == "mesenchymal"
    with pytest.raises(ValueError, match="ordered bounds"):
        MechanisticFeature(
            feature_id="feature.bad-interval",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.INTERVAL,
            unit="fraction",
            lower_bound=0.9,
            upper_bound=0.1,
            lineage=MechanisticFeatureLineage(
                feature_id="feature.bad-interval",
                source_artifacts=(source,),
                claim="Bad interval.",
            ),
        )
    with pytest.raises(ValueError, match="categorical feature"):
        MechanisticFeature(
            feature_id="feature.bad-category",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="label",
            scalar_value=1.0,
            lineage=MechanisticFeatureLineage(
                feature_id="feature.bad-category",
                source_artifacts=(source,),
                claim="Bad category.",
            ),
        )
    with pytest.raises(ValueError, match="scalar feature"):
        MechanisticFeature(
            feature_id="feature.two-values",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.SCALAR,
            unit="score",
            scalar_value=1.0,
            category="also-category",
            lineage=MechanisticFeatureLineage(
                feature_id="feature.two-values",
                source_artifacts=(source,),
                claim="Two values.",
            ),
        )
    with pytest.raises(ValueError, match="lineage id"):
        MechanisticFeature(
            feature_id="feature.lineage-mismatch",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.SCALAR,
            unit="score",
            scalar_value=1.0,
            lineage=lineage,
        )
    with pytest.raises(ValueError, match="self-loop"):
        MechanisticRelation(
            relation_id="relation.self",
            source_feature_id="feature.interval",
            target_feature_id="feature.interval",
            kind=MechanisticRelationKind.REGULATES,
        )


def test_contract_object_closure_rejects_duplicates_and_unknown_lineage() -> None:
    base = request()
    feature = base.feature_inputs[0]
    relation = MechanisticRelation(
        relation_id="relation.pathway-state",
        source_feature_id=feature.feature_id,
        target_feature_id="feature.other",
        kind=MechanisticRelationKind.PARTICIPATES,
    )
    with pytest.raises(ValueError, match="unknown feature"):
        MechanisticFeatureObject(
            object_id="object.bad",
            version="1.0.0",
            features=(feature,),
            relations=(relation,),
            configuration=base.configuration,
        )
    with pytest.raises(ValueError, match="unknown transformation"):
        MechanisticFeatureObject(
            object_id="object.bad-transform",
            version="1.0.0",
            features=(
                feature.model_copy(
                    update={
                        "lineage": feature.lineage.model_copy(
                            update={"transformation_ids": ("unknown",)}
                        )
                    }
                ),
            ),
            configuration=base.configuration,
        )
    with pytest.raises(ValueError, match="feature ids must be unique"):
        MechanisticFeatureObject(
            object_id="object.duplicate",
            version="1.0.0",
            features=(feature, feature),
            configuration=base.configuration,
        )
    feature_two = feature.model_copy(
        update={
            "feature_id": "feature.other",
            "lineage": feature.lineage.model_copy(update={"feature_id": "feature.other"}),
        }
    )
    duplicate_relations = MechanisticFeatureObject.model_construct(
        object_id="object.duplicate-relations",
        version="1.0.0",
        features=(feature, feature_two),
        relations=(),
        configuration=base.configuration,
    )
    relation_a = MechanisticRelation.model_construct(
        relation_id="relation.a",
        source_feature_id=feature.feature_id,
        target_feature_id=feature_two.feature_id,
        kind=MechanisticRelationKind.REGULATES,
    )
    # Self-loop validation is already covered; use model_construct to reach object closure.
    object.__setattr__(duplicate_relations, "relations", (relation_a, relation_a))
    with pytest.raises(ValueError, match="relation ids"):
        type(duplicate_relations).model_validate(duplicate_relations)


def test_request_and_result_closure_reject_tamper_and_duplicate_regions() -> None:
    document = json.loads(request().model_dump_json())
    document["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValueError, match="M12-02"):
        ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(json.dumps(document))
    duplicate_sources = json.loads(request().model_dump_json())
    duplicate_sources["source_artifacts"].append(duplicate_sources["source_artifacts"][0])
    with pytest.raises(ValueError, match="source artifact"):
        ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(
            json.dumps(duplicate_sources)
        )
    duplicate_features = json.loads(request().model_dump_json())
    duplicate_features["feature_inputs"].append(duplicate_features["feature_inputs"][0])
    with pytest.raises(ValueError, match="feature input"):
        ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(
            json.dumps(duplicate_features)
        )
    unknown_relation = json.loads(request().model_dump_json())
    unknown_relation["relations"] = [
        {
            "relation_id": "relation.unknown",
            "source_feature_id": "feature.unknown",
            "target_feature_id": "feature.pathway",
            "kind": "regulates",
        }
    ]
    with pytest.raises(ValueError, match="unknown feature input"):
        ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(
            json.dumps(unknown_relation)
        )
    result = construct_mechanistic_features(request())
    result_document = json.loads(result.model_dump_json())
    result_document["request_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="request digest"):
        type(result).model_validate_json(json.dumps(result_document))
    result_document = json.loads(result.model_dump_json())
    result_document["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="result digest"):
        type(result).model_validate_json(json.dumps(result_document))
    abstained = json.loads(result.model_dump_json())
    abstained["status"] = "abstained"
    abstained["result_digest"] = result_payload_digest(abstained)
    with pytest.raises(ValueError, match="abstained result"):
        type(result).model_validate_json(json.dumps(abstained))
    duplicate_diagnostics = json.loads(result.model_dump_json())
    duplicate_diagnostics["diagnostics"].append(duplicate_diagnostics["diagnostics"][0])
    with pytest.raises(ValueError, match="diagnostic ids"):
        type(result).model_validate_json(json.dumps(duplicate_diagnostics))
    counter_evidence = json.loads(result.model_dump_json())
    counter_evidence["evidence"][0]["role"] = "counter_evidence"
    with pytest.raises(ValueError, match="relabel"):
        type(result).model_validate_json(json.dumps(counter_evidence))
    unsupported = json.loads(result.model_dump_json())
    unsupported["support_decision"]["status"] = "unsupported"
    with pytest.raises(ValueError, match="constructed result"):
        type(result).model_validate_json(json.dumps(unsupported))


def test_strict_replay_and_hostile_preflight_fail_closed() -> None:
    class Hostile:
        def __getattribute__(self, _name: str) -> object:
            raise RuntimeError("hostile")

    with pytest.raises(MechanisticFeatureAuthorizationError):
        preflight_mechanistic_feature_authorization(Hostile())
    with pytest.raises(MechanisticFeatureValidationError):
        _plain_value({1: "non-string-key"})
    assert _state_text("accepted") == "accepted"
    assert _state_text(UpstreamDecisionState.ACCEPTED) == "accepted"
    assert _state_text(object()) is None
    payload = request().model_dump_json()
    assert validate_json_request(json.loads(payload), payload).request_id == request().request_id
    with pytest.raises(ValueError):  # noqa: PT011
        validate_json_request([], payload)
    with pytest.raises(ValueError):  # noqa: PT011
        validate_json_request(json.loads(payload), b"{}")
    mismatched = json.loads(payload)
    mismatched["request_id"] = "request.other"
    with pytest.raises(MechanisticFeatureValidationError):
        validate_json_request(mismatched, payload)


def test_fallback_findings_and_abstention_diagnostics() -> None:
    diagnostics = (
        MechanisticFeatureDiagnostic(
            diagnostic_id="diagnostic.pass",
            status=MechanisticDiagnosticStatus.PASS,
            message="pass",
        ),
    )
    assert _findings(request(), diagnostics)[0].value == "upstream_unsupported"
    assert "input_incomplete" in {
        item.value
        for item in _findings(
            request().model_copy(update={"quality_status": "rejected"}), diagnostics
        )
    }
    assert "not evaluable" in _abstention_reason(request(), diagnostics)
    assert "parent-specific" in _abstention_reason(
        request().model_copy(update={"quality_status": "rejected"}), diagnostics
    )
    failed = (
        MechanisticFeatureDiagnostic(
            diagnostic_id="diagnostic.fail",
            status=MechanisticDiagnosticStatus.FAIL,
            message="failed",
        ),
    )
    assert "topology_invariant_failed" in {item.value for item in _findings(request(), failed)}


def test_dict_replay_mapping_and_service_validation_paths() -> None:
    payload = request().model_dump(mode="json")
    assert construct_mechanistic_features(payload).feature_object is not None
    broken = dict(payload)
    broken["upstream_result"] = {"media_type": "application/json"}
    with pytest.raises(MechanisticFeatureValidationError):
        construct_mechanistic_features(broken)
    normalized = dict(payload)
    normalized_context = dict(normalized["context"])
    normalized_context["occurred_at"] = "2026-01-01T00:00:00+00:00"
    normalized["context"] = normalized_context
    with pytest.raises(MechanisticFeatureValidationError):
        construct_mechanistic_features(normalized)
    with pytest.raises(MechanisticFeatureValidationError):
        _plain_value(UserDict({"request": "mapping"}))
    assert _plain_value(request().feature_inputs[0])["feature_id"] == "feature.pathway"
    service = M1203Service()
    assert service.validate_request(request()).request_id == request().request_id


def test_api_and_cli_negative_paths(tmp_path: Path) -> None:
    client = TestClient(app)
    assert client.get("/v1/m12-03/schema/nope").status_code == HTTP_NOT_FOUND
    malformed = client.post("/v1/modules/M12-03/construct", content=b"not-json")
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT
    bad_result = client.post("/v1/modules/M12-03/verify", content=b"{}")
    assert bad_result.status_code == HTTP_UNPROCESSABLE_CONTENT

    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_text(request().model_dump_json(), encoding="utf-8")
    result_path = tmp_path / "result.json"
    constructed = runner.invoke(m1203_app, ["construct", str(request_path)])
    assert constructed.exit_code == 0
    result_path.write_text(constructed.stdout, encoding="utf-8")
    verified = runner.invoke(m1203_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    invalid_construct = runner.invoke(m1203_app, ["construct", str(tmp_path / "missing.json")])
    assert invalid_construct.exit_code != 0
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1203_app, ["construct", str(malformed_path)]).exit_code != 0
    invalid_result = runner.invoke(m1203_app, ["verify", str(request_path)])
    assert invalid_result.exit_code != 0
    assert runner.invoke(m1203_app, ["export-schema", "nope"]).exit_code != 0
    assert runner.invoke(m1203_app, ["export-schema", "request"]).exit_code == 0
    assert str(m1203_adapter._CliSchemaError())
    assert str(m1203_adapter._CliRequestError())


def test_plugin_descriptor_typed_and_invalid_json_paths() -> None:
    plugin = M1203Plugin(M1203Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-03"
    assert plugin.run(plugin.validate(request())).status.value == "constructed"
    assert (
        plugin.run(plugin.validate(request().model_dump(mode="json"))).status.value == "constructed"
    )
    with pytest.raises(ValueError):  # noqa: PT011
        plugin.validate(b'{"request_id":1}')
