"""Deep contract, replay and adversarial coverage for M19-05."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1905 import cli, create_app
from glio_proteogen.contracts.m19_05 import (
    M1905_DOSSIER_SHA256,
    M1905_DOSSIER_SLICE,
    M1905_M1904_RESULT_MEDIA_TYPE,
    HumanReviewWorkspace,
    OrderingPolicy,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
    WorkspaceStatus,
    contract_json_schemas,
)
from glio_proteogen.contracts.m19_05.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_05_workflow_presentation_service import (  # noqa: E501
    M1905AuthorizationError,
    M1905Engine,
    M1905Plugin,
    M1905ReplayError,
    M1905Service,
    ValidatedM1905Request,
)

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 8
_CONTROL_COUNT = 7
_ESTIMATED_PROBABILITY = 0.9
_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_FORBIDDEN = 403
_HTTP_UNPROCESSABLE = 422
_CLI_ERROR = 1
_CLI_REFUSED = 2


def _artifact(
    artifact_id: str,
    character: str,
    media_type: str = "application/octet-stream",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version="1.0.0",
        digest="sha256:" + character * 64,
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M19-05 review evidence.",
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision_state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity_state = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.CONFLICTED
    consent_state = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.config", "1"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity_state,
            policy_version="1.0.0",
            binding_digest="sha256:" + "2" * 64,
            evidence=_artifact("control.identity", "2"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance", "3"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent_state,
            policy_version="1.0.0",
            evidence=_artifact("control.consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.quality", "5"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.support", "6"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.intended", "7"),
        ),
    )


def build_request(
    *,
    item_status: ReviewItemStatus = ReviewItemStatus.SUPPORTED,
    accepted: bool = True,
) -> PresentProteotypeHumanReviewWorkspaceRequest:
    upstream = _artifact("upstream.m1904", "8", M1905_M1904_RESULT_MEDIA_TYPE)
    item_artifacts = tuple(_artifact(f"item.{index}", chr(97 + index)) for index in range(6))
    items = tuple(
        ReviewItem(
            item_id=f"item.{index}",
            view_kind=view,
            title=view.value.replace("_", " ").title(),
            position=index,
            status=item_status,
            evidence=(_evidence(item_artifacts[index]),),
            uncertainty_summary="Caller-declared uncertainty remains visible to the reviewer.",
            evidence_summary="Caller-declared evidence summary is attributable.",
            provenance_artifact=item_artifacts[index],
        )
        for index, view in enumerate(ViewKind)
    )
    configuration_artifact = _artifact("configuration.m1905", "9")
    configuration = PresentationConfiguration(
        configuration_id="configuration.m1905",
        version="1.0.0",
        method="locked-human-review-presentation",
        model_reference=_artifact("model.m1905", "0"),
        evidence=(_evidence(configuration_artifact),),
    )
    policy = PresentationPolicy(
        required_views=tuple(ViewKind),
        default_ordering=OrderingPolicy.SAFE_DEFAULT,
        maximum_items=6,
        configuration=configuration,
    )
    source_artifacts = (upstream, *item_artifacts)
    return PresentProteotypeHumanReviewWorkspaceRequest(
        request_id="request.m1905",
        context=ExecutionContext(
            request_id="request.m1905",
            actor_id="actor.synthetic",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        aligned_evidence_bundle=upstream,
        policy=policy,
        review_items=items,
        source_artifacts=source_artifacts,
    )


def test_contract_metadata_binds_authority_and_strict_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["dossierSha256"] == M1905_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M1905_DOSSIER_SLICE
        assert metadata["strict"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["taskSpecificViews"] == [view.value for view in ViewKind]
        assert metadata["upstreamInputMediaType"] == M1905_M1904_RESULT_MEDIA_TYPE


def test_request_closure_rejects_identity_drift_duplicates_and_missing_views() -> None:
    request = build_request()
    with pytest.raises(ValidationError, match="request id"):
        PresentProteotypeHumanReviewWorkspaceRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "context": request.context.model_copy(
                    update={"request_id": "request.other"}
                ).model_dump(mode="python")
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="source artifact ids"):
        PresentProteotypeHumanReviewWorkspaceRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0],) * 2},
            strict=True,
        )
    with pytest.raises(ValidationError, match="all six"):
        PresentationPolicy.model_validate(
            request.policy.model_dump(mode="python") | {"required_views": tuple(ViewKind)[:-1]},
            strict=True,
        )


def test_workspace_closure_rejects_reordered_or_incomplete_material() -> None:
    result = M1905Engine().present(build_request())
    assert result.workspace is not None
    workspace = result.workspace
    reordered = workspace.model_copy(update={"items": tuple(reversed(workspace.items))})
    with pytest.raises(ValidationError, match="positions"):
        HumanReviewWorkspace.model_validate(reordered.model_dump(mode="python"), strict=True)
    incomplete = workspace.model_copy(update={"items": workspace.items[:-1]})
    with pytest.raises(ValidationError, match="every workspace view"):
        HumanReviewWorkspace.model_validate(incomplete.model_dump(mode="python"), strict=True)


def test_engine_presents_all_views_and_preserves_uncertainty_provenance() -> None:
    engine = M1905Engine()
    request = build_request()
    result = engine.present(request)
    assert result.status is WorkspaceStatus.PRESENTED
    assert result.workspace is not None
    assert result.workspace.items == request.review_items
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.probability == _ESTIMATED_PROBABILITY
    assert result.request_digest == canonical_request_digest(request)
    assert engine.verify(result) == result


def test_engine_abstains_on_abstained_item_without_negative_conversion() -> None:
    result = M1905Engine().present(build_request(item_status=ReviewItemStatus.ABSTAINED))
    assert result.status is WorkspaceStatus.ABSTAINED
    assert result.workspace is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason is not None
    assert result.uncertainty.measurement.probability is None
    assert result.emits_parent is False


def test_authorization_gate_is_fail_closed_and_sanitized() -> None:
    with pytest.raises(M1905AuthorizationError):
        M1905Engine().present(build_request(accepted=False))
    with pytest.raises(M1905AuthorizationError):
        M1905Engine().present({"request_id": "request.m1905"})


def test_replay_detects_digest_request_and_payload_tampering() -> None:
    engine = M1905Engine()
    result = engine.present(build_request())
    with pytest.raises(M1905ReplayError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "a" * 64}))
    changed_request = build_request(item_status=ReviewItemStatus.LIMITED)
    altered = result.model_copy(
        update={
            "request": changed_request,
            "request_digest": canonical_request_digest(changed_request),
        }
    )
    with pytest.raises(M1905ReplayError):
        engine.verify(altered)
    with pytest.raises(M1905ReplayError):
        engine.verify({"not": "a result"})


def test_strict_validation_rejects_extra_fields_and_coercion() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        PresentProteotypeHumanReviewWorkspaceRequest.model_validate(payload, strict=True)
    invalid_item = request.review_items[0].model_dump(mode="python")
    invalid_item["position"] = "0"
    with pytest.raises(ValidationError):
        ReviewItem.model_validate(invalid_item, strict=True)


def test_service_json_boundary_and_plugin_token_seam_are_parse_once() -> None:
    request = build_request()
    service = M1905Service()
    payload = canonical_json_bytes(request)
    result = service.execute(payload)
    assert service.verify(canonical_json_bytes(result)) == result

    plugin = M1905Plugin(service)
    token = plugin.validate(payload)
    assert isinstance(token, ValidatedM1905Request)
    assert plugin.run(token) == result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M19-05"
    assert plugin.descriptor().owner == "Data engineering"

    forged = ValidatedM1905Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_service_rejects_duplicate_json_keys_and_oversized_payload() -> None:
    service = M1905Service()
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        service.validate_request('{"request_id":"one","request_id":"two"}')
    with pytest.raises(ValueError, match="JSON input exceeds the byte limit"):
        service.validate_request(b'{"request_id":"' + b"x" * 5_000_000 + b'"}')


def test_fastapi_schema_present_verify_and_sanitized_failures() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app()) as client:
        schema = client.get("/v1/m19-05/schema/request")
        assert schema.status_code == _HTTP_OK
        assert schema.json()["x-glio-contract"]["parentTarget"] == "proteotype"
        assert client.get("/v1/m19-05/schema/unknown").status_code == _HTTP_NOT_FOUND

        presented = client.post("/v1/modules/M19-05/present", json=payload)
        assert presented.status_code == _HTTP_OK
        result = presented.json()
        assert result["status"] == "presented"
        verified = client.post("/v1/modules/M19-05/verify", json=result)
        assert verified.status_code == _HTTP_OK
        assert verified.json()["result_digest"] == result["result_digest"]

        denied = client.post(
            "/v1/modules/M19-05/present",
            json=build_request(accepted=False).model_dump(mode="json"),
        )
        assert denied.status_code == _HTTP_FORBIDDEN
        assert "requires accepted controls" not in denied.text

        malformed = client.post("/v1/modules/M19-05/present", content=b"{not-json")
        assert malformed.status_code == _HTTP_UNPROCESSABLE
        assert "Traceback" not in malformed.text

        result["result_digest"] = "sha256:" + "a" * 64
        tampered = client.post("/v1/modules/M19-05/verify", json=result)
        assert tampered.status_code == _HTTP_UNPROCESSABLE
        assert tampered.json()["detail"] == "M19-05 replay verification failed"


def test_typer_schema_present_verify_no_overwrite_and_safe_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M19-05"

    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    presented = runner.invoke(cli, ["present", str(request_path), "--output", str(result_path)])
    assert presented.exit_code == 0
    verified = runner.invoke(cli, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["status"] == "presented"
    refused = runner.invoke(cli, ["present", str(request_path), "--output", str(result_path)])
    assert refused.exit_code == _CLI_REFUSED
    assert "refusing overwrite" in refused.output

    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(build_request(accepted=False)))
    denied = runner.invoke(cli, ["present", str(denied_path)])
    assert denied.exit_code == _CLI_REFUSED
    assert "authorization denied" in denied.output

    missing = runner.invoke(cli, ["verify", str(tmp_path / "missing.json")])
    assert missing.exit_code == _CLI_ERROR
    assert "Traceback" not in missing.output
