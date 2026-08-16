"""Deep contract, runtime, adapter, replay, and safety coverage for M17-05."""

# Assertions intentionally exercise sanitized exception paths.
# ruff: noqa: BLE001, E501, PLR2004, PT017, TRY003

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from evals.m17_05.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1705 import cli, create_app
from glio_proteogen.contracts.m17_05 import (
    HumanReviewWorkspace,
    OrderingPolicy,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    ReviewItemStatus,
    VariantPeptideHumanReviewWorkspaceResult,
    ViewKind,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_05_workflow_presentation_service import (
    M1705AuthorizationError,
    M1705Plugin,
    M1705ReplayVerificationError,
    M1705Service,
    M1705WorkflowPresentationEngine,
    ValidatedM1705Request,
    preflight_m1705_authorization,
    present_variant_peptide_human_review_workspace,
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


def test_contract_rejects_item_request_and_result_closure_breaks() -> None:
    request = _request()
    result = M1705WorkflowPresentationEngine().infer(request)
    assert result.workspace is not None

    duplicate_items = result.workspace.model_copy(
        update={"items": (result.workspace.items[0], result.workspace.items[0])}
    )
    with pytest.raises(ValueError, match="item ids must be unique"):
        HumanReviewWorkspace.model_validate(duplicate_items.model_dump(mode="python"), strict=True)

    noncontiguous = result.workspace.model_copy(
        update={
            "items": (
                result.workspace.items[0],
                result.workspace.items[1].model_copy(update={"position": 2}),
            )
        }
    )
    with pytest.raises(ValueError, match="contiguous"):
        HumanReviewWorkspace.model_validate(noncontiguous.model_dump(mode="python"), strict=True)

    def invalid_request(candidate: PresentVariantPeptideHumanReviewWorkspaceRequest) -> None:
        PresentVariantPeptideHumanReviewWorkspaceRequest.model_validate(
            candidate.model_dump(mode="python"), strict=True
        )

    with pytest.raises(ValueError, match="configured workspace item limit"):
        invalid_request(
            request.model_copy(
                update={"policy": request.policy.model_copy(update={"maximum_items": 1})}
            )
        )
    with pytest.raises(ValueError, match="review item ids"):
        invalid_request(request.model_copy(update={"review_items": (request.review_items[0],) * 2}))
    with pytest.raises(ValueError, match="contiguous"):
        invalid_request(
            request.model_copy(
                update={
                    "review_items": (
                        request.review_items[0],
                        request.review_items[1].model_copy(update={"position": 2}),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="every policy-required"):
        invalid_request(
            request.model_copy(
                update={
                    "review_items": request.review_items[:5],
                    "policy": request.policy.model_copy(
                        update={"required_views": (ViewKind.NEXT_ACTION,)}
                    ),
                }
            )
        )
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        invalid_request(
            request.model_copy(
                update={"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])}
            )
        )
    with pytest.raises(ValueError, match="aligned evidence bundle"):
        invalid_request(
            request.model_copy(update={"source_artifacts": request.source_artifacts[1:]})
        )
    missing_provenance = request.review_items[0].model_copy(
        update={
            "provenance_artifact": request.source_artifacts[0].model_copy(
                update={"digest": "sha256:" + ("0" * 64)}
            )
        }
    )
    with pytest.raises(ValueError, match="provenance"):
        invalid_request(
            request.model_copy(
                update={"review_items": (missing_provenance, *request.review_items[1:])}
            )
        )
    missing_evidence = request.review_items[0].model_copy(
        update={
            "evidence": (
                request.review_items[0].evidence[0].model_copy(
                    update={
                        "reference": request.source_artifacts[0].model_copy(
                            update={"digest": "sha256:" + ("0" * 64)}
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="evidence must bind"):
        invalid_request(
            request.model_copy(
                update={"review_items": (missing_evidence, *request.review_items[1:])}
            )
        )

    def invalid_result(candidate: VariantPeptideHumanReviewWorkspaceResult) -> None:
        VariantPeptideHumanReviewWorkspaceResult.model_validate(
            candidate.model_dump(mode="python"), strict=True
        )

    with pytest.raises(ValueError, match="request digest"):
        invalid_result(result.model_copy(update={"request_digest": "sha256:" + ("a" * 64)}))
    with pytest.raises(ValueError, match="supported workspace"):
        invalid_result(result.model_copy(update={"workspace": None}))
    with pytest.raises(ValueError, match="ordering"):
        invalid_result(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(
                        update={"ordering": OrderingPolicy.UNCERTAINTY_FIRST}
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="source bundle"):
        invalid_result(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(
                        update={"source_bundle": request.source_artifacts[1]}
                    )
                }
            )
        )
    renamed = result.workspace.items[0].model_copy(update={"item_id": "different.item"})
    with pytest.raises(ValueError, match="exactly the request"):
        invalid_result(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(
                        update={"items": (renamed, *result.workspace.items[1:])}
                    )
                }
            )
        )
    abstained = M1705WorkflowPresentationEngine().infer(_request("abstained"))
    with pytest.raises(ValueError, match="no workspace"):
        invalid_result(abstained.model_copy(update={"workspace": result.workspace}))
    with pytest.raises(ValueError, match="finding ids"):
        invalid_result(
            result.model_copy(update={"findings": (result.findings[0], result.findings[0])})
        )
    duplicate_code = result.findings[0].model_copy(update={"finding_id": "finding.other"})
    with pytest.raises(ValueError, match="finding codes"):
        invalid_result(result.model_copy(update={"findings": (result.findings[0], duplicate_code)}))


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


def test_engine_defensive_replay_ordering_and_public_operation() -> None:
    engine = M1705WorkflowPresentationEngine()
    request = build_scenario_request(ordering=OrderingPolicy.UNCERTAINTY_FIRST)
    result = engine.infer(request)
    assert result.workspace is not None
    assert result.workspace.ordering.value == "uncertainty_first"
    assert present_variant_peptide_human_review_workspace(request) == result
    preflight_m1705_authorization(
        {"context": {"references": request.context.references.model_dump(mode="json")}}
    )
    with pytest.raises(M1705AuthorizationError):
        preflight_m1705_authorization({"context": {}})
    with pytest.raises(M1705ReplayVerificationError):
        engine.verify(object())
    with pytest.raises(M1705ReplayVerificationError):
        engine.verify(
            result.model_copy(update={"result_digest": "sha256:" + ("a" * 64)}),
            replay=False,
        )
    replay_mismatch = result.model_copy(update={"human_review_required": False})
    replay_mismatch = replay_mismatch.model_copy(
        update={"result_digest": result_payload_digest(replay_mismatch)}
    )
    with pytest.raises(M1705ReplayVerificationError):
        engine.verify(replay_mismatch)
    assert engine.verify(result, replay=False) == result


def test_service_bytes_plugin_and_tamper_replay() -> None:
    service = M1705Service()
    request = _request()
    result = service.execute(canonical_json_bytes(request))
    assert service.verify(result.model_dump(mode="json")) == result

    plugin = M1705Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(token) == result
    mapping_token = plugin.validate(request.model_dump(mode="json"))
    assert plugin.run(mapping_token) == result
    assert plugin.verify(result) == result
    assert service.validate_request(request) == request
    assert service.verify(canonical_json_bytes(result)) == result
    assert service.descriptor().module_id == "GLIO-PROTEOGEN-M17-05"
    with pytest.raises(TypeError):
        plugin.run(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        plugin.run(ValidatedM1705Request(request=request, _seal=object()))

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
    assert client.get("/v1/m17-05/schema/nope").status_code == 404

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
    tampered_result = deepcopy(result)
    tampered_result["result_digest"] = "sha256:" + ("a" * 64)
    assert (
        client.post(
            "/v1/modules/M17-05/verify",
            content=canonical_json_bytes(tampered_result),
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    denied = client.post(
        "/v1/modules/M17-05/present",
        content=canonical_json_bytes(_request(accepted=False)),
        headers={"content-type": "application/json"},
    )
    assert denied.status_code == 403

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
    stdout_result = runner.invoke(cli, ["present", str(request_path)])
    assert stdout_result.exit_code == 0
    stdin_result = runner.invoke(
        cli,
        ["present", "-"],
        input=canonical_json_bytes(_request()).decode("utf-8"),
    )
    assert stdin_result.exit_code == 0
    verified = runner.invoke(cli, ["verify", str(output_path)])
    assert verified.exit_code == 0
    second = runner.invoke(cli, ["present", str(request_path), "--output", str(output_path)])
    assert second.exit_code == 2
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(_request(accepted=False)))
    assert runner.invoke(cli, ["present", str(denied_path)]).exit_code == 2
    assert runner.invoke(cli, ["present", str(tmp_path / "missing.json")]).exit_code == 1
