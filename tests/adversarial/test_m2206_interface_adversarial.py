"""Negative transport, CLI, plugin and replay coverage for M22-06."""

# ruff: noqa: INP001, PLR2004, TRY003

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used by temporary path annotations.
from typing import Any, NoReturn, cast

import pytest
from fastapi.testclient import TestClient
from tests.adversarial.test_m2206_contract_adversarial import _request
from typer.testing import CliRunner

from glio_proteogen.contracts.m22_06 import (
    ChallengeDisposition,
    ChallengeKind,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ProteinRnaDiscordanceRobustnessChallengeResult,
    RobustnessConfiguration,
    RobustnessSurface,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    M2206Engine,
    M2206Plugin,
    M2206ReplayError,
    M2206Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    cli as m2206_cli,
)
from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    engine as m2206_engine,
)


def test_fastapi_rejects_malformed_non_object_and_tampered_result() -> None:
    client = TestClient(create_app())
    assert client.post("/v1/modules/M22-06/verify", content=b"{").status_code == 422
    assert client.post("/v1/modules/M22-06/verify", json=[]).status_code == 422
    result = M2206Engine().evaluate(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M22-06/verify", json=result).status_code == 422


def test_typer_rejects_malformed_abstained_and_tampered(tmp_path: Path) -> None:
    runner = CliRunner()
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(malformed)]).exit_code != 0
    request = _request()
    failed = request.model_copy(
        update={
            "scenarios": (
                request.scenarios[0].model_copy(
                    update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
                ),
                *request.scenarios[1:],
            )
        }
    )
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(failed.model_dump_json(), encoding="utf-8")
    abstained = runner.invoke(
        cli_app, ["challenge", str(request_path), "--output", str(result_path)]
    )
    assert abstained.exit_code == 1
    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result_digest"] = "sha256:" + "f" * 64
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0


def test_engine_plugin_and_canonical_dict_edges() -> None:
    engine = M2206Engine()
    plugin = M2206Plugin()
    request = _request()
    with pytest.raises((TypeError, ValueError)):
        plugin.validate("{")
    with pytest.raises((TypeError, ValueError)):
        plugin.validate({"bad": True})
    with pytest.raises((TypeError, ValueError)):
        plugin.verify({"bad": True})
    with pytest.raises(M2206ReplayError):
        engine.verify(object())
    result = engine.evaluate(request)
    assert plugin.verify(result).result_digest == result.result_digest
    with pytest.raises(M2206ReplayError):
        engine.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert result_payload_digest(result) == result_payload_digest(result.model_dump(mode="json"))


