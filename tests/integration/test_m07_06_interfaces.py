"""HTTP, CLI, and plugin parity tests for provisional M07-06."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m07_06 import M0706_CONSTRAINT_MEDIA_TYPE
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706Plugin,
    M0706Service,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.api import (
    create_app,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.cli import (
    app as cli_app,
)

if TYPE_CHECKING:
    from pathlib import Path

_OK = 200
_UNPROCESSABLE = 422
_NOT_FOUND = 404


def _artifact(
    label: str, char: str = "a", media_type: str = "application/json"
) -> dict[str, object]:
    return {
        "artifact_id": label,
        "version": "1.0.0",
        "digest": f"sha256:{char * 64}",
        "media_type": media_type,
    }


def _accepted(label: str) -> dict[str, object]:
    return {
        "decision_id": f"decision.m0706.{label}",
        "state": "accepted",
        "policy_version": "1.0.0",
        "evidence": _artifact(f"evidence.{label}"),
    }


def _request() -> dict[str, object]:
    constraint = _artifact("constraint.m0705", "d", M0706_CONSTRAINT_MEDIA_TYPE)
    return {
        "request_id": "request.m0706.interface",
        "context": {
            "request_id": "request.m0706.interface",
            "actor_id": "actor.m0706.interface",
            "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "references": {
                "approved_configuration": _accepted("configuration"),
                "identity_lineage": {
                    "decision_id": "decision.m0706.identity",
                    "state": "resolved",
                    "policy_version": "1.0.0",
                    "binding_digest": "sha256:" + "b" * 64,
                    "evidence": _artifact("evidence.identity", "b"),
                },
                "provenance": _accepted("provenance"),
                "consent": {
                    "decision_id": "decision.m0706.consent",
                    "state": "granted",
                    "policy_version": "1.0.0",
                    "evidence": _artifact("evidence.consent", "c"),
                },
                "quality": _accepted("quality"),
                "support": _accepted("support"),
                "intended_use": _accepted("intended-use"),
            },
        },
        "constraint_result": constraint,
        "policy": {
            "policy_id": "policy.m0706.interface",
            "version": "1.0.0",
            "method": "provisional-no-calibration",
            "calibration_reference": _artifact("calibration.m0706", "e"),
        },
        "source_artifacts": [constraint, _artifact("source.proteome", "f")],
    }


def test_api_validate_decompose_and_verify_have_stable_shapes() -> None:
    client = TestClient(create_app())
    valid = client.post("/v1/modules/M07-06/validate", json=_request())
    assert valid.status_code == _OK
    decomposed = client.post("/v1/modules/M07-06/decompose", json=_request())
    assert decomposed.status_code == _OK
    result = decomposed.json()["result"]
    verified = client.post("/v1/modules/M07-06/verify", json=result)
    assert verified.status_code == _OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M07-06/schemas/output").status_code == _OK
    assert client.get("/v1/modules/M07-06/schemas/not-a-contract").status_code == _NOT_FOUND


def test_api_rejects_duplicate_json_keys_and_sanitizes_validation() -> None:
    client = TestClient(create_app())
    duplicate = client.post(
        "/v1/modules/M07-06/validate",
        content=b'{"request_id":"a","request_id":"b"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == _UNPROCESSABLE
    assert duplicate.json()["detail"]["type"] == "json_duplicate_key"
    invalid = client.post("/v1/modules/M07-06/validate", json={"context": {}})
    assert invalid.status_code == _UNPROCESSABLE
    assert all("input" not in error for error in invalid.json()["detail"])


def test_plugin_and_cli_parse_once_and_match_service(tmp_path: Path) -> None:
    payload = _request()
    plugin = M0706Plugin(M0706Service())
    token = plugin.validate(payload)
    result = plugin.run(token)
    assert plugin.verify(result).model_dump(mode="json") == result.model_dump(mode="json")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = CliRunner()
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    output_path = tmp_path / "result.json"
    execution = runner.invoke(
        cli_app, ["decompose", str(request_path), "--output", str(output_path)]
    )
    assert execution.exit_code == 1
    verified = runner.invoke(cli_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
