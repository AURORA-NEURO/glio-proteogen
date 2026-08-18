"""Deep contract, runtime, interface, and safety matrix for M13-05."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1305 import app, m1305_app
from glio_proteogen.contracts.m13_05 import (
    M1305_M1304_RESULT_MEDIA_TYPE,
    ChangePoint,
    ChangePointStatus,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelProteotypeLongitudinalEvolutionRequest,
    ProteotypeLongitudinalEvolutionResult,
    TrajectoryDimension,
    TrajectoryPolicy,
    canonical_request_digest,
    expected_uncertainty,
)
from glio_proteogen.contracts.m13_05.canonical import result_payload_digest
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
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c13_variant_peptide.m13_05_longitudinal_evolution import (
    M1305AuthorizationError,
    M1305InferenceError,
    M1305LongitudinalEngine,
    M1305Plugin,
    M1305ReplayVerificationError,
    M1305Service,
    ValidatedM1305Request,
)
from glio_proteogen.modules.c13_variant_peptide.m13_05_longitudinal_evolution.engine import (
    _label_for,
    preflight_longitudinal_authorization,
)

_BASELINE_OBSERVATIONS = 2
_EXPECTED_OBSERVATIONS = 3
_CLI_SCHEMA_ERROR = 2
_CLI_SUCCESS = 0


def _digest(index: int) -> str:
    return "sha256:" + f"{index:064x}"


def _artifact(index: int, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact-{index}",
        version="1.0.0",
        digest=_digest(index),
        media_type=media_type,
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    decision_state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    return ExecutionContext(
        request_id="context-request",
        actor_id="actor-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config-decision",
                state=decision_state,
                policy_version="1.0.0",
                evidence=_artifact(10),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.RESOLVED
                if accepted
                else IdentityLineageState.UNRESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest(11),
                evidence=_artifact(11),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-decision",
                state=decision_state,
                policy_version="1.0.0",
                evidence=_artifact(12),
            ),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED if accepted else ConsentState.WITHHELD,
                policy_version="1.0.0",
                evidence=_artifact(13),
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-decision",
                state=decision_state,
                policy_version="1.0.0",
                evidence=_artifact(14),
            ),
            support=UpstreamDecisionReference(
                decision_id="support-decision",
                state=decision_state,
                policy_version="1.0.0",
                evidence=_artifact(15),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-decision",
                state=decision_state,
                policy_version="1.0.0",
                evidence=_artifact(16),
            ),
        ),
    )


def _request(
    objective: str = "stable",
    *,
    accepted: bool = True,
    count: int = 3,
) -> ModelProteotypeLongitudinalEvolutionRequest:
    configuration = EvolutionModelConfiguration(
        configuration_id="configuration-1",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective=objective,
        model_reference=_artifact(20, "application/vnd.model+json"),
    )
    policy = TrajectoryPolicy(
        dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TERRITORY),
        minimum_observations=2,
        configuration=configuration,
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    observations = tuple(
        {
            "observation_id": f"observation-{index}",
            "sequence": index,
            "observed_at": start + timedelta(days=index),
            "territory": "primary" if index == 0 else "recurrence",
            "treatment_era": ("baseline" if index < _BASELINE_OBSERVATIONS else "post-treatment"),
            "feature_artifact": _artifact(100 + index),
        }
        for index in range(count)
    )
    return ModelProteotypeLongitudinalEvolutionRequest(
        request_id="request-1",
        context=_context(accepted=accepted),
        network_state_result=_artifact(30, M1305_M1304_RESULT_MEDIA_TYPE),
        policy=policy,
        observations=observations,
        source_artifacts=(_artifact(40),),
    )


def test_supported_trajectory_and_replay_are_deterministic() -> None:
    request = _request("change_point:2:early:late")
    engine = M1305LongitudinalEngine()
    result = engine.infer(request)
    assert result.status.value == "modeled"
    assert result.parent_target == "proteotype"
    assert result.trajectory[0].label == "early"
    assert result.trajectory[-1].label == "late"
    assert result.change_points[0].status is ChangePointStatus.DETECTED
    assert result.request_digest == canonical_request_digest(request)
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


@pytest.mark.parametrize(
    "objective", ["stable", "territory", "treatment_era", "clone", "state_transition"]
)
def test_supported_objective_families(objective: str) -> None:
    result = M1305LongitudinalEngine().infer(_request(objective))
    assert result.status.value == "modeled"
    assert len(result.trajectory) == _EXPECTED_OBSERVATIONS


def test_unsupported_objective_abstains_without_negative_finding() -> None:
    result = M1305LongitudinalEngine().infer(_request("unapproved-opaque-model"))
    assert result.status.value == "not_evaluable"
    assert result.trajectory == ()
    assert result.change_points == ()
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True


def test_change_point_outside_history_abstains() -> None:
    result = M1305LongitudinalEngine().infer(_request("change_point:9:early:late"))
    assert result.status.value == "not_evaluable"
    assert "outside" in (result.abstention_reason or "")


def test_controls_are_checked_before_execution() -> None:
    with pytest.raises(M1305AuthorizationError):
        M1305LongitudinalEngine().infer(_request(accepted=False))
    with pytest.raises(M1305AuthorizationError):
        M1305Service.validate_request(_request(accepted=False).model_dump(mode="json"))


def test_tampered_result_fails_replay() -> None:
    engine = M1305LongitudinalEngine()
    result = engine.infer(_request())
    tampered = result.model_copy(update={"result_id": "result.tampered"})
    with pytest.raises(M1305ReplayVerificationError):
        engine.verify(tampered)


def test_plugin_is_strict_parse_once_and_token_bound() -> None:
    request = _request()
    plugin = M1305Plugin(M1305Service())
    token = plugin.validate(json.dumps(request.model_dump(mode="json")))
    result = plugin.run(token)
    assert result.status.value == "modeled"
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(StrictJsonError):
        plugin.validate('{"request_id":"x","duplicate":1,"duplicate":2}')


def test_fastapi_validate_schema_infer_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request_json = _request().model_dump(mode="json")
    schema_response = client.get("/v1/m13-05/schema/request")
    assert schema_response.status_code == HTTPStatus.OK
    assert schema_response.json()["x-glio-contract"]["provisionalAbi"] is True
    inferred = client.post("/v1/modules/M13-05/longitudinal", json=request_json)
    assert inferred.status_code == HTTPStatus.OK
    assert inferred.json()["output_type"] == "proteotype_longitudinal_evolution"
    verified = client.post("/v1/modules/M13-05/verify", json=inferred.json())
    assert verified.status_code == HTTPStatus.OK
    unauthorized = client.post(
        "/v1/modules/M13-05/longitudinal", json=_request(accepted=False).model_dump(mode="json")
    )
    assert unauthorized.status_code == HTTPStatus.FORBIDDEN
    malformed = client.post("/v1/modules/M13-05/longitudinal", json={"request_id": "bad"})
    assert malformed.status_code in {HTTPStatus.FORBIDDEN, HTTPStatus.UNPROCESSABLE_ENTITY}
    assert "traceback" not in malformed.text.lower()


def test_fastapi_content_type_and_schema_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m13-05/schema/not-a-schema").status_code == HTTPStatus.NOT_FOUND
    assert (
        client.post(
            "/v1/modules/M13-05/longitudinal",
            content="{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    )


def test_typer_schema_infer_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    schema = runner.invoke(m1305_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    inferred = runner.invoke(m1305_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    verified = runner.invoke(m1305_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert "proteotype_longitudinal_evolution" in verified.stdout


def test_request_rejects_wrong_upstream_media_type() -> None:
    payload = _request().model_dump(mode="json")
    payload["network_state_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M13-04"):
        ModelProteotypeLongitudinalEvolutionRequest.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_contract_rejects_duplicate_dimensions_and_invalid_change_point_shapes() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        TrajectoryPolicy(
            dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TIME_COURSE),
            minimum_observations=2,
            configuration=_request().policy.configuration,
        )
    with pytest.raises(ValueError, match="detected change point"):
        ChangePoint(
            change_point_id="change-point-1",
            sequence=1,
            status=ChangePointStatus.DETECTED,
            rationale="missing evidence and state links",
        )
    with pytest.raises(ValueError, match="non-detected"):
        ChangePoint(
            change_point_id="change-point-2",
            sequence=1,
            status=ChangePointStatus.NOT_DETECTED,
            before_state_id="state-a",
            rationale="not detected",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("duplicate_ids", "identifiers"),
        ("unordered_sequences", "ordered by sequence"),
        ("unordered_times", "ordered by observed_at"),
        ("short_history", "minimum"),
    ],
)
def test_contract_rejects_temporal_request_violations(field: str, message: str) -> None:
    payload = _request().model_dump(mode="json")
    if field == "duplicate_ids":
        payload["observations"][1]["observation_id"] = payload["observations"][0]["observation_id"]
    elif field == "unordered_sequences":
        payload["observations"][1]["sequence"] = 0
    elif field == "unordered_times":
        payload["observations"][1]["observed_at"] = payload["observations"][0]["observed_at"]
    else:
        payload["policy"]["minimum_observations"] = 4
    with pytest.raises(ValueError, match=message):
        ModelProteotypeLongitudinalEvolutionRequest.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_objective_parser_and_label_fallbacks() -> None:
    engine = M1305LongitudinalEngine()
    assert engine.infer(_request("trajectory:stable")).status.value == "modeled"
    assert (
        engine.infer(_request("change_point:not-an-int:before:after")).status.value
        == "not_evaluable"
    )
    assert engine.infer(_request("change_point:0:before:after")).status.value == "not_evaluable"
    assert _label_for("time_course", _request().observations[0], 0) == "time_course"
    with pytest.raises(M1305InferenceError):
        _label_for("change_point", _request().observations[0], 0)
    with pytest.raises(M1305AuthorizationError):
        preflight_longitudinal_authorization({})


def test_engine_and_service_error_replay_paths() -> None:
    engine = M1305LongitudinalEngine()
    service = M1305Service(engine)
    request = _request()
    result = service.execute(request)
    assert service.verify(result, replay=False).result_id == result.result_id
    with pytest.raises(M1305ReplayVerificationError):
        engine.verify(object())
    with pytest.raises(M1305ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(TypeError):
        M1305Plugin(service).run(ValidatedM1305Request(request=request, _seal=object()))
    assert expected_uncertainty(supported=False).support.state.value == "not_estimable"


def _valid_result_payload(result: object, *, request: object | None = None) -> dict[str, object]:
    payload = result.model_dump(mode="json")  # type: ignore[union-attr]
    if request is not None:
        payload["request"] = request.model_dump(mode="json")  # type: ignore[union-attr]
        request_digest = canonical_request_digest(request)  # type: ignore[arg-type]
        payload["request_digest"] = request_digest
        payload["result_id"] = f"result.{request_digest.removeprefix('sha256:')}"
    payload["result_digest"] = "sha256:" + "0" * 64
    constructed = ProteotypeLongitudinalEvolutionResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(constructed)
    return payload


def test_result_contract_closes_identifiers_ordering_and_references() -> None:
    result = M1305LongitudinalEngine().infer(_request())
    payload = _valid_result_payload(result)
    for field, value, message in (
        ("request_digest", "sha256:" + "f" * 64, "request digest"),
        ("result_id", "result.wrong", "identifier"),
    ):
        broken = dict(payload)
        broken[field] = value
        with pytest.raises(ValueError, match=message):
            ProteotypeLongitudinalEvolutionResult.model_validate_json(
                json.dumps(broken), strict=True
            )
    broken = dict(payload)
    broken["evidence"] = []
    with pytest.raises(ValueError, match="evidence"):
        ProteotypeLongitudinalEvolutionResult.model_validate_json(json.dumps(broken), strict=True)
    broken = dict(payload)
    broken["trajectory"] = [*payload["trajectory"]]
    broken["trajectory"][1]["state_id"] = broken["trajectory"][0]["state_id"]
    with pytest.raises(ValueError, match="state identifiers"):
        ProteotypeLongitudinalEvolutionResult.model_validate_json(json.dumps(broken), strict=True)


def test_result_contract_rejects_unsafe_abstention_and_change_point_links() -> None:
    engine = M1305LongitudinalEngine()
    modeled = engine.infer(_request())
    payload = _valid_result_payload(modeled)
    broken = dict(payload)
    broken["trajectory"] = []
    with pytest.raises(ValueError, match="modeled result"):
        ProteotypeLongitudinalEvolutionResult.model_validate_json(json.dumps(broken), strict=True)
    abstained = engine.infer(_request("unknown:model"))
    abstained_payload = _valid_result_payload(abstained)
    abstained_payload["trajectory"] = [modeled.model_dump(mode="json")["trajectory"][0]]
    with pytest.raises(ValueError, match="abstained result"):
        ProteotypeLongitudinalEvolutionResult.model_validate_json(
            json.dumps(abstained_payload), strict=True
        )
    change = engine.infer(_request("change_point:2:before:after"))
    change_payload = _valid_result_payload(change)
    change_payload["change_points"][0]["before_state_id"] = "state.missing"
    with pytest.raises(ValueError, match="reference trajectory"):
        ProteotypeLongitudinalEvolutionResult.model_validate_json(
            json.dumps(change_payload), strict=True
        )


def test_replay_detects_denied_controls_and_semantic_tamper() -> None:
    engine = M1305LongitudinalEngine()
    result = engine.infer(_request())
    denied_result = _valid_result_payload(result, request=_request(accepted=False))
    with pytest.raises(M1305ReplayVerificationError):
        engine.verify(
            ProteotypeLongitudinalEvolutionResult.model_validate_json(
                json.dumps(denied_result), strict=True
            )
        )
    changed = _valid_result_payload(result)
    changed["trajectory"][0]["label"] = "tampered"
    changed["result_digest"] = "sha256:" + "0" * 64
    changed_constructed = ProteotypeLongitudinalEvolutionResult.model_construct(**changed)
    changed["result_digest"] = result_payload_digest(changed_constructed)
    with pytest.raises(M1305ReplayVerificationError):
        engine.verify(
            ProteotypeLongitudinalEvolutionResult.model_validate_json(
                json.dumps(changed), strict=True
            )
        )


def test_plugin_descriptor_object_validation_and_verify() -> None:
    plugin = M1305Plugin(M1305Service())
    request = _request()
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-05"
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.verify(result).result_id == result.result_id


def test_fastapi_strict_json_validation_and_verify_failures() -> None:
    client = TestClient(app)
    malformed = client.post(
        "/v1/modules/M13-05/longitudinal",
        content="{not-json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    incomplete = _request().model_dump(mode="json")
    incomplete.pop("policy")
    invalid = client.post("/v1/modules/M13-05/longitudinal", json=incomplete)
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (
        client.post(
            "/v1/modules/M13-05/verify",
            content="{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    )
    invalid_result = client.post(
        "/v1/modules/M13-05/verify",
        content="{not-json",
        headers={"content-type": "application/json"},
    )
    assert invalid_result.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_typer_error_surfaces_and_stdout(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    unknown = runner.invoke(m1305_app, ["export-schema", "nope"])
    assert unknown.exit_code == _CLI_SCHEMA_ERROR
    stdout_result = runner.invoke(m1305_app, ["infer", str(request_path)])
    assert stdout_result.exit_code == _CLI_SUCCESS
    output = tmp_path / "result.json"
    output.write_text("existing", encoding="utf-8")
    already_exists = runner.invoke(m1305_app, ["infer", str(request_path), "--output", str(output)])
    assert already_exists.exit_code != 0
    invalid_request = tmp_path / "invalid.json"
    invalid_request.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(m1305_app, ["infer", str(invalid_request)])
    assert invalid.exit_code != 0
    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("{}", encoding="utf-8")
    failed_verify = runner.invoke(m1305_app, ["verify", str(invalid_result)])
    assert failed_verify.exit_code != 0
