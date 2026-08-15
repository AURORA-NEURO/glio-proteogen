"""Deep runtime, replay, adapter, and safety gates for provisional M12-03."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.m1203 import app, m1203_app
from glio_proteogen.contracts.m12_03 import (
    M1203_M1202_INPUT_MEDIA_TYPE,
    M1203_OPERATION,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureLineage,
    MechanisticFeatureKind,
    MechanisticValueKind,
    NegativeControlStatus,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
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


def request(*, negative: NegativeControlStatus = NegativeControlStatus.PASSED) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
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
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "constructed"
    verified = client.post("/v1/modules/M12-03/verify", json=result)
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    schema = client.get("/v1/m12-03/schema/request")
    assert schema.status_code == 200
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    bad = client.post("/v1/modules/M12-03/construct", content=b"{\"request_id\": 3}")
    assert bad.status_code == 422
    assert "validation" in bad.json()["error"]["message"]
    assert "traceback" not in bad.text.lower()


def test_cli_schema_no_overwrite(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    output = tmp_path / "schema.json"
    runner = CliRunner()
    first = runner.invoke(m1203_app, ["export-schema", "request", "--output", str(output)])
    assert first.exit_code == 0
    second = runner.invoke(m1203_app, ["export-schema", "request", "--output", str(output)])
    assert second.exit_code != 0
