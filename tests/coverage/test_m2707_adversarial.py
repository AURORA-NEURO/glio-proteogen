"""Adversarial M27-07 authorization, replay, and boundary tests."""

# ruff: noqa: PLR2004, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from evals.m27_07.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_07 import (
    ApprovedChangePackage,
    ChampionChallengerComparison,
    ComparisonStatus,
    ControlComplexActivityChangeRequest,
    MetricComparison,
    PromotionState,
    RevalidationPlan,
    contract_json_schemas,
)
from glio_proteogen.contracts.m27_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import (
    ChangeControlSubmission,
    M2707Plugin,
    M2707Service,
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.cli import cli
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.engine import (
    ChangeControlAuthorizationError,
    M2707ChangeControlEngine,
)


def test_schema_metadata_is_closed() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 8
    assert all(
        cast("dict[str, object]", schema["x-glio-contract"])["provisionalAbi"] is True
        for schema in schemas.values()
    )


def test_unsupported_upstream_abstains_before_execution() -> None:
    request = build_request()
    object.__setattr__(request.upstream_result, "media_type", "application/json")
    with pytest.raises(ValueError, match="request must bind"):
        type(request).model_validate(request.model_dump(mode="python"), strict=True)


def test_consent_withheld_is_denied() -> None:
    with pytest.raises(ChangeControlAuthorizationError):
        M2707ChangeControlEngine().evaluate(build_request(consent=ConsentState.WITHHELD))


def test_context_identity_mismatch_is_denied() -> None:
    request = build_request()
    object.__setattr__(request.context, "request_id", "m2707.request.other")
    with pytest.raises(ChangeControlAuthorizationError):
        M2707ChangeControlEngine().evaluate(request)


def test_rejected_control_is_denied() -> None:
    request = build_request()
    object.__setattr__(request.context.references.quality, "state", "rejected")
    with pytest.raises(ChangeControlAuthorizationError):
        M2707ChangeControlEngine().evaluate(request)


def test_duplicate_source_artifacts_are_denied() -> None:
    request = build_request()
    object.__setattr__(request, "source_artifacts", (request.source_artifacts[0],) * 2)
    with pytest.raises(ChangeControlAuthorizationError):
        M2707ChangeControlEngine().evaluate(request)


def test_source_artifacts_bind_upstream_and_nested_evidence_exactly() -> None:
    request = build_request()
    missing_upstream = tuple(
        artifact
        for artifact in request.source_artifacts
        if artifact.artifact_id != request.upstream_result.artifact_id
    )
    forged_rollback = request.source_artifacts[3].model_copy(
        update={"digest": "sha256:" + "f" * 64}
    )

    with pytest.raises(ValueError, match="bind upstream"):
        ControlComplexActivityChangeRequest.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": missing_upstream}
        )
    with pytest.raises(ValueError, match="bind upstream"):
        ControlComplexActivityChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "source_artifacts": (
                    *request.source_artifacts[:3],
                    forged_rollback,
                    *request.source_artifacts[4:],
                )
            }
        )

    object.__setattr__(request, "source_artifacts", missing_upstream)
    with pytest.raises(ChangeControlAuthorizationError, match="bind upstream"):
        M2707ChangeControlEngine().evaluate(request)


def test_source_manifest_binds_champion_and_challenger_digests() -> None:
    request = build_request()
    unbound = tuple(
        artifact
        for artifact in request.source_artifacts
        if artifact.digest not in {request.champion_digest, request.challenger_digest}
    )
    object.__setattr__(request, "source_artifacts", unbound)

    with pytest.raises(ChangeControlAuthorizationError, match="champion/challenger"):
        M2707ChangeControlEngine().evaluate(request)


def test_identity_unresolved_is_denied() -> None:
    request = build_request()
    object.__setattr__(
        request.context.references.identity_lineage, "state", IdentityLineageState.UNRESOLVED
    )
    with pytest.raises(ChangeControlAuthorizationError):
        M2707ChangeControlEngine().evaluate(request)


