"""Negative-path coverage for the M20-05 safety envelope."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m20_05.benchmark import main as benchmark_main
from evals.m20_05.benchmark import run_benchmark
from evals.m20_05.evaluator import main as evaluator_main
from evals.m20_05.evaluator import run_evaluator
from evals.m20_05.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m20_05 import (
    HumanReviewWorkspace,
    PresentationPolicy,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ReviewItemStatus,
    ViewKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    M2005AuthorizationError,
    M2005Plugin,
    M2005ReplayError,
    M2005Service,
    WorkflowPresentationSubmission,
    cli_app,
    create_app,
    preflight_m2005_authorization,
    present_protein_subtype_human_review_workspace,
)
from tests.contract.test_m20_05_adversarial import _item

_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_preflight_rejects_non_mapping_and_missing_controls() -> None:
    with pytest.raises(M2005AuthorizationError):
        preflight_m2005_authorization(object())
    with pytest.raises(M2005AuthorizationError):
        preflight_m2005_authorization({"context": {"references": {}}})

    class ExplodingContext:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(M2005AuthorizationError):
        preflight_m2005_authorization(ExplodingContext())


def test_policy_rejects_duplicate_and_incomplete_required_views() -> None:
    policy = build_request().policy
    base = policy.model_dump(mode="python", exclude={"required_views"})
    with pytest.raises(ValidationError, match="unique"):
        PresentationPolicy(
            **base,
            required_views=(ViewKind.TASK_SUMMARY, ViewKind.TASK_SUMMARY),
        )
    with pytest.raises(ValidationError, match="every safety-critical"):
        PresentationPolicy(**base, required_views=(ViewKind.TASK_SUMMARY,))


def test_request_rejects_wrong_upstream_media_duplicate_items_and_positions() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["aligned_evidence_bundle"] = request.aligned_evidence_bundle.model_copy(
        update={"media_type": "application/json"}
    )
    with pytest.raises(ValidationError, match="provisional M20-04"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest(**cast("Any", payload))
    payload = request.model_dump(mode="python")
    payload["review_items"] = (request.review_items[0], *request.review_items)
    with pytest.raises(ValidationError, match="item ids"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest(**cast("Any", payload))
    payload = request.model_dump(mode="python")
    payload["review_items"] = tuple(
        item.model_copy(update={"position": item.position + 1}) for item in request.review_items
    )
    with pytest.raises(ValidationError, match="positions"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest(**cast("Any", payload))


def test_review_workspace_rejects_duplicate_ids_and_noncontiguous_positions() -> None:
    request = build_request()
    with pytest.raises(ValidationError, match="item ids"):
        HumanReviewWorkspace(
            workspace_id="workspace.bad-ids",
            version="1.0.0",
            items=(request.review_items[0], request.review_items[0]),
            ordering=request.policy.default_ordering,
            automation_bias_warning="Review all evidence before use.",
            source_bundle=request.aligned_evidence_bundle,
            evidence=request.review_items[0].evidence,
        )
    with pytest.raises(ValidationError, match="contiguous"):
        HumanReviewWorkspace(
            workspace_id="workspace.bad-positions",
            version="1.0.0",
            items=tuple(
                item.model_copy(update={"position": item.position + 1})
                for item in request.review_items
            ),
            ordering=request.policy.default_ordering,
            automation_bias_warning="Review all evidence before use.",
            source_bundle=request.aligned_evidence_bundle,
            evidence=request.review_items[0].evidence,
        )


def test_abstained_item_requires_explicit_escalation() -> None:
    request = build_request()
    bad = _item(ViewKind.TASK_SUMMARY, 0, status=ReviewItemStatus.ABSTAINED).model_copy(
        update={"discrepancy_ids": (), "next_action": None}
    )
    payload = request.model_dump(mode="python")
    payload["review_items"] = (bad, *request.review_items[1:])
    with pytest.raises(ValidationError, match="review escalation"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest(**cast("Any", payload))


def test_service_denies_unsafe_context_and_replay_tampering() -> None:
    service = M2005Service()
    with pytest.raises(M2005AuthorizationError):
        service.present(denied_request())
    result = service.present(build_request())
    with pytest.raises(M2005ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "e" * 64}))
    with pytest.raises(M2005ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))


def test_api_sanitizes_non_object_unknown_schema_and_denial() -> None:
    client = TestClient(create_app(M2005Service()))
    assert client.post("/v1/modules/M20-05/verify", content=b"[").status_code == _HTTP_UNPROCESSABLE
    assert (
        client.post("/v1/modules/M20-05/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    assert client.get("/v1/modules/M20-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    denied = denied_request().model_dump(mode="json")
    response = client.post("/v1/modules/M20-05/validate", json=denied)
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_sanitizes_bad_inputs_and_refuses_overwrite(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["present", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    output_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            cli_app, ["present", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app, ["present", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )


def test_plugin_rejects_bad_submission_and_json() -> None:
    plugin = M2005Plugin(M2005Service())
    with pytest.raises(TypeError, match="workflow presentation submission"):
        plugin.validate(build_request())
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(WorkflowPresentationSubmission(request=b"[]"))


def test_plugin_rejects_forged_cross_instance_and_nested_mutated_tokens() -> None:
    typed = build_request()
    plugin = M2005Plugin(M2005Service())
    other = M2005Plugin(M2005Service())
    token = plugin.validate(WorkflowPresentationSubmission(typed))
    forged = type(token)(request=token.request, _seal=object())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        other.run(token)

    changed_item = token.request.review_items[0].model_copy(
        update={"title": "forged review item"}
    )
    object.__setattr__(
        token.request,
        "review_items",
        (changed_item, *token.request.review_items[1:]),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_public_wrapper_plugin_replay_and_evaluator_entrypoints(capsys: Any) -> None:
    request = build_request()
    result = present_protein_subtype_human_review_workspace(request)
    plugin = M2005Plugin(M2005Service())
    assert plugin.replay(result).result_digest == result.result_digest
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(0)
    benchmark = run_benchmark(1)
    assert benchmark["passed"] is True
    benchmark_main()
    evaluator = run_evaluator()
    assert evaluator["passed"] == evaluator["scenario_count"]
    evaluator_main()
    assert "M20-05" in capsys.readouterr().out
