"""Adversarial M19-07 claims-ceiling and interface parity coverage."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m19_07 import (
    ExportFindingCode,
    ExportProteotypeDownstreamContractRequest,
    ExportStatus,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    M1907Engine,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    api as m1907_api,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    cli as m1907_cli,
)
from tests.contract.test_m19_07_deep import _evidence, _request

_BAD_CLAIM = "caller claims protein inference for glioma-specific biology"
_HTTP_OK = 200

if TYPE_CHECKING:
    from pathlib import Path


def _request_with_claim_surface(
    surface: str,
) -> ExportProteotypeDownstreamContractRequest:
    request = _request()
    if surface == "field.documentation":
        field = request.fields[0].model_copy(update={"documentation": _BAD_CLAIM})
        return request.model_copy(update={"fields": (field,)})
    if surface == "support.rationale":
        support = request.support_decision.model_copy(update={"rationale": _BAD_CLAIM})
        return request.model_copy(update={"support_decision": support})
    if surface == "configuration.evidence":
        evidence = _evidence("prohibited-configuration").model_copy(update={"claim": _BAD_CLAIM})
        configuration = request.configuration.model_copy(update={"evidence": (evidence,)})
        return request.model_copy(update={"configuration": configuration})
    if surface == "field.evidence":
        evidence = _evidence("prohibited-field").model_copy(update={"claim": _BAD_CLAIM})
        field = request.fields[0].model_copy(update={"evidence": (evidence,)})
        return request.model_copy(update={"fields": (field,)})
    raise AssertionError


@pytest.mark.parametrize(
    "surface",
    ["field.documentation", "support.rationale", "configuration.evidence", "field.evidence"],
)
def test_every_caller_claim_surface_abstains_without_contract(surface: str) -> None:
    result = M1907Engine().export(_request_with_claim_surface(surface))
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.support_decision.status.value == "unsupported"
    assert any(
        finding.code is ExportFindingCode.PROHIBITED_CLAIM_BOUNDARY for finding in result.findings
    )
    assert M1907Engine().verify(result) == result


def test_api_and_cli_preserve_claim_boundary_abstention(tmp_path: Path) -> None:
    request = _request_with_claim_surface("configuration.evidence")
    payload = request.model_dump(mode="json")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(m1907_api.create_m1907_app()) as client:
        api_response = client.post("/v1/modules/M19-07/export", json=payload)
    cli_result = CliRunner().invoke(m1907_cli.app, ["export", str(request_path)])

    assert api_response.status_code == _HTTP_OK, api_response.text
    assert cli_result.exit_code == 0, cli_result.output
    api_payload = api_response.json()
    cli_payload = json.loads(cli_result.stdout)
    assert api_payload == cli_payload
    assert api_payload["status"] == ExportStatus.ABSTAINED.value
    assert api_payload["contract"] is None
    assert any(
        finding["code"] == ExportFindingCode.PROHIBITED_CLAIM_BOUNDARY.value
        for finding in api_payload["findings"]
    )