def test_plugin_rejects_copied_token() -> None:
    plugin = M2707Plugin()
    token = plugin.validate(ChangeControlSubmission(build_request()))
    with pytest.raises(ValueError, match="capability"):
        plugin.run(type(token)(request=token.request, request_digest=token.request_digest))


def test_plugin_rejects_mutated_request() -> None:
    plugin = M2707Plugin()
    request = build_request()
    token = plugin.validate(ChangeControlSubmission(request))
    object.__setattr__(request, "request_id", "m2707.request.mutated")
    with pytest.raises(ValueError, match="capability"):
        plugin.run(token)


def test_service_rejects_oversized_json() -> None:
    with pytest.raises(ValueError, match="validation failed"):
        M2707Service().validate_request(b"{" + b"a" * (4 * 1024 * 1024) + b"}")


def test_service_rejects_unknown_outer_field() -> None:
    payload = build_request().model_dump(mode="json")
    payload["unknown_field"] = True
    with pytest.raises(ValueError, match="validation failed"):
        M2707Service().validate_request(json.dumps(payload))


def test_service_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="validation failed"):
        M2707Service().validate_request(b"not-json")


def test_strict_parse_once_rejects_duplicate_and_nonfinite_json() -> None:
    request_json = build_request().model_dump_json()
    duplicate = request_json.replace(
        '"request_id":"m2707.request.default"',
        '"request_id":"m2707.request.default","request_id":"m2707.request.default"',
        1,
    )
    with pytest.raises(ValueError, match="validation failed"):
        M2707Service().validate_request(duplicate)
    nonfinite = request_json.replace(
        '"champion_digest":', '"champion_value":NaN,"champion_digest":', 1
    )
    with pytest.raises(ValueError, match="validation failed"):
        M2707Service().validate_request(nonfinite)


def test_result_replay_detects_forged_digest() -> None:
    service = M2707Service()
    result = service.execute(build_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    assert service.verify(forged) is False


def test_result_replay_detects_forged_status() -> None:
    service = M2707Service()
    result = service.execute(build_request())
    forged = result.model_copy(update={"human_review_required": True})
    assert service.verify(forged) is False


def test_result_rejects_self_rehashed_package_control_mutations() -> None:
    result = M2707Service().execute(build_request())
    assert result.approved_change_package is not None
    forged_package = result.approved_change_package.model_copy(
        update={
            "rollback_point": result.approved_change_package.rollback_point.model_copy(
                update={"rollback_reason": "forged rollback instruction"}
            )
        }
    )
    forged = result.model_copy(update={"approved_change_package": forged_package})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request change controls"):
        type(result).model_validate(forged.model_dump(mode="python"), strict=True)


def test_result_rejects_self_rehashed_package_identity_mutation() -> None:
    result = M2707Service().execute(build_request())
    assert result.approved_change_package is not None
    forged_package = result.approved_change_package.model_copy(
        update={"package_digest": "sha256:" + "f" * 64}
    )
    forged = result.model_copy(update={"approved_change_package": forged_package})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="package identity"):
        type(result).model_validate(forged.model_dump(mode="python"), strict=True)


def test_api_rejects_non_object_payload() -> None:
    response = TestClient(create_app()).post("/v1/modules/M27-07/validate", content=b"[]")
    assert response.status_code == 422


def test_api_rejects_unknown_schema() -> None:
    response = TestClient(create_app()).get("/v1/contracts/M27-07/unknown/schema")
    assert response.status_code == 404


def test_api_named_schema_and_parse_errors() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/contracts/M27-07/request/schema").status_code == 200
    assert client.post("/v1/modules/M27-07/validate", content=b"not-json").status_code == 422
    assert client.post("/v1/modules/M27-07/verify", content=b"not-json").status_code == 422


def test_api_strict_parser_rejects_duplicate_and_oversized_payloads() -> None:
    client = TestClient(create_app())
    request_json = build_request().model_dump_json()
    duplicate = request_json.replace(
        '"request_id":"m2707.request.default"',
        '"request_id":"m2707.request.default","request_id":"m2707.request.default"',
        1,
    ).encode()
    assert client.post("/v1/modules/M27-07/validate", content=duplicate).status_code == 422
    oversized = b"{" + b" " * (4 * 1024 * 1024) + b"}"
    assert client.post("/v1/modules/M27-07/validate", content=oversized).status_code == 422


