"""Deep contract, runtime, adapter, replay, and safety coverage for M17-05."""

# Assertions intentionally exercise sanitized exception paths.
# ruff: noqa: BLE001, PLR2004, PT017, TRY003

from __future__ import annotations

from copy import deepcopy
from typing import Any

from evals.m17_05.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1705 import cli, create_app
from glio_proteogen.contracts.m17_05 import (
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    ReviewItemStatus,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_05_workflow_presentation_service import (
    M1705AuthorizationError,
    M1705Plugin,
    M1705ReplayVerificationError,
    M1705Service,
    M1705WorkflowPresentationEngine,
)


def _request(
    scenario: str = "supported",
    *,
    accepted: bool = True,
) -> PresentVariantPeptideHumanReviewWorkspaceRequest:
    return build_scenario_request(scenario, accepted=accepted)


def test_contract_rejects_wrong_media_and_duplicate_views() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["aligned_evidence_bundle"]["media_type"] = "application/json"
    try:
        PresentVariantPeptideHumanReviewWorkspaceRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
    except ValueError as error:
        assert "M17-02" in str(error)
    else:
        raise AssertionError("wrong upstream media must be rejected")

    payload = _request().model_dump(mode="json")
    policy = payload["policy"]
    policy["required_views"] = ["task_summary", "task_summary"]
    try:
        PresentVariantPeptideHumanReviewWorkspaceRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate required views must be rejected")


def test_runtime_presents_safe_order_and_preserves_parent_boundary() -> None:
    result = M1705WorkflowPresentationEngine().infer(_request("conflicted"))
    assert result.status.value == "presented"
    assert result.workspace is not None
    assert result.workspace.safe_default_order is True
    assert result.workspace.items[0].status is ReviewItemStatus.CONFLICTED
    assert result.parent_target == "variant_peptide"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert any(finding.code.value == "discrepancy_requires_review" for finding in result.findings)


def test_runtime_abstains_for_unresolved_material() -> None:
    result = M1705WorkflowPresentationEngine().infer(_request("abstained"))
    assert result.status.value == "abstained"
    assert result.workspace is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_service_bytes_plugin_and_tamper_replay() -> None:
    service = M1705Service()
    request = _request()
    result = service.execute(canonical_json_bytes(request))
    assert service.verify(result.model_dump(mode="json")) == result

    plugin = M1705Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(token) == result
    assert plugin.verify(result) == result

    tampered: dict[str, Any] = deepcopy(result.model_dump(mode="json"))
    tampered["result_digest"] = "sha256:" + ("a" * 64)
    try:
        service.verify(tampered)
    except Exception as error:
        assert isinstance(error, (ValueError, M1705ReplayVerificationError))
    else:
        raise AssertionError("tampered result must fail verification")


def test_authorization_gate_runs_before_execution() -> None:
    denied = _request().model_copy(
        update={"context": _request(accepted=False).context},
    )
    try:
        M1705WorkflowPresentationEngine().infer(denied)
    except M1705AuthorizationError:
        pass
    else:
        raise AssertionError("rejected controls must deny execution")


def test_fastapi_schema_present_verify_and_sanitized_error() -> None:
    client = TestClient(create_app())
    request = _request()
    schema = client.get("/v1/m17-05/schema/request")
    assert schema.status_code == 200
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True

    presented = client.post(
        "/v1/modules/M17-05/present",
        content=canonical_json_bytes(request),
        headers={"content-type": "application/json"},
    )
    assert presented.status_code == 200
    result = presented.json()
    verified = client.post(
        "/v1/modules/M17-05/verify",
        content=canonical_json_bytes(result),
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == 200

    bad = client.post(
        "/v1/modules/M17-05/present",
        content=b'{"context": {"leaked": "details"}}',
        headers={"content-type": "application/json"},
    )
    assert bad.status_code == 422
    assert "leaked" not in bad.text


def test_typer_schema_and_no_overwrite(tmp_path: Any) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert '"provisionalAbi": true' in schema.stdout

    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    output_path = tmp_path / "result.json"
    first = runner.invoke(cli, ["present", str(request_path), "--output", str(output_path)])
    assert first.exit_code == 0
    second = runner.invoke(cli, ["present", str(request_path), "--output", str(output_path)])
    assert second.exit_code == 2
