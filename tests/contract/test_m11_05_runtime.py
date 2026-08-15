"""Adversarial contract/runtime/interface tests for M11-05."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m1105 as m1105_adapter
from glio_proteogen.adapters.m1105 import app, m1105_app
from glio_proteogen.contracts.m11_05 import (
    M1105_M1104_RESULT_MEDIA_TYPE,
    ChangePoint,
    EvolutionModelConfiguration,
    EvolutionModelFamily,
    ModelVariantPeptideLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryDimension,
    TrajectoryPolicy,
    TrajectoryStatus,
    VariantPeptideLongitudinalEvolutionResult,
    contract_json_schema,
    expected_uncertainty,
)
from glio_proteogen.contracts.m11_05.canonical import (
    normalized_request,
    result_payload_digest,
)
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_05_longitudinal_evolution import (
    M1105AuthorizationError,
    M1105LongitudinalEngine,
    M1105Plugin,
    M1105ReplayVerificationError,
    M1105Service,
    ValidatedM1105Request,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_FORBIDDEN = 403
_HTTP_BAD_REQUEST = 400
_CLI_USAGE_ERROR = 2


def _digest(letter: str) -> str:
    return f"sha256:{letter * 64}"


def _artifact(name: str, letter: str = "a", media: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_digest(letter),
        media_type=media,
    )


def _request(*, denied_role: str | None = None) -> ModelVariantPeptideLongitudinalEvolutionRequest:
    artifact = _artifact("evidence", "b")
    upstream = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=(
                UpstreamDecisionState.REJECTED
                if role == denied_role
                else UpstreamDecisionState.ACCEPTED
            ),
            policy_version="1.0.0",
            evidence=artifact,
        )
        for role in (
            "approved_configuration",
            "provenance",
            "quality",
            "support",
            "intended_use",
        )
    }
    references = ContextReferences(
        approved_configuration=upstream["approved_configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity_lineage",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_digest("c"),
            evidence=artifact,
        ),
        provenance=upstream["provenance"],
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.WITHHELD if denied_role == "consent" else ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=artifact,
        ),
        quality=upstream["quality"],
        support=upstream["support"],
        intended_use=upstream["intended_use"],
    )
    context = ExecutionContext(
        request_id="request.m1105",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=references,
    )
    model = EvolutionModelConfiguration(
        configuration_id="config.m1105",
        version="1.0.0",
        model_family=EvolutionModelFamily.STATE_SPACE,
        objective="deterministic ordered trajectory baseline",
        model_reference=_artifact("model", "d", "application/model"),
    )
    policy = TrajectoryPolicy(
        dimensions=(TrajectoryDimension.TIME_COURSE, TrajectoryDimension.TREATMENT_ERA),
        minimum_observations=2,
        configuration=model,
    )
    observations = (
        TimePointObservation(
            observation_id="observation.1",
            sequence=0,
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            territory="primary",
            treatment_era="baseline",
            feature_artifact=_artifact("feature.1", "e"),
            evidence=(
                # Reusing an immutable reference is permitted; the observation ID is unique.
                EvidenceReference(reference=artifact, role="evidence", claim="observation"),
            ),
        ),
        TimePointObservation(
            observation_id="observation.2",
            sequence=1,
            observed_at=datetime(2026, 2, 1, tzinfo=UTC),
            territory="recurrent",
            treatment_era="post-treatment",
            feature_artifact=_artifact("feature.2", "f"),
            evidence=(),
        ),
        TimePointObservation(
            observation_id="observation.3",
            sequence=2,
            observed_at=datetime(2026, 3, 1, tzinfo=UTC),
            territory="recurrent",
            treatment_era="post-treatment",
            feature_artifact=_artifact("feature.3", "0"),
            evidence=(),
        ),
    )
    return ModelVariantPeptideLongitudinalEvolutionRequest(
        request_id="request.m1105",
        context=context,
        network_state_result=_artifact("mechanism-result", "1", M1105_M1104_RESULT_MEDIA_TYPE),
        policy=policy,
        observations=observations,
        source_artifacts=(artifact,),
    )


def test_supported_runtime_replays_and_detects_change_point() -> None:
    request = _request()
    service = M1105Service()
    result = service.execute(request)
    assert result.status.value == "modeled"
    assert [state.state_id for state in result.trajectory] == ["state.0", "state.1"]
    assert result.change_points[0].status.value == "detected"
    assert result.human_review_required is True
    assert service.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_denied_control_fails_before_payload_traversal() -> None:
    class Hostile:
        def __getattribute__(self, name: str) -> Any:
            if name == "context":
                return _request(denied_role="support").context
            raise AssertionError

    with pytest.raises(M1105AuthorizationError):
        M1105LongitudinalEngine().infer(Hostile())


def test_out_of_order_and_duplicate_history_are_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="strictly ordered"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate(
            request.model_copy(
                update={
                    "observations": tuple(reversed(request.observations)),
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="unique"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate(
            request.model_copy(
                update={
                    "observations": (
                        *request.observations[:2],
                        request.observations[0].model_copy(update={"sequence": 2}),
                    ),
                }
            ),
            strict=True,
        )


def test_tampering_is_rejected_without_replay() -> None:
    result = M1105LongitudinalEngine().infer(_request())
    payload = result.model_dump(mode="json")
    payload["trajectory"][0]["label"] = "tampered"
    with pytest.raises(M1105ReplayVerificationError):
        M1105LongitudinalEngine().verify(payload, replay=False)
    payload = result.model_dump(mode="json")
    payload["request"]["observations"][1]["territory"] = "tampered"
    with pytest.raises(M1105ReplayVerificationError):
        M1105LongitudinalEngine().verify(payload)


def test_plugin_is_parse_once_and_token_bound() -> None:
    service = M1105Service()
    plugin = M1105Plugin(service)
    raw = json.dumps(_request().model_dump(mode="json"), separators=(",", ":"))
    token = plugin.validate(raw)
    assert plugin.run(token).status.value == "modeled"
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M11-05"


def test_api_and_cli_schema_and_execution(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(_request().model_dump(mode="json"), separators=(",", ":")), encoding="utf-8"
    )
    client = TestClient(app)
    response = client.post(
        "/v1/modules/M11-05/evolve",
        content=request_path.read_bytes(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_OK
    assert client.get("/v1/m11-05/schema/request").status_code == _HTTP_OK
    assert client.get("/v1/m11-05/schema/nope").status_code == _HTTP_NOT_FOUND
    assert (
        client.post(
            "/v1/modules/M11-05/evolve",
            content=request_path.read_bytes(),
            headers={"content-type": "text/plain"},
        ).status_code
        == _HTTP_UNSUPPORTED_MEDIA
    )
    runner = CliRunner()
    registered = runner.invoke(
        m1105_app, ["evolve", str(request_path), "--output", str(result_path)]
    )
    assert registered.exit_code == 0, registered.stdout
    verified = runner.invoke(m1105_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.stdout
    schema = runner.invoke(m1105_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    metadata = cast("dict[str, object]", contract_json_schema("request")["x-glio-contract"])
    assert metadata["provisionalAbi"] is True


def test_service_typed_path_and_canonical_dict_projection() -> None:
    request = _request()
    service = M1105Service()
    assert service.validate_request(request) == request
    assert normalized_request(request.model_dump(mode="json"))["request_id"] == request.request_id
    assert expected_uncertainty(supported=False).measurement.probability is None


def test_plugin_typed_path_forged_token_and_verify() -> None:
    service = M1105Service()
    plugin = M1105Plugin(service)
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "modeled"
    assert plugin.verify(plugin.run(token)).status.value == "modeled"
    forged = ValidatedM1105Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)


def test_engine_malformed_and_replay_mismatch_paths() -> None:
    engine = M1105LongitudinalEngine()
    result = engine.infer(_request())
    with pytest.raises(M1105ReplayVerificationError):
        engine.verify({}, replay=False)

    class DivergentEngine(M1105LongitudinalEngine):
        def infer(self, _request: object) -> VariantPeptideLongitudinalEvolutionResult:
            return result.model_copy(update={"human_review_required": False})

    with pytest.raises(M1105ReplayVerificationError):
        DivergentEngine().verify(result)


def test_contract_negative_shapes_and_result_closure() -> None:
    request = _request()
    duplicate_dimensions = request.model_dump(mode="json")
    duplicate_dimensions["policy"]["dimensions"] = ["time_course", "time_course"]
    with pytest.raises(ValueError, match="dimensions must be unique"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate_json(
            canonical_json_bytes(duplicate_dimensions), strict=True
        )
    with pytest.raises(ValueError, match="detected change point"):
        ChangePoint.model_validate_json(
            canonical_json_bytes(
                {
                    "change_point_id": "change.invalid",
                    "sequence": 1,
                    "status": "detected",
                    "rationale": "missing evidence",
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="non-detected"):
        ChangePoint.model_validate_json(
            canonical_json_bytes(
                {
                    "change_point_id": "change.invalid",
                    "sequence": 1,
                    "status": "not_detected",
                    "before_state_id": "state.0",
                    "rationale": "shape is closed",
                }
            ),
            strict=True,
        )
    request_payload = request.model_dump(mode="json")
    request_payload["policy"]["dimensions"] = ["time_course", "time_course"]
    with pytest.raises(ValueError, match="unique"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate_json(
            canonical_json_bytes(request_payload), strict=True
        )
    too_short = request.model_dump(mode="json")
    too_short["policy"]["minimum_observations"] = 4
    with pytest.raises(ValueError, match="minimum"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate_json(
            canonical_json_bytes(too_short), strict=True
        )
    times_reversed = request.model_dump(mode="json")
    observations = cast("list[dict[str, object]]", times_reversed["observations"])
    observations[0]["observed_at"], observations[1]["observed_at"] = (
        observations[1]["observed_at"],
        observations[0]["observed_at"],
    )
    with pytest.raises(ValueError, match="observed_at"):
        ModelVariantPeptideLongitudinalEvolutionRequest.model_validate_json(
            canonical_json_bytes(times_reversed), strict=True
        )

    result = M1105LongitudinalEngine().infer(request)

    def invalid_result(**updates: object) -> None:
        payload = result.model_dump(mode="json")
        payload.update(updates)
        with pytest.raises(ValueError, match=r"."):
            type(result).model_validate_json(canonical_json_bytes(payload), strict=True)

    invalid_result(request_digest=_digest("9"))
    invalid_result(trajectory=[])
    invalid_result(
        status=TrajectoryStatus.ABSTAINED.value,
        abstention_reason="not evaluable",
        support_decision={
            "status": "unsupported",
            "reason_code": "m1105_unsupported",
            "rationale": "safe failure",
        },
    )
    duplicate_states = result.model_dump(mode="json")
    duplicate_states["trajectory"][1]["state_id"] = duplicate_states["trajectory"][0]["state_id"]
    with pytest.raises(ValueError, match="state identifiers"):
        type(result).model_validate_json(canonical_json_bytes(duplicate_states), strict=True)
    unordered_states = result.model_dump(mode="json")
    unordered_states["trajectory"] = list(reversed(unordered_states["trajectory"]))
    with pytest.raises(ValueError, match="ordered"):
        type(result).model_validate_json(canonical_json_bytes(unordered_states), strict=True)
    duplicate_diagnostics = result.model_dump(mode="json")
    duplicate_diagnostics["diagnostics"][1]["diagnostic_id"] = duplicate_diagnostics["diagnostics"][
        0
    ]["diagnostic_id"]
    with pytest.raises(ValueError, match="diagnostic identifiers"):
        type(result).model_validate_json(canonical_json_bytes(duplicate_diagnostics), strict=True)
    too_many_change_points = result.model_dump(mode="json")
    base_change = too_many_change_points["change_points"][0]
    too_many_change_points["change_points"] = [
        {**base_change, "change_point_id": f"change.extra.{index}"} for index in range(4)
    ]
    with pytest.raises(ValueError, match="exceeds"):
        type(result).model_validate_json(canonical_json_bytes(too_many_change_points), strict=True)
    invalid_result(result_digest=_digest("9"))
    assert result_payload_digest(result) == result.result_digest


def test_api_and_cli_negative_boundaries(tmp_path: Path) -> None:
    request_payload = canonical_json_bytes(_request())
    client = TestClient(app)
    assert (
        client.post(
            "/v1/m11-05/evolve",
            content=b'{"request_id":1,"request_id":2}',
            headers={"content-type": "application/json"},
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    invalid_body = _request().model_dump(mode="json")
    invalid_body.pop("observations")
    assert (
        client.post(
            "/v1/m11-05/evolve",
            content=canonical_json_bytes(invalid_body),
            headers={"content-type": "application/json"},
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    denied_payload = canonical_json_bytes(_request(denied_role="support"))
    assert (
        client.post(
            "/v1/m11-05/evolve",
            content=denied_payload,
            headers={"content-type": "application/json"},
        ).status_code
        == _HTTP_FORBIDDEN
    )
    result = M1105LongitudinalEngine().infer(_request())
    result_payload = canonical_json_bytes(result)
    assert (
        client.post(
            "/v1/m11-05/verify",
            content=result_payload,
            headers={"content-type": "application/json"},
        ).status_code
        == _HTTP_OK
    )
    assert (
        client.post(
            "/v1/m11-05/verify",
            content=b"{}",
            headers={"content-type": "application/json"},
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post(
            "/v1/m11-05/verify",
            content=result_payload,
            headers={"content-type": "text/plain"},
        ).status_code
        == _HTTP_UNSUPPORTED_MEDIA
    )
    runner = CliRunner()
    assert runner.invoke(m1105_app, ["export-schema", "unknown"]).exit_code == _CLI_USAGE_ERROR
    request_path = tmp_path / "request.json"
    request_path.write_bytes(request_payload)
    assert runner.invoke(m1105_app, ["evolve", str(request_path)]).exit_code == 0
    output = tmp_path / "result.json"
    output.write_text("existing", encoding="utf-8")
    assert (
        runner.invoke(m1105_app, ["evolve", str(request_path), "--output", str(output)]).exit_code
        != 0
    )
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1105_app, ["evolve", str(bad)]).exit_code != 0
    assert runner.invoke(m1105_app, ["verify", str(bad)]).exit_code != 0
    assert runner.invoke(m1105_app, ["verify", str(tmp_path / "missing.json")]).exit_code != 0


def test_adapter_private_error_and_canonical_mapping_paths() -> None:
    assert m1105_adapter._json_error(_HTTP_BAD_REQUEST, "bad").status_code == _HTTP_BAD_REQUEST
    assert normalized_request({"x": 1}) == {"x": 1}
    assert result_payload_digest({"result_digest": "ignored", "x": 1}) == result_payload_digest(
        {"x": 1}
    )
