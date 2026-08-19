"""Adversarial contract, runtime, plugin, API, and CLI coverage for M18-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m18_05.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1805 import cli, create_app
from glio_proteogen.contracts.m18_05 import (
    M1805_M1804_INPUT_MEDIA_TYPE,
    BiomarkerPanelReviewWorkspaceResult,
    HumanReviewWorkspace,
    PresentBiomarkerPanelReviewWorkspaceRequest,
    WorkspaceConfiguration,
    WorkspaceFindingCode,
    WorkspaceSectionKind,
    WorkspaceStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c18_spatial_proteomics.m18_05_workflow_presentation_service import (
    M1805AuthorizationError,
    M1805Plugin,
    M1805ReplayVerificationError,
    M1805Service,
    M1805WorkflowPresentationEngine,
    ValidatedM1805Request,
    preflight_m1805_authorization,
    present_biomarker_panel_review_workspace,
)

if TYPE_CHECKING:
    from pathlib import Path


HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
CLI_ERROR = 1
CLI_REFUSED = 2
SECTION_COUNT = 6
ESTIMATED_PROBABILITY = 0.9


def _request_payload(request: PresentBiomarkerPanelReviewWorkspaceRequest) -> dict[str, object]:
    return request.model_dump(mode="json")


def _validated_request(
    request: PresentBiomarkerPanelReviewWorkspaceRequest, **updates: object
) -> PresentBiomarkerPanelReviewWorkspaceRequest:
    payload = request.model_dump(mode="python")
    payload.update(updates)
    return PresentBiomarkerPanelReviewWorkspaceRequest.model_validate(payload, strict=True)


def _validated_result(
    result: BiomarkerPanelReviewWorkspaceResult, **updates: object
) -> BiomarkerPanelReviewWorkspaceResult:
    payload = result.model_dump(mode="python")
    payload.update(updates)
    return BiomarkerPanelReviewWorkspaceResult.model_validate(payload, strict=True)


def test_runtime_presents_complete_workspace_with_safe_ordering() -> None:
    result = M1805WorkflowPresentationEngine().infer(build_scenario_request())

    assert result.status is WorkspaceStatus.PRESENTED
    assert result.workspace is not None
    assert len(result.workspace.sections) == SECTION_COUNT
    assert result.workspace.default_section_order[0] == "section.m1805.0"
    assert result.workspace.sections[0].kind is WorkspaceSectionKind.TASK_SUMMARY
    assert result.workspace.configuration.automation_bias_warning
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert result.uncertainty.measurement.probability == ESTIMATED_PROBABILITY
    assert len(result.provenance.control_decisions) == SECTION_COUNT + 1
    assert result.findings[0].code is WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
    assert present_biomarker_panel_review_workspace(build_scenario_request()) == result


def test_runtime_abstains_without_workspace_for_unsupported_inputs() -> None:
    result = M1805WorkflowPresentationEngine().infer(build_scenario_request("unsupported"))

    assert result.status is WorkspaceStatus.ABSTAINED
    assert result.workspace is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.abstention_reason
    assert result.findings[0].code is WorkspaceFindingCode.UPSTREAM_UNSUPPORTED
    assert result.uncertainty.measurement.probability is None
    assert any(item.code == "safe_abstention" for item in result.limitations)


def test_service_accepts_bytes_mapping_and_typed_inputs_but_rejects_duplicate_json() -> None:
    service = M1805Service()
    request = build_scenario_request()
    payload = canonical_json_bytes(request)
    assert service.execute(payload) == service.execute(_request_payload(request))
    assert service.execute(request).status is WorkspaceStatus.PRESENTED
    with pytest.raises(ValueError, match="duplicate"):
        service.execute(b'{"request_id":"first","request_id":"second"}')


def test_service_verify_accepts_bytes_mapping_and_typed_result() -> None:
    service = M1805Service()
    result = service.execute(build_scenario_request())
    assert service.verify(canonical_json_bytes(result)) == result
    assert service.verify(result.model_dump(mode="json")) == result
    assert service.verify(result) == result
    assert service.verify(result, replay=False) == result


def test_plugin_requires_issued_parse_once_token() -> None:
    service = M1805Service()
    plugin = M1805Plugin(service)
    other_plugin = M1805Plugin(M1805Service())
    token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert isinstance(token, ValidatedM1805Request)
    assert plugin.run(token).status is WorkspaceStatus.PRESENTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M18-05"
    assert plugin.validate(build_scenario_request()).request == token.request
    assert plugin.verify(plugin.run(token)) == plugin.run(token)

    forged = ValidatedM1805Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="validated request token"):
        other_plugin.run(token)

    forged = ValidatedM1805Request(request=token.request, _seal=token._seal)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

    nested_mutation = token.request.sections[0].model_copy(
        update={"title": "nested post-validation mutation"}
    )
    mutated_request = token.request.model_copy(
        update={"sections": (nested_mutation, *token.request.sections[1:])}
    )
    object.__setattr__(token, "request", mutated_request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_authorization_is_fail_closed_for_mapping_and_broken_context() -> None:
    states = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    preflight_m1805_authorization(
        {"context": {"references": {role: {"state": state} for role, state in states.items()}}}
    )

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M1805AuthorizationError):
        preflight_m1805_authorization({"context": BrokenMapping()})


def test_request_closure_rejects_wrong_media_duplicate_order_and_unknown_sources() -> None:
    request = build_scenario_request()
    bad_upstream = request.upstream_result.model_copy(
        update={"media_type": "application/octet-stream"}
    )
    with pytest.raises(ValidationError, match="M18-04 intended-use"):
        _validated_request(request, upstream_result=bad_upstream)

    duplicate_section = request.sections[1].model_copy(
        update={"section_id": request.sections[0].section_id}
    )
    with pytest.raises(ValidationError, match="section ids"):
        _validated_request(
            request, sections=(request.sections[0], duplicate_section, *request.sections[2:])
        )

    with pytest.raises(ValidationError, match="default order"):
        _validated_request(
            request,
            default_section_order=tuple(reversed(request.default_section_order)),
        )

    unknown_source = (
        request.sections[0].source_artifacts[0].model_copy(update={"artifact_id": "source.unknown"})
    )
    changed_section = request.sections[0].model_copy(update={"source_artifacts": (unknown_source,)})
    with pytest.raises(ValidationError, match="unknown source"):
        _validated_request(request, sections=(changed_section, *request.sections[1:]))


def test_request_closure_rejects_duplicate_source_artifacts_and_missing_upstream() -> None:
    request = build_scenario_request()
    with pytest.raises(ValidationError, match="source artifacts"):
        _validated_request(request, source_artifacts=(request.source_artifacts[0],) * 2)
    with pytest.raises(ValidationError, match="upstream result"):
        _validated_request(request, source_artifacts=(request.source_artifacts[1],))


def test_configuration_and_workspace_closure_reject_missing_views_or_unsafe_order() -> None:
    request = build_scenario_request()
    with pytest.raises(ValidationError, match="all six"):
        WorkspaceConfiguration.model_validate(
            request.configuration.model_copy(
                update={
                    "required_sections": (
                        *tuple(WorkspaceSectionKind)[:-1],
                        WorkspaceSectionKind.TASK_SUMMARY,
                    )
                }
            ).model_dump(mode="python"),
            strict=True,
        )

    result = M1805WorkflowPresentationEngine().infer(request)
    assert result.workspace is not None
    workspace = result.workspace

    def validate(candidate: HumanReviewWorkspace) -> None:
        HumanReviewWorkspace.model_validate(candidate.model_dump(mode="python"), strict=True)

    duplicate_id = workspace.model_copy(
        update={"sections": (workspace.sections[0], workspace.sections[0], *workspace.sections[2:])}
    )
    with pytest.raises(ValidationError, match="section ids"):
        validate(duplicate_id)

    missing_kind = workspace.model_copy(
        update={
            "sections": (
                *workspace.sections[:5],
                workspace.sections[1].model_copy(
                    update={"section_id": "section.m1805.evidence.duplicate"}
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="every required"):
        validate(missing_kind)

    unsafe_order = workspace.model_copy(
        update={"default_section_order": tuple(reversed(workspace.default_section_order))}
    )
    with pytest.raises(ValidationError, match="task summary"):
        validate(unsafe_order)


def test_workspace_closure_rejects_duplicate_or_incomplete_default_order() -> None:
    result = M1805WorkflowPresentationEngine().infer(build_scenario_request())
    assert result.workspace is not None
    workspace = result.workspace
    duplicate_order = workspace.model_copy(
        update={
            "default_section_order": (
                workspace.default_section_order[0],
                workspace.default_section_order[0],
                *workspace.default_section_order[2:],
            )
        }
    )
    with pytest.raises(ValidationError, match="exactly once"):
        HumanReviewWorkspace.model_validate(duplicate_order.model_dump(mode="python"), strict=True)


def test_result_closure_rejects_digest_status_and_finding_drift() -> None:
    engine = M1805WorkflowPresentationEngine()
    presented = engine.infer(build_scenario_request())
    abstained = engine.infer(build_scenario_request("unsupported"))

    with pytest.raises(ValidationError, match="request digest"):
        _validated_result(presented, request_digest="sha256:" + "a" * 64)
    with pytest.raises(ValidationError, match="presented result"):
        _validated_result(presented, workspace=None)
    with pytest.raises(ValidationError, match="abstained result"):
        _validated_result(abstained, workspace=presented.workspace)
    with pytest.raises(ValidationError, match="abstained result"):
        _validated_result(abstained, abstention_reason=None)
    with pytest.raises(ValidationError, match="result digest"):
        _validated_result(presented, result_digest="sha256:" + "b" * 64)

    finding = presented.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        _validated_result(presented, findings=(finding, finding))
    same_code = finding.model_copy(update={"finding_id": "finding.other"})
    with pytest.raises(ValidationError, match="finding codes"):
        _validated_result(presented, findings=(finding, same_code))


def test_replay_tamper_and_public_digest_are_canonical() -> None:
    engine = M1805WorkflowPresentationEngine()
    request = build_scenario_request()
    result = engine.infer(request)
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )

    tampered = result.model_copy(update={"result_digest": "sha256:" + "a" * 64})
    with pytest.raises(M1805ReplayVerificationError):
        engine.verify(tampered)
    with pytest.raises(M1805ReplayVerificationError):
        engine.verify({"not": "a result"})

    altered_request = build_scenario_request("unsupported")
    altered = result.model_copy(
        update={
            "request": altered_request,
            "request_digest": canonical_request_digest(altered_request),
        }
    )
    object.__setattr__(altered, "result_digest", result_payload_digest(altered))
    with pytest.raises(M1805ReplayVerificationError):
        engine.verify(altered)


def test_api_schema_export_and_route_parity() -> None:
    request = build_scenario_request()
    with TestClient(create_app()) as client:
        schema = client.get("/v1/m18-05/schema/request")
        assert schema.status_code == HTTP_OK
        assert schema.json()["x-glio-contract"]["parentTarget"] == "biomarker panel"
        assert client.get("/v1/m18-05/schema/unknown").status_code == HTTP_NOT_FOUND

        presented = client.post("/v1/modules/M18-05/present", json=_request_payload(request))
        assert presented.status_code == HTTP_OK
        body = presented.json()
        assert body["status"] == "presented"
        verified = client.post("/v1/modules/M18-05/verify", json=body)
        assert verified.status_code == HTTP_OK
        assert verified.json()["result_digest"] == body["result_digest"]


def test_api_sanitizes_auth_malformed_and_tamper_failures() -> None:
    with TestClient(create_app()) as client:
        denied = client.post(
            "/v1/modules/M18-05/present",
            json=_request_payload(build_scenario_request(accepted=False)),
        )
        assert denied.status_code == HTTP_FORBIDDEN
        assert "requires accepted controls" not in denied.text
        malformed = client.post("/v1/modules/M18-05/present", content=b"{not-json")
        assert malformed.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert "Traceback" not in malformed.text

        result = M1805Service().execute(build_scenario_request()).model_dump(mode="json")
        result["result_digest"] = "sha256:" + "a" * 64
        replay = client.post("/v1/modules/M18-05/verify", json=result)
        assert replay.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_api_maps_explicit_replay_error() -> None:
    class ReplayService(M1805Service):
        def verify(
            self,
            result: object,
            *,
            replay: bool = True,
        ) -> BiomarkerPanelReviewWorkspaceResult:
            del result, replay
            raise M1805ReplayVerificationError

    with TestClient(create_app(ReplayService())) as client:
        response = client.post("/v1/modules/M18-05/verify", json={"ignored": True})
        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert response.json()["detail"] == "M18-05 replay verification failed"


def test_cli_present_verify_overwrite_stdin_and_auth(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M18-05"

    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    presented = runner.invoke(cli, ["present", str(request_path), "--output", str(output_path)])
    assert presented.exit_code == 0
    verified = runner.invoke(cli, ["verify", str(output_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["status"] == "presented"
    refused = runner.invoke(cli, ["present", str(request_path), "--output", str(output_path)])
    assert refused.exit_code == CLI_REFUSED
    stdin = runner.invoke(
        cli, ["present", "-"], input=canonical_json_bytes(build_scenario_request()).decode()
    )
    assert stdin.exit_code == 0
    invalid = runner.invoke(cli, ["present", str(tmp_path / "missing.json")])
    assert invalid.exit_code == CLI_ERROR
    assert "Traceback" not in invalid.output

    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(build_scenario_request(accepted=False)))
    denied = runner.invoke(cli, ["present", str(denied_path)])
    assert denied.exit_code == CLI_REFUSED
    assert "authorization denied" in denied.output


def test_cli_rejects_tampered_result(tmp_path: Path) -> None:
    runner = CliRunner()
    result = M1805Service().execute(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "b" * 64
    result_path = tmp_path / "tampered.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    verified = runner.invoke(cli, ["verify", str(result_path)])
    assert verified.exit_code == CLI_ERROR
    assert "Traceback" not in verified.output


def test_explicit_media_and_section_catalogue() -> None:
    assert build_scenario_request().upstream_result.media_type == M1805_M1804_INPUT_MEDIA_TYPE
    assert set(WorkspaceSectionKind) == {
        WorkspaceSectionKind.TASK_SUMMARY,
        WorkspaceSectionKind.EVIDENCE_SUMMARY,
        WorkspaceSectionKind.UNCERTAINTY,
        WorkspaceSectionKind.DISCREPANCIES,
        WorkspaceSectionKind.PROVENANCE,
        WorkspaceSectionKind.NEXT_ACTION,
    }