def test_result_closure_and_engine_validation_reject_tampering() -> None:
    request = _request()
    result = M2206Engine().evaluate(request)
    invalid_request = request.model_dump(mode="python")
    invalid_request["request_id"] = "request.m2206.invalid"
    with pytest.raises(ValueError, match="request is invalid"):
        M2206Engine().validate_request(invalid_request)

    changed_digest = result.model_dump(mode="python")
    changed_digest["request_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="exact request"):
        type(result).model_validate(changed_digest)
    changed_identifier = result.model_dump(mode="python")
    changed_identifier["result_id"] = "result." + "f" * 64
    with pytest.raises(ValueError, match="derived from request"):
        type(result).model_validate(changed_identifier)

    tampered_model = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    class TamperedAdapter:
        def validate_python(
            self, _candidate: object, *, strict: bool = True
        ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
            del strict
            return tampered_model

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(m2206_engine, "_RESULT_ADAPTER", cast("Any", TamperedAdapter()))
    try:
        with pytest.raises(M2206ReplayError, match="digest mismatch"):
            M2206Engine().verify(tampered_model)
    finally:
        monkeypatch.undo()

    unsupported = request.model_copy(
        update={
            "scenarios": (
                request.scenarios[0].model_copy(
                    update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
                ),
                *request.scenarios[1:],
            )
        }
    )
    abstained = M2206Engine().evaluate(unsupported)
    invalid_abstention = abstained.model_dump(mode="python")
    invalid_abstention["safe_failure_report"] = None
    with pytest.raises(ValueError, match="safe failure"):
        type(abstained).model_validate(invalid_abstention)


def test_preflight_property_failure_is_safe() -> None:
    class Broken:
        @property
        def context(self) -> object:
            raise RuntimeError("malformed context")

    with pytest.raises(ValueError, match="controls are malformed"):
        M2206Engine().evaluate(Broken())


def test_contract_closure_rejects_duplicate_and_unknown_members() -> None:
    request = _request()
    duplicate_config = request.configuration.model_dump(mode="python")
    duplicate_config["required_challenge_kinds"] = (
        *tuple(ChallengeKind)[:-1],
        ChallengeKind.MISSING_DATA,
    )
    with pytest.raises(ValueError, match="challenge kinds must be unique"):
        RobustnessConfiguration.model_validate(duplicate_config)

    surface = M2206Engine().evaluate(request).robustness_surface
    assert surface is not None
    surface_dict = surface.model_dump(mode="python")
    surface_dict["scenarios"] = (*surface.scenarios[:-1], surface.scenarios[0])
    with pytest.raises(ValueError, match="scenario ids must be unique"):
        RobustnessSurface.model_validate(surface_dict)
    duplicate_observations = surface.model_dump(mode="python")
    duplicate_observations["observations"] = (
        *surface.observations[:-1],
        surface.observations[0],
    )
    with pytest.raises(ValueError, match="observation ids must be unique"):
        RobustnessSurface.model_validate(duplicate_observations)
    unknown_observation = surface.model_dump(mode="python")
    unknown_observation["observations"] = (
        *surface.observations[:-1],
        surface.observations[-1].model_copy(update={"scenario_id": "scenario.unknown"}),
    )
    with pytest.raises(ValueError, match="unknown scenario"):
        RobustnessSurface.model_validate(unknown_observation)

    duplicate_request = request.model_dump(mode="python")
    duplicate_request["scenarios"] = (*request.scenarios[:-1], request.scenarios[0])
    with pytest.raises(ValueError, match="scenario ids must be unique"):
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(duplicate_request)
    duplicate_source = request.model_dump(mode="python")
    duplicate_source["source_artifacts"] = (request.source_artifacts[0],) * 2
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(duplicate_source)


def test_api_known_schema_and_sanitized_service_errors() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M22-06/schemas/request").status_code == 200

    class BrokenService(M2206Service):
        def validate_request(self, _candidate: object) -> NoReturn:
            raise ValueError("secret validation detail")

        def execute(self, _candidate: object) -> NoReturn:
            raise ValueError("secret execution detail")

        def verify(self, _candidate: object, *, replay: bool = True) -> NoReturn:
            del replay
            raise ValueError("secret replay detail")

    broken_client = TestClient(create_app(BrokenService()))
    payload = _request().model_dump(mode="json")
    validation = broken_client.post("/v1/modules/M22-06/validate", json=payload)
    assert validation.status_code == 422
    assert "secret" not in validation.text
    challenge = broken_client.post("/v1/modules/M22-06/challenge", json=payload)
    assert challenge.status_code == 422
    assert "secret" not in challenge.text

    valid_result = M2206Engine().evaluate(_request()).model_dump(mode="json")
    replay = broken_client.post("/v1/modules/M22-06/verify", json=valid_result)
    assert replay.status_code == 422
    assert "secret" not in replay.text


def test_cli_schema_output_and_sanitized_service_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "schema.json"
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        == 0
    )
    assert schema_path.exists()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0

    class BrokenService(M2206Service):
        def validate_request(self, _candidate: object) -> NoReturn:
            raise ValueError("secret validation detail")

        def execute(self, _candidate: object) -> NoReturn:
            raise ValueError("secret execution detail")

        def verify(self, _candidate: object, *, replay: bool = True) -> NoReturn:
            del replay
            raise ValueError("secret replay detail")

    monkeypatch.setattr(m2206_cli, "_SERVICE", BrokenService())
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    validation = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validation.exit_code != 0
    assert "secret" not in validation.output
    challenge = runner.invoke(cli_app, ["challenge", str(request_path)])
    assert challenge.exit_code != 0
    assert "secret" not in challenge.output


def test_cli_supported_stdout_and_verify_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    challenge = runner.invoke(cli_app, ["challenge", str(request_path)])
    assert challenge.exit_code == 0
    result_path.write_text(challenge.stdout, encoding="utf-8")

    class MismatchService(M2206Service):
        def verify(
            self,
            result: object,
            *,
            replay: bool = True,
        ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
            del result
            del replay
            return (
                M2206Engine()
                .evaluate(_request())
                .model_copy(update={"result_digest": "sha256:" + "f" * 64})
            )

    monkeypatch.setattr(m2206_cli, "_SERVICE", MismatchService())
    mismatch = runner.invoke(cli_app, ["verify", str(result_path)])
    assert mismatch.exit_code == 1
    assert '"verified": false' in mismatch.stdout
