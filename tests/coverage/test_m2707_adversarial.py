"""Adversarial M27-07 authorization, replay, and boundary tests."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from typing import cast

import pytest
from evals.m27_07.fixture import build_request
from fastapi.testclient import TestClient

from glio_proteogen.contracts.m27_07 import (
    ChampionChallengerComparison,
    ComparisonStatus,
    MetricComparison,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import (
    ChangeControlSubmission,
    M2707Plugin,
    M2707Service,
    create_app,
)
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


def test_api_rejects_non_object_payload() -> None:
    response = TestClient(create_app()).post("/v1/modules/M27-07/validate", content=b"[]")
    assert response.status_code == 422


def test_api_rejects_unknown_schema() -> None:
    response = TestClient(create_app()).get("/v1/contracts/M27-07/unknown/schema")
    assert response.status_code == 404


def test_api_sanitizes_invalid_control() -> None:
    payload = build_request().model_dump(mode="json")
    payload["upstream_result"]["media_type"] = "application/json"
    response = TestClient(create_app()).post("/v1/modules/M27-07/control", json=payload)
    assert response.status_code == 422
    assert "request must bind" not in response.text


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