def test_api_sanitizes_invalid_control() -> None:
    payload = build_request().model_dump(mode="json")
    payload["upstream_result"]["media_type"] = "application/json"
    response = TestClient(create_app()).post("/v1/modules/M27-07/control", json=payload)
    assert response.status_code == 422
    assert "request must bind" not in response.text


def test_api_control_sanitizes_execution_denial() -> None:
    payload = build_request().model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    response = TestClient(create_app()).post("/v1/modules/M27-07/control", json=payload)
    assert response.status_code == 422


def test_comparison_requires_distinct_digests() -> None:
    request = build_request()
    with pytest.raises(ValueError, match="distinct"):
        ChampionChallengerComparison(
            comparison_id="m2707.comparison.same",
            champion_digest=request.champion_digest,
            challenger_digest=request.champion_digest,
            status=ComparisonStatus.PASSED,
            metrics=(
                MetricComparison(
                    metric="m",
                    champion_value=1.0,
                    challenger_value=1.0,
                    tolerance=0.1,
                    within_tolerance=True,
                ),
            ),
            evidence=(request.classification.evidence[0],),
        )


def test_approved_package_has_no_biology_authority() -> None:
    result = M2707Service().execute(build_request())
    assert result.parent_target == "complex activity"
    assert result.emits_parent is False
    assert all(
        "biology" in item.statement or "caller" in item.statement or "provisional" in item.statement
        for item in result.limitations
    )


def test_cli_exports_validates_controls_and_verifies(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(cli, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(cli, ["control", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )
    assert runner.invoke(cli, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(cli, ["control", str(request_path), "--output", str(result_path)]).exit_code
        != 0
    )


def test_cli_strict_parser_rejects_duplicate_request(tmp_path: Path) -> None:
    request_path = tmp_path / "duplicate.json"
    request_json = build_request().model_dump_json()
    request_path.write_text(
        request_json.replace(
            '"request_id":"m2707.request.default"',
            '"request_id":"m2707.request.default","request_id":"m2707.request.default"',
            1,
        ),
        encoding="utf-8",
    )
    assert CliRunner().invoke(cli, ["validate", str(request_path)]).exit_code != 0


def test_cli_error_and_unknown_schema_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    missing = tmp_path / "missing.json"
    assert runner.invoke(cli, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli, ["validate", str(missing)]).exit_code != 0
    assert runner.invoke(cli, ["control", str(missing)]).exit_code != 0
    assert runner.invoke(cli, ["verify", str(missing)]).exit_code != 0


def test_canonical_dict_projection_is_deterministic() -> None:
    request = build_request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )


def test_revalidation_plan_rejects_missing_check() -> None:
    request = build_request()
    with pytest.raises(ValueError, match="required"):
        RevalidationPlan(
            plan_id="m2707.plan.bad",
            version="1.0.0",
            required_checks=("schema",),
            completed_checks=("security",),
            validation_digest=request.revalidation.validation_digest,
            evidence=request.revalidation.evidence,
        )


def test_approved_package_rejects_failed_comparison() -> None:
    request = build_request()
    comparison = ChampionChallengerComparison(
        comparison_id="m2707.comparison.failed",
        champion_digest=request.champion_digest,
        challenger_digest=request.challenger_digest,
        status=ComparisonStatus.FAILED,
        metrics=(
            MetricComparison(
                metric="m",
                champion_value=1.0,
                challenger_value=2.0,
                tolerance=0.1,
                within_tolerance=False,
            ),
        ),
        evidence=(request.classification.evidence[0],),
    )
    with pytest.raises(ValueError, match="passing"):
        ApprovedChangePackage(
            package_id="m2707.package.bad",
            version="1.0.0",
            classification=request.classification,
            revalidation=request.revalidation,
            comparison=comparison,
            approval_reference="m2707.approval",
            promotion_state=PromotionState.APPROVED,
            rollback_point=request.rollback_point,
            package_digest=request.champion_digest,
            evidence=request.classification.evidence,
        )
