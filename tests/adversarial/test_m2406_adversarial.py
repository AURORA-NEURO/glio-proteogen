"""Adversarial contract, authorization, replay, and interface closure for M24-06."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from evals.m24_06.fixture import build_request, denied_request, unsupported_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m24_06 import (
    ChallengeDisposition,
    ChallengeKind,
    RobustnessConfiguration,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    M2406AuthorizationError,
    M2406Plugin,
    M2406ReplayError,
    M2406Service,
    RobustnessChallengeSubmission,
    challenge_biomarker_panel_robustness,
    cli_app,
    create_app,
    preflight_m2406_authorization,
)
from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    cli as cli_module,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422
_HTTP_OK = 200


def test_every_authorization_control_fails_closed() -> None:
    request = build_request()
    roles = {
        "approved_configuration": {"state": UpstreamDecisionState.REJECTED},
        "identity_lineage": {"state": IdentityLineageState.UNRESOLVED},
        "provenance": {"state": UpstreamDecisionState.REJECTED},
        "consent": {"state": ConsentState.WITHHELD},
        "quality": {"state": UpstreamDecisionState.REJECTED},
        "support": {"state": UpstreamDecisionState.REJECTED},
        "intended_use": {"state": UpstreamDecisionState.REJECTED},
    }
    for role, update in roles.items():
        references = request.context.references.model_copy(
            update={role: getattr(request.context.references, role).model_copy(update=update)}
        )
        denied = request.context.model_copy(update={"references": references})
        with pytest.raises(M2406AuthorizationError):
            preflight_m2406_authorization(request.model_copy(update={"context": denied}))


def test_preflight_rejects_mapping_shape_and_hostile_get() -> None:
    with pytest.raises(M2406AuthorizationError):
        preflight_m2406_authorization(object())
    with pytest.raises(M2406AuthorizationError):
        preflight_m2406_authorization({"context": None})

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M2406AuthorizationError):
        preflight_m2406_authorization({"context": ExplodingMapping()})


def test_configuration_and_observation_invariants_reject_conflicts() -> None:
    request = build_request()
    configuration = request.configuration
    with pytest.raises(ValidationError, match="challenge kinds"):
        RobustnessConfiguration(
            configuration_id="duplicate",
            version="1.0.0",
            required_challenge_kinds=(*tuple(ChallengeKind)[:-1], ChallengeKind.SITE_SHIFT),
            ood_threshold=0.8,
            evidence=configuration.evidence,
        )
    observation = request.scenarios[0]
    result = M2406Service().challenge(request)
    assert result.robustness_surface is not None
    first = result.robustness_surface.observations[0]
    with pytest.raises(ValidationError, match="bounds"):
        first.__class__.model_validate(
            first.model_dump(mode="python") | {"envelope_lower": 0.9, "envelope_upper": 0.2},
            strict=True,
        )
    with pytest.raises(ValidationError, match="within-envelope"):
        first.__class__.model_validate(
            first.model_dump(mode="python")
            | {"within_envelope": False, "disposition": ChallengeDisposition.WITHIN_ENVELOPE},
            strict=True,
        )
    assert observation.kind is ChallengeKind.MISSING_DATA


def test_surface_and_request_identity_closures_reject_duplicates() -> None:
    request = build_request()
    result = M2406Service().challenge(request)
    assert result.robustness_surface is not None
    surface = result.robustness_surface
    duplicate_scenario = surface.scenarios[0].model_copy(
        update={"scenario_id": surface.scenarios[1].scenario_id}
    )
    with pytest.raises(ValidationError, match="scenario ids"):
        surface.__class__.model_validate(
            surface.model_dump(mode="python")
            | {"scenarios": (duplicate_scenario, *surface.scenarios[1:])},
            strict=True,
        )
    duplicate_observation = surface.observations[0].model_copy(
        update={"observation_id": surface.observations[1].observation_id}
    )
    with pytest.raises(ValidationError, match="observation ids"):
        surface.__class__.model_validate(
            surface.model_dump(mode="python")
            | {"observations": (duplicate_observation, *surface.observations[1:])},
            strict=True,
        )
    with pytest.raises(ValidationError, match="unknown scenario"):
        surface.__class__.model_validate(
            surface.model_dump(mode="python")
            | {
                "observations": (
                    surface.observations[0].model_copy(update={"scenario_id": "unknown"}),
                    *surface.observations[1:],
                )
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="context"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"context": request.context.model_copy(update={"request_id": "wrong"})},
            strict=True,
        )


def test_request_challenge_kind_and_upstream_artifact_closures() -> None:
    request = build_request()
    with pytest.raises(ValidationError, match="exactly all"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"scenarios": request.scenarios[:-1]}, strict=True
        )
    with pytest.raises(ValidationError, match="upstream"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[1],)},
            strict=True,
        )
    duplicate = request.scenarios[0].model_copy(
        update={"scenario_id": request.scenarios[1].scenario_id}
    )
    with pytest.raises(ValidationError, match="scenario ids"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"scenarios": (duplicate, *request.scenarios[1:])},
            strict=True,
        )
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])},
            strict=True,
        )


def test_result_identity_and_safe_abstention_closures() -> None:
    service = M2406Service()
    result = service.challenge(build_request())
    with pytest.raises(ValidationError, match="request digest"):
        result.__class__.model_validate(
            result.model_dump(mode="python") | {"request_digest": "sha256:" + "0" * 64},
            strict=True,
        )
    with pytest.raises(ValidationError, match="result identifier"):
        result.__class__.model_validate(
            result.model_dump(mode="python") | {"result_id": "forged"}, strict=True
        )
    abstained = service.challenge(unsupported_request())
    payload = abstained.model_dump(mode="python")
    payload["support_decision"] = {
        **payload["support_decision"],
        "status": SupportStatus.SUPPORTED,
    }
    with pytest.raises(ValidationError, match="abstained result"):
        abstained.__class__.model_validate(payload, strict=True)
    with pytest.raises(ValidationError, match="supported robustness surface"):
        result.__class__.model_validate(
            result.model_dump(mode="python") | {"robustness_surface": None}, strict=True
        )


def test_canonical_dict_entrypoints_and_public_operation_are_stable() -> None:
    request = build_request()
    dumped = request.model_dump(mode="json")
    assert canonical_request_digest(dumped) == canonical_request_digest(request)
    assert result_payload_digest({"result_digest": "sha256:" + "0" * 64, "request": dumped})
    result = challenge_biomarker_panel_robustness(request)
    assert result.result_id.startswith("m2406.result.")
    assert (
        M2406Service().validate_request(request.model_dump_json()).request_id == request.request_id
    )


def test_engine_rejects_constructed_wrong_upstream_media() -> None:
    request = build_request()
    forged = request.model_construct(
        **{
            **request.model_dump(mode="python"),
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "application/json"}
            ),
        }
    )
    with pytest.raises(ValidationError, match="M24-05"):
        M2406Service().challenge(forged)


def test_service_replay_and_fastapi_tamper_are_sanitized() -> None:
    service = M2406Service()
    result = service.challenge(build_request())
    with pytest.raises(M2406ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    client = TestClient(create_app(service))
    forged = result.model_dump(mode="json")
    forged["result_digest"] = "sha256:" + "0" * 64
    response = client.post("/v1/modules/M24-06/verify", json=forged)
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text
    assert (
        client.post("/v1/modules/M24-06/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    assert client.get("/v1/modules/M24-06/schemas/request").status_code == _HTTP_OK
    denied = client.post(
        "/v1/modules/M24-06/validate",
        content=build_request()
        .model_copy(update={"context": denied_request().context})
        .model_dump_json(),
    )
    assert denied.status_code == _HTTP_UNPROCESSABLE


def test_plugin_and_typer_reject_invalid_tokens_and_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = M2406Plugin(M2406Service())
    with pytest.raises(TypeError, match="robustness challenge submission"):
        plugin.validate(object())
    with pytest.raises((ValidationError, M2406AuthorizationError)):
        plugin.validate(RobustnessChallengeSubmission(request=b"[]"))
    assert (
        plugin.run(
            plugin.validate(
                RobustnessChallengeSubmission(request=build_request().model_dump(mode="python"))
            )
        ).status.value
        == "evaluated"
    )
    runner = CliRunner()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(invalid)]).exit_code != 0
    result_path = tmp_path / "result.json"
    result_path.write_text(
        M2406Service().challenge(build_request()).model_dump_json(), encoding="utf-8"
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(
        build_request().model_copy(update={"context": denied_request().context}).model_dump_json(),
        encoding="utf-8",
    )
    assert runner.invoke(cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["challenge", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(cli_app, ["challenge", str(request_path)]).exit_code == 0
    assert M2406Service().export_json(M2406Service().challenge(build_request()))

    class FakeService:
        def verify_replay(self, result: Any) -> Any:
            return result.model_copy(update={"result_digest": "sha256:" + "0" * 64})

    monkeypatch.setattr(cli_module, "_SERVICE", FakeService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

    class RaisingService:
        def verify_replay(self, result: Any) -> Any:
            del result
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", RaisingService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0


__all__ = []
