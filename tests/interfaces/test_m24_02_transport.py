"""Transport and CLI size-boundary tests for M24-02."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    M2402_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c21_reference_material.m24_02_synthetic_truth_simulation_generator import (  # noqa: E501
    cli as cli_module,
)
from glio_proteogen.modules.c21_reference_material.m24_02_synthetic_truth_simulation_generator.api import (  # noqa: E501
    create_app,
)


def test_http_request_ceiling_rejects_before_route_parsing() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/modules/M24-02/generate",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(M2402_MAX_CANONICAL_REQUEST_BYTES + 1),
        },
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_http_result_ceiling_rejects_before_replay_parsing() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/modules/M24-02/verify",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(M2402_MAX_CANONICAL_RESULT_BYTES + 1),
        },
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_cli_result_ceiling_rejects_oversized_file() -> None:
    result_path = Path(__file__)
    with patch.object(cli_module, "read_bounded", side_effect=RequestBodyTooLargeError):
        result = CliRunner().invoke(cli_module.app, ["verify", str(result_path)])

    assert result.exit_code != 0
    assert "valid M24-02 result" in result.output
