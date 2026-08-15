"""Adversarial runtime and adapter coverage for M10-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m10_05.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1005 import create_m1005_app, m1005_app
from glio_proteogen.contracts.m10_05 import (
    ConstraintEvaluationOutcome,
    ConstraintHardness,
    ConstraintKind,
    MechanismConstraint,
    canonical_request_digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator import (  # noqa: E501
    M1005ConstraintAuthorizationError,
    M1005Plugin,
    M1005ReplayVerificationError,
    M1005Service,
)

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_FORBIDDEN = 403


def test_integrator_reports_soft_conflict_and_ablation() -> None:
    result = M1005Service().execute(build_request(soft_expression="always_false"))
    assert result.status.value == "integrated"
    assert result.evaluations[1].outcome is ConstraintEvaluationOutcome.VIOLATED
    assert result.ablations[0].effect_delta == 0.0
    assert result.human_review_required is True
    assert result.emits_parent is False


@pytest.mark.parametrize("expression", ["always_false", "x < 0"])
def test_hard_constraint_violation_abstains(expression: str) -> None:
    result = M1005Service().execute(build_request(hard_expression=expression))
    assert result.status.value == "abstained"
    assert result.estimates == ()
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True


def test_unknown_constraint_language_abstains_without_heuristics() -> None:
    result = M1005Service().execute(build_request(hard_expression="pathway_score > threshold"))
    assert result.status.value == "abstained"
    assert {item.outcome for item in result.evaluations} == {
        ConstraintEvaluationOutcome.NOT_EVALUABLE,
        ConstraintEvaluationOutcome.SATISFIED,
    }
    assert result.support_decision.status.value == "unsupported"


@pytest.mark.parametrize("field", ["approved_configuration", "identity_lineage", "consent"])
def test_control_preflight_fails_before_constraint_traversal(field: str) -> None:
    request = build_request()
    refs = request.context.references
    changed = getattr(refs, field).model_copy(update={"state": "unknown"})
    blocked_refs = refs.model_copy(update={field: changed})
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": blocked_refs})}
    )
    with pytest.raises(M1005ConstraintAuthorizationError):
        M1005Service().execute(blocked)


def test_plugin_accepts_json_once_and_rejects_copied_token() -> None:
    plugin = M1005Plugin(M1005Service())
    token = plugin.validate(build_request().model_dump_json())
    result = plugin.run(token)
    assert result.request_digest == canonical_request_digest(build_request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token.__class__(request=token.request, _seal=object()))


def test_plugin_rejects_mutated_issued_request() -> None:
    plugin = M1005Plugin(M1005Service())
    token = plugin.validate(build_request())
    object.__setattr__(token.request, "request_id", "request.mutated")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_replay_rejects_every_derived_region_mutation() -> None:
    service = M1005Service()
    result = service.execute(build_request())
    for update in (
        {"result_id": "result.forged"},
        {"evaluations": ()},
        {"limitations": ()},
        {"human_review_required": not result.human_review_required},
    ):
        with pytest.raises((M1005ReplayVerificationError, ValueError)):
            service.verify(result.model_copy(update=update))


def test_verify_without_replay_still_validates_digest() -> None:
    service = M1005Service()
    result = service.execute(build_request())
    assert service.verify(result, replay=False).model_dump() == result.model_dump()
    with pytest.raises((M1005ReplayVerificationError, ValueError)):
        service.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)


def test_duplicate_json_keys_are_rejected_before_validation() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads('{"request_id":"a","request_id":"b"}')


def test_api_schema_validate_integrate_and_verify_parity() -> None:
    client = TestClient(create_m1005_app())
    request = build_request()
    payload = request.model_dump_json()
    schema = client.get("/v1/m10-05/schema/request")
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    validated = client.post("/v1/m10-05/validate", content=payload)
    assert validated.status_code == HTTP_OK
    assert validated.json()["valid"] is True
    executed = client.post("/v1/m10-05/integrate", content=payload)
    assert executed.status_code == HTTP_OK
    verified = client.post("/v1/m10-05/verify", content=executed.content)
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True


def test_api_denies_unaccepted_controls() -> None:
    client = TestClient(create_m1005_app())
    request = build_request(unknown_controls=True)
    response = client.post("/v1/m10-05/integrate", content=request.model_dump_json())
    assert response.status_code == HTTP_FORBIDDEN
    assert "controls" in response.json()["detail"]


def test_cli_validate_integrate_and_export_schema(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    validated = runner.invoke(m1005_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    integrated = runner.invoke(m1005_app, ["integrate", str(request_path)])
    assert integrated.exit_code == 0
    output_path.write_text(integrated.stdout, encoding="utf-8")
    verified = runner.invoke(m1005_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
    schema = runner.invoke(m1005_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$id"].endswith(":output")


def test_constraint_contract_rejects_duplicate_features_and_bad_soft_weight() -> None:
    with pytest.raises(ValueError, match="feature ids must be unique"):
        MechanismConstraint(
            constraint_id="constraint.duplicate",
            kind=ConstraintKind.GRAPH,
            hardness=ConstraintHardness.SOFT,
            expression="always_true",
            feature_ids=("feature.x", "feature.x"),
            weight=0.5,
        )
    with pytest.raises(ValueError, match="soft constraints require"):
        MechanismConstraint(
            constraint_id="constraint.no-weight",
            kind=ConstraintKind.GRAPH,
            hardness=ConstraintHardness.SOFT,
            expression="always_true",
            feature_ids=("feature.x",),
        )


def test_service_result_is_deterministic() -> None:
    service = M1005Service()
    first = service.execute(build_request(soft_expression="always_false"))
    second = service.execute(build_request(soft_expression="always_false"))
    assert first.model_dump_json() == second.model_dump_json()
    assert first.result_digest == second.result_digest
